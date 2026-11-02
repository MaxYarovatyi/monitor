import socket
import struct
import threading
import time
from urllib.parse import parse_qs, urlsplit

import numpy as np

TS = 188

def _parse(url):
    u = urlsplit(url)
    local = parse_qs(u.query).get("localaddr", [""])[0]
    return u.hostname, u.port, local

class UdpTsAnalyzer:
    
    def __init__(self, url, on_stats):
        self.on_stats = on_stats
        self.host, self.port, self.local = _parse(url)
        try:
            first = int(self.host.split(".")[0])
            self.ok = bool(self.port) and 224 <= first <= 239
        except Exception:
            self.ok = False
        self._stop = threading.Event()
        self._last_cc = {}
        self._cc_total = 0
        
    def start(self):
        if self.ok:
            threading.Thread(target=self._run, daemon=True).start()
            
    def stop(self):
        self._stop.set()
    
    def _run(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8*1024*1024)
            s.bind(("", self.port))
            mreq = struct.pack("4s4s", socket.inet_aton(self.host), socket.inet_aton(self.local or "0.0.0.0"))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            s.settimeout(0.2)
        except OSError as e:
            print(f"[ts_analyzer {self.host}:{self.port}] {e}")
            return
        chunks, t0 = [], time.time()
        while not self._stop.is_set():
            try:
                chunks.append(s.recv(65536))
            except socket.timeout:
                pass
            now = time.time()
            if now - t0 >=1.0:
                try:
                    self.on_stats(self._process(chunks, now - t0))
                except Exception as e:
                    print(f"[ts_analyzer] {e}")
                chunks, t0 = [], now
        s.close()
    
    def _process(self, chunks, dt):
        raw = b"".join(c[: len(c) // TS*TS] for c in chunks)
        total = len(raw) // TS
        res = {"src": "wire", "kbps": total * TS * 8 / 1000 / dt,
               "null_pct": 0.0, "cc_recent": 0, "lost_recent": 0,
               "sync_err": 0, "cc_total": self._cc_total}
        if total == 0:
            return res
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, TS)
        bad = arr[:, 0] != 0x47
        res["sync_err"] = int(bad.sum())
        arr = arr[~bad]
        if len(arr) == 0:
            return res
        pids = ((arr[:, 1].astype(np.uint16) & 0x1F) << 8) | arr[:, 2]
        cc = arr[:, 3] & 0x0F
        afc = (arr[:, 3] >> 4) & 3
        null = pids == 0x1FFF
        res["null_pct"] = float(null.sum()) * 100 / len(arr)
        payload = ((afc & 1) == 1) & ~null     # CC росте лише в пакетах з корисним вмістом
        errors = lost = 0
        for pid in np.unique(pids[payload]):
            seq = cc[(pids == pid) & payload].astype(np.int16)
            prev = self._last_cc.get(int(pid))
            if prev is not None:
                seq = np.concatenate(([prev], seq))
            if len(seq) > 1:
                d = np.diff(seq) & 15              # очікуємо 1; 0 = допустимий дублікат
                miss = (d != 1) & (d != 0)
                errors += int(miss.sum())
                lost += int((d[miss] - 1).sum())
            self._last_cc[int(pid)] = int(seq[-1])
        self._cc_total += errors
        res.update(cc_recent=errors, lost_recent=lost, cc_total=self._cc_total)
        return res 