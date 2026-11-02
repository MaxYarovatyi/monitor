import sys
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
import os

import numpy as np

from ingest.ts_analyzer import UdpTsAnalyzer


def _find_ffmpeg():
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent.parent
    local = base / "ffmpeg" / "ffmpeg.exe"
    if local.exists():
        return str(local)
    return shutil.which("ffmpeg") or "ffmpeg"

FFMPEG = _find_ffmpeg()
print("ffmpeg:", FFMPEG)
TILE_W, TILE_H, TILE_FPS = 320, 180, 12
FRAME_BYTES = TILE_W * TILE_H * 3
AUDIO_RATE = 16000
AUDIO_CHUNK = AUDIO_RATE // 10 * 2        # 0.1 с, mono s16le = 3200 байт
NO_SIGNAL_S = 8.0
RECONNECT_S = 3.0


def _srt_caller(url):
    if not url.lower().startswith("srt") or "mode=" in url.lower():
        return url
    return url + ("&" if "?" in url else "?") + "mode=caller"

def _kill_tree(p):
    if p.poll() is not None:
        return
    try:
        p.kill()
    except Exception:
        pass
    if Path(FFMPEG).parent.name != "ffmpeg":     # shim Chocolatey: потрібне вбивство дерева
           subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                          capture_output=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

def build_cmd(url, mode, audio_port=None, tap_port=None, quality="full"):
    cmd = [FFMPEG, "-hide_banner", "-loglevel", os.environ.get("MV_FFLOG", "error"), "-nostdin"]
    low = url.lower()
    if "://" not in url:
        cmd += ["-re", "-stream_loop", "-1"]
    elif low.startswith("udp"):
        cmd += ["-fifo_size", "100000", "-overrun_nonfatal", "1"]
    elif low.startswith("rtmp"):
        cmd += ["-rtmp_live", "live"]
    elif low.startswith("http"):
        cmd += ["-reconnect", "1", "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5"]
    vsync = []
    if mode == "cuvid":
        cmd += ["-c:v", "h264_cuvid", "-deint", "adaptive",
                "-resize", f"{TILE_W}x{TILE_H}"]
        vf = f"fps={TILE_FPS}"
    elif mode == "cuda":
        cmd += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda","-extra_hw_frames", "4"]
        vf = f"scale_cuda={TILE_W}:{TILE_H},hwdownload,format=nv12,fps={TILE_FPS}"
    else:
        cmd += ["-threads", "1"]          # 20 процесів × багато потоків декодера = зайве перемикання
        if quality == "smooth":
            cmd += ["-skip_loop_filter", "all", "-skip_frame", "noref"]
        elif quality == "light":
            cmd += ["-skip_loop_filter", "all", "-skip_frame", "nokey"]
        vf = f"scale={TILE_W}:{TILE_H}:flags=fast_bilinear"
        if quality == "light":
            vsync = ["-fps_mode", "passthrough"]    # лише справжні кадри, без дублікатів
        else:
            vf += f",fps={TILE_FPS}"
    cmd += ["-fflags", "nobuffer", "-analyzeduration", "5000000",
            "-probesize", "5000000", "-i", _srt_caller(url),
            # вихід 1: відео в pipe
            "-map", "0:v:0", "-an", "-sn", "-vf", vf, *vsync,
            "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
    if audio_port:                            # вихід 2: звук
        cmd += ["-map", "0:a:0?", "-vn", "-ac", "1", "-ar", str(AUDIO_RATE),
                "-f", "s16le", f"tcp://127.0.0.1:{audio_port}"]
    if tap_port:                              # вихід 3: копія потоку для лічильника бітрейту
        cmd += ["-map", "0:v:0", "-c", "copy",
                "-f", "mpegts", f"tcp://127.0.0.1:{tap_port}"]
    return cmd


def _server():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    return srv, srv.getsockname()[1]


class ChannelPipeline:
    """Один канал: ffmpeg -> кадри, піки звуку, бітрейт. Колбеки йдуть з робочих потоків."""

    def __init__(self, url, decoder="auto", on_frame=None, on_status=None,
                 on_audio=None, on_stats=None, quality="full"):
        self.url = url
        self.decoder = decoder                # auto | cuda | cpu
        self.on_frame = on_frame or (lambda b: None)
        self.on_status = on_status or (lambda s: None)
        self.on_audio = on_audio or (lambda db: None)
        self.on_stats = on_stats or (lambda d: None)
        self.audio = True
        self.last_error = ""
        self._stop = threading.Event()
        self._proc = None
        self._last_frame = time.time()
        self._tap_bytes = 0
        self._ts = None
        self.err_log = []
        self.quality = quality
        self._switching = False

    def set_quality(self,q):
        if q == self.quality:
            return
        self.quality = q
        self._switching = True
        self._kill()
    def start(self):
        if self.url.lower().startswith("udp"):
            self._ts = UdpTsAnalyzer(self.url, self.on_stats)
            self._ts.start()
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()
        if self._ts:
            self._ts.stop()
        self._kill()

    def _kill(self):
        p = self._proc
        if p and p.poll() is None:
            try:
                _kill_tree(p)
            except Exception:
                pass

    def _run(self):
        gpu = {"cpu": "cpu" , "cuvid":"cuvid"}.get(self.decoder, "cuda")
        while not self._stop.is_set():
            self._switching = False
            mode = gpu if self.quality == "full" else "cpu"
            self.on_status(f"CONNECTING ({mode}/{self.quality})")
            frames = self._session(mode)
            if self._stop.is_set():
                break
            if self._switching:           # це зміна якості, а не збій
                continue
            err = self.last_error or "немає кадрів 8 с"
            print(f"[{self.url}] {mode}: кадрів {frames}: " + " | ".join(self.err_log[-5:]))
            self.on_status(f"NO_SIGNAL: {err[:70]}")
            if frames == 0:
                if any("does not contain any stream" in l for l in self.err_log):
                    self.audio = False
                elif self.decoder == "auto" and self.quality == "full":
                    gpu = "cpu" if gpu == "cuda" else "cuda"
            self._stop.wait(RECONNECT_S)

    def _session(self, mode):
        self.last_error = ""
        q = self.quality
        self.err_log = []
        self._tap_bytes = 0
        a_srv, a_port = _server() if self.audio else (None, None)
        t_srv, t_port = _server()
        try:
            p = subprocess.Popen(
                build_cmd(self.url, mode, a_port, t_port, q),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            self.last_error = str(e)
            for s in (a_srv, t_srv):
                if s:
                    s.close()
            return 0
        self._proc = p
        self._last_frame = time.time()

        def drain():
            for line in p.stderr:
                txt = line.decode(errors="replace").strip()
                self.last_error = txt
                self.err_log.append(txt)
                if os.environ.get("MV_FFLOG"):
                    print(f"[{self.url}] {txt}")
                del self.err_log[:-30]
        threading.Thread(target=drain, daemon=True).start()
        got = [False]
        def watchdog():
            while p.poll() is None and not self._stop.is_set():
                limit = (15.0 if q == "light" else NO_SIGNAL_S) if got[0] else 20.0
                if time.time() - self._last_frame > limit:
                    _kill_tree(p)
                    return
                time.sleep(0.5)
        threading.Thread(target=watchdog, daemon=True).start()

        if a_srv:
            buf = bytearray()

            def on_audio_bytes(chunk):
                buf.extend(chunk)
                while len(buf) >= AUDIO_CHUNK:
                    self.on_audio(self._peak_db(bytes(buf[:AUDIO_CHUNK])))
                    del buf[:AUDIO_CHUNK]
            threading.Thread(target=self._serve, args=(a_srv, p, on_audio_bytes),
                             daemon=True).start()

        def on_tap_bytes(chunk):
            self._tap_bytes += len(chunk)
        threading.Thread(target=self._serve, args=(t_srv, p, on_tap_bytes),
                         daemon=True).start()
        threading.Thread(target=self._bitrate_loop, args=(p,), daemon=True).start()

        frames = 0
        t_fps, n_fps = time.time(), 0
        last = time.time()
        while True:
            data = p.stdout.read(FRAME_BYTES)
            if len(data) < FRAME_BYTES:
                break
            t1 = time.time()
            frames += 1
            self._last_frame = t1
            if frames == 1:
                self.on_status(f"OK ({mode}/{q})")
            self.on_frame(data)
            t2 = time.time()
            if t2 - t1 > 0.05:
                print(f"[{self.url[-10:]} {mode}/{q}] callback {1000*(t2-t1):.0f} мс")
            if t1 - last > 0.5:
                 print(f"[{self.url[-10:]} {mode}/{q}] чекали кадр {t1-last:.2f} с")
            last = t2
        self._kill()
        return frames

    def _serve(self, srv, p, on_chunk):
        srv.settimeout(1.0)
        conn = None
        try:
            while conn is None and p.poll() is None and not self._stop.is_set():
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    pass
            if conn is None:
                return
            conn.settimeout(2.0)
            while p.poll() is None and not self._stop.is_set():
                try:
                    chunk = conn.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                on_chunk(chunk)
        except OSError:
            pass
        finally:
            if conn:
                conn.close()
            srv.close()

    def _bitrate_loop(self, p):
        prev, t0 = 0, time.time()
        while p.poll() is None and not self._stop.is_set():
            time.sleep(1.0)
            now, cur = time.time(), self._tap_bytes
            self.on_stats({"src": "mux", "kbps": (cur - prev) * 8 / 1000 / (now - t0)})
            prev, t0 = cur, now

    @staticmethod
    def _peak_db(raw):
        x = np.frombuffer(raw, dtype=np.int16).astype(np.int32)
        peak = int(np.abs(x).max())
        return 20.0 * np.log10(max(peak, 1) / 32768.0)