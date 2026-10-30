import sqlite3
import time
from datetime import datetime

KEYS = ("no_signal", "low_bitrate", "cc_errors", "silence", "black", "freeze")
PERIODS = {"1 година": 3600, "24 години": 86400, "7 днів": 7 * 86400, "30 днів": 30*86400}

def compute(db_path, seconds):
    now = time.time()
    since = now - seconds
    con = sqlite3.connect(db_path, timeout=30)
    long = seconds > 7 * 86400          # сирі дані зберігаються лише 8 днів
    try:
        first = con.execute("SELECT min(ts) FROM metrics WHERE ts >= ?",
                            (since,)).fetchone()[0]
        events = con.execute(
            "SELECT ts, channel, key, level FROM events WHERE ts >= ? ORDER BY ts",
            (since,)).fetchall()
        if long:
            fh = con.execute("SELECT min(hour_ts) FROM metrics_hourly "
                             "WHERE hour_ts >= ?", (since - 3600,)).fetchone()[0]
            first = min(x for x in (first, fh) if x is not None) \
                if (first or fh) else None
            agg = con.execute(
                "SELECT channel, sum(avg_kbps*ok_samples)/sum(ok_samples), "
                "min(min_kbps) FROM metrics_hourly "
                "WHERE hour_ts >= ? AND ok_samples > 0 GROUP BY channel",
                (since - 3600,)).fetchall()
        else:
            agg = con.execute(
                "SELECT channel, avg(kbps), min(kbps) FROM metrics "
                "WHERE ts >= ? AND status = 'OK' GROUP BY channel",
                (since,)).fetchall()
    finally:
        con.close()
    start = max(since, first) if first else since     # реально спостережуваний час
    observed = max(1.0, now - start)

    ch = {}

    def rec(name):
        return ch.setdefault(name, {
            "name": name, "inc": {k: 0 for k in KEYS}, "down_s": 0.0,
            "hours": [0] * 24, "open": {}, "avg_kbps": None, "min_kbps": None})

    for ts, name, key, level in events:
        r = rec(name)
        o = r["open"]
        if level == "OK":
            t0 = o.pop(key, None)
            if t0 is None and key == "no_signal":
                t0 = start                              # збій почався до початку періоду
            if t0 is not None and key == "no_signal":
                r["down_s"] += max(0.0, ts - t0)
        elif key not in o:                               # WARN→ALARM не рахуємо двічі
            o[key] = ts
            if key in r["inc"]:
                r["inc"][key] += 1
            r["hours"][datetime.fromtimestamp(ts).hour] += 1

    for name, avg, mn in agg:
        r = rec(name)
        r["avg_kbps"], r["min_kbps"] = avg, mn

    rows = []
    for r in ch.values():
        t0 = r["open"].get("no_signal")
        if t0 is not None:
            r["down_s"] += now - t0
        down = min(r["down_s"], observed)
        n_ns = r["inc"]["no_signal"]
        r["total"] = sum(r["inc"].values())
        r["avail"] = 100.0 * (1 - down / observed)
        r["mtbf"] = observed / n_ns if n_ns else None
        r.pop("open")
        rows.append(r)
    rows.sort(key=lambda r: (-r["total"], r["name"]))
    return {"observed": observed, "rows": rows}