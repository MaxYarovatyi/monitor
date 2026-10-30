import time

LV = {None: 0, "WARN": 1, "ALARM": 2}
LABEL = {"no_signal": "Немає сигналу", "low_bitrate": "Бітрейт",
         "cc_errors": "Втрати пакетів (CC)", "silence": "Тиша",
         "black": "Чорний кадр", "freeze": "Завмирання кадру"}


class AlarmEngine:
    """Пороги, гістерезис і антимигання. Викликається з одного потоку (tick)."""

    def __init__(self, publish, classify = None):
        self._publish = publish
        self._classify = classify
        self._cur = {}      # (cid, key) -> "WARN" | "ALARM"
        self._pend = {}     # (cid, key) -> (рівень, к-сть тіків поспіль)

    def active(self, cid):
        return {k: lv for (c, k), lv in list(self._cur.items()) if c == cid}

    def forget(self, cid):
        for d in (self._cur, self._pend):
            for key in [k for k in list(d) if k[0] == cid]:
                d.pop(key, None)

    def update(self, cid, name, snap, th):
        want = self._evaluate(cid, snap, th)
        keys = set(want) | {k for (c, k) in list(self._cur) if c == cid}
        for key in keys:
            level, msg = want.get(key, (None, ""))
            cur = self._cur.get((cid, key))
            if LV[level] > LV[cur]:                    # підвищення: чекаємо підтвердження
                need = 1 if key == "no_signal" else max(1, int(th["raise_after_s"]))
                lvl, n = self._pend.get((cid, key), (None, 0))
                n = n + 1 if lvl == level else 1
                self._pend[(cid, key)] = (level, n)
                if n < need:
                    continue
            else:                                      # зниження або без змін: одразу
                self._pend.pop((cid, key), None)
                if level == cur:
                    continue
            self._pend.pop((cid, key), None)
            if level is None:
                self._cur.pop((cid, key), None)
                msg = f"{LABEL[key]}: відновлено"
            else:
                self._cur[(cid, key)] = level
                if self._classify and key in ("no_signal", "low_bitrate"):
                    try:
                        msg += f" — причина: {self._classify(cid, key, snap)}"
                    except Exception as e:
                        print(f"[classify] {e}")
            self._publish("alarm", cid, {
                "ts": time.time(), "cid": cid, "channel": name, "key": key,
                "level": level or "OK", "message": msg})

    def _evaluate(self, cid, s, th):
        out = {}
        if s["kind"] == "NO_SIGNAL":
            out["no_signal"] = ("ALARM", f"немає сигналу, перепідключень: {s['reconnects']}")

        if s["has_rate"]:
            lvl = self._bitrate_level(s["kbps"], th, self._cur.get((cid, "low_bitrate")))
            if lvl:
                out["low_bitrate"] = (
                    lvl, f"бітрейт {s['kbps']:.0f} kbps "
                         f"(пороги {th['min_kbps']:.0f}/{th['warn_kbps']:.0f})")

        n = s["cc_min"]
        if th["cc_alarm_per_min"] and n >= th["cc_alarm_per_min"]:
            out["cc_errors"] = ("ALARM", f"CC-помилок за 60 с: {n}")
        elif th["cc_warn_per_min"] and n >= th["cc_warn_per_min"]:
            out["cc_errors"] = ("WARN", f"CC-помилок за 60 с: {n}")

        if (th["silence_s"] > 0 and s["kind"] == "OK"
                and s["silent_for"] >= th["silence_s"]):
            out["silence"] = ("WARN", f"тиша {s['silent_for']:.0f} с")
        if th["black_s"] > 0 and s["kind"] == "OK" and s["black_for"] >= th["black_s"]:
            out["black"] = ("WARN", f"чорний кадр {s['black_for']:.0f} с")
        if th["freeze_s"] > 0 and s["kind"] == "OK" and s["freeze_for"] >= th["freeze_s"]:
            out["freeze"] = ("WARN", f"кадр завмер {s['freeze_for']:.0f} с")
        return out

    @staticmethod
    def _bitrate_level(kbps, th, prev):
        h = 1 + th["hysteresis_pct"] / 100
        lo, wn = th["min_kbps"], th["warn_kbps"]
        if kbps < lo or (prev == "ALARM" and kbps < lo * h):
            return "ALARM"
        if wn > 0 and (kbps < wn or (prev in ("WARN", "ALARM") and kbps < wn * h)):
            return "WARN"
        return None