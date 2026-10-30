import queue
import sqlite3
import threading
import time

RAW_DAYS = 8
KEEP_DAYS = 365

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS metrics(
    ts REAL, channel TEXT, src TEXT, kbps REAL, null_pct REAL,
    cc_total INTEGER, cc_min INTEGER, audio_db REAL, status TEXT, reconnects INTEGER);
CREATE INDEX IF NOT EXISTS ix_metrics ON metrics(channel, ts);
CREATE TABLE IF NOT EXISTS events(
    ts REAL, channel TEXT, key TEXT, level TEXT, message TEXT);
CREATE INDEX IF NOT EXISTS ix_metrics_ts ON metrics(ts);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS metrics_hourly(
    channel TEXT, hour_ts INTEGER, samples INTEGER, ok_samples INTEGER,
    avg_kbps REAL, min_kbps REAL, max_kbps REAL, max_cc_min INTEGER,
    reconnects INTEGER, PRIMARY KEY(channel, hour_ts));
"""


def maintenance(con):
    now = time.time()
    hi = int(now//3600)*3600
    last = con.execute("SELECT max(hour_ts) FROM metrics_hourly").fetchone()[0]
    lo = last + 3600 if last is not None else 0
    con.execute(
        "INSERT OR REPLACE INTO metrics_hourly "
        "SELECT channel, CAST(ts/3600 AS INTEGER)*3600 AS h, count(*), "
        "sum(status='OK'), avg(CASE WHEN status='OK' THEN kbps END), "
        "min(CASE WHEN status='OK' THEN kbps END), max(kbps), "
        "max(cc_min), max(reconnects) "
        "FROM metrics WHERE ts >= ? AND ts < ? GROUP BY channel, h", (lo, hi))
    con.execute("DELETE FROM metrics WHERE ts < ?", (now - RAW_DAYS * 86400,))
    con.execute("DELETE FROM events WHERE ts < ?", (now - KEEP_DAYS * 86400,))
    con.execute("DELETE FROM metrics_hourly WHERE hour_ts < ?",
                (now - KEEP_DAYS * 86400,))
    con.commit()

class Storage:
    """Один потік-письменник із чергою; запис пачками раз на ~2 с."""

    def __init__(self, path):
        self.path = str(path)
        self._q = queue.Queue(maxsize=100000)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def add_metric(self, name, s):
        self._put(("m", (s["ts"], name, s["src"], s["kbps"], s["null_pct"],
                         s["cc_total"], s["cc_min"], s["audio_db"],
                         s["kind"], s["reconnects"])))

    def add_event(self, ev):
        self._put(("e", (ev["ts"], ev["channel"], ev["key"],
                         ev["level"], ev["message"])))

    def _put(self, item):
        try:
            self._q.put_nowait(item)
        except queue.Full:
            pass                                   # краще втратити рядок, ніж зависнути

    def _run(self):
        try:
            con = sqlite3.connect(self.path)
            con.executescript(SCHEMA)
        except Exception as e:
            print(f"[db] {e}")
            return
        m, e_, last = [], [], time.time()
        
        def flush():
            nonlocal m, e_, last
            try:
                if m:
                    con.executemany("INSERT INTO metrics VALUES(?,?,?,?,?,?,?,?,?,?)", m)
                if e_:
                    con.executemany("INSERT INTO events VALUES(?,?,?,?,?)", e_)
                con.commit()
            except Exception as ex:
                print(f"[db] {ex}")
            m, e_, last = [], [], time.time()
        maint = 0.0
        while not (self._stop.is_set() and self._q.empty()):
            try:
                kind, row = self._q.get(timeout=0.5)
                (m if kind == "m" else e_).append(row)
            except queue.Empty:
                pass
            if time.time() - last >= 2.0:
                flush()
            if time.time() - maint >= 3600:
                maint = time.time()
                try:
                    maintenance(con)
                except Exception as ex:
                    print(f"[db] maintenance: {ex}")
        flush()
        con.close()