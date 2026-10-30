import threading
import time
from collections import deque


class ChannelState:
    """Поточний стан каналу. Пишуть робочі потоки, читає Monitor під lock."""

    def __init__(self, cid, name, url, th):
        self.cid, self.name, self.url, self.th = cid, name, url, th
        self.lock = threading.Lock()
        self.status = "INIT"
        self.reconnects = 0
        self.mux_kbps = 0.0
        self.wire, self.wire_ts = None, 0.0
        self.cc_events = deque()          # (ts, кількість) за останні 60 с
        self.cc_total = 0
        self.audio_db, self.audio_ts = None, 0.0
        self.quiet_since = None
        self.down = False
        self.black_since = None
        self.freeze_since = None
        self.vid_mean = None

    def on_status(self, text):
        with self.lock:
            self.status = text
            if text.startswith("NO_SIGNAL"):
                self.down = True
                self.reconnects += 1
                self.mux_kbps = 0.0
                self.audio_db = None
                self.quiet_since = None
                self.black_since = None
                self.freeze_since = None
            elif text.startswith("OK"):
                self.down = False

    def on_stats(self, d):
        now = time.time()
        with self.lock:
            if d["src"] == "wire":
                self.wire, self.wire_ts = d, now
                self.cc_total = d["cc_total"]
                if d["cc_recent"]:
                    self.cc_events.append((now, d["cc_recent"]))
            else:
                self.mux_kbps = d["kbps"]

    def on_audio(self, db):
        now = time.time()
        with self.lock:
            self.audio_db, self.audio_ts = db, now
            if db < self.th["silence_db"]:
                if self.quiet_since is None:
                    self.quiet_since = now
            else:
                self.quiet_since = None

    def snapshot(self):
        now = time.time()
        with self.lock:
            w = self.wire if self.wire and now - self.wire_ts < 3 else None
            while self.cc_events and now - self.cc_events[0][0] > 60:
                self.cc_events.popleft()
            audio_ok = self.audio_db is not None and now - self.audio_ts < 2
            kind = self.status.split(":")[0].split(" ")[0]
            if self.down and kind in ("CONNECTING", "NO_SIGNAL"):
                kind = "NO_SIGNAL"
            return {
                "ts": now,
                "status": self.status,
                "kind": kind,                        # INIT | CONNECTING | OK | NO_SIGNAL
                "src": "wire" if w else "mux",
                "kbps": w["kbps"] if w else self.mux_kbps,
                "has_rate": bool(w) or kind in ("OK", "NO_SIGNAL"),
                "null_pct": w["null_pct"] if w else 0.0,
                "cc_total": self.cc_total,
                "cc_min": sum(n for _, n in self.cc_events),
                "audio_db": self.audio_db if audio_ok else None,
                "silent_for": (now - self.quiet_since
                               if audio_ok and self.quiet_since else 0.0),
                "reconnects": self.reconnects,
                "black_for": now - self.black_since if self.black_since else 0.0,
                "freeze_for": now - self.freeze_since if self.freeze_since else 0.0,
                "vid_mean": self.vid_mean
            }
    
    def on_video(self, mean, std, diff):
        now = time.time()
        with self.lock:
            self.vid_mean = mean
            black = mean < self.th["black_level"] and std < self.th["black_std"]
            if black:
                if self.black_since is None:
                    self.black_since = now
            else:
                self.black_since = None
            frozen = diff is not None and diff < self.th["freeze_diff"]
            if frozen:
                if self.freeze_since is None:
                    self.freeze_since = now
            else:
                self.freeze_since = None