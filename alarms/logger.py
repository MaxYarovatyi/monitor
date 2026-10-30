import threading
from datetime import datetime

from core.config import ROOT

LOGS_DIR = ROOT / "alarm_logs"

def format_event(ev, full = False):
    fmt = "%Y-%m-%d %H:%M:%S" if full else "%H:%M:%S"
    ts = datetime.fromtimestamp(ev["ts"]).strftime(fmt)
    return f"[{ts}] [{ev['level']:<5}] [{ev['channel']}] {ev['message']}"

class FileAlarmLogger:
    def __init__(self, bus):
        self._lock = threading.Lock()
        LOGS_DIR.mkdir(exist_ok=True)
        bus.subscribe("alarm", None, self._on_alarm)

    def _on_alarm(self, cid, ev):
        path = LOGS_DIR / (datetime.now().strftime("%d-%m-%Y") + ".log")
        try:
            with self._lock, open(path, "a", encoding="utf-8") as f:
                f.write(format_event(ev,full=True) + "\n")
        except Exception as e:
            print(f"[alarm_log] {e}")