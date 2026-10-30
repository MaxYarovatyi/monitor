import time

GROUP_S = 15

TEXT_RULES = (
    ("connection refused", "джерело відхиляє з'єднання: порт закрито або сервіс не запущено"),
    ("timed out", "таймаут: джерело не відповідає"),
    ("404", "ресурс не знайдено (404): змінився шлях або ключ потоку"),
    ("401", "відмова в доступі (401)"),
    ("403", "відмова в доступі (403)"),
    ("setup failure", "SRT: не вдалося встановити з'єднання"),
    ("rejected", "з'єднання відхилено джерелом"),
    ("pps", "потік без ключового кадру або пошкоджений"),
    ("invalid data", "пошкоджені дані в потоці"),
    ("немає кадрів", "з'єднання є, але дані не надходять: джерело мовчить"),
)


class Classifier:
    """Причина збою за ознаками: правила, а не модель."""

    def __init__(self):
        self._ns = {}                    # cid -> час останнього NO_SIGNAL

    def classify(self, cid, key, s):
        if key == "no_signal":
            return self._no_signal(cid, s)
        if key == "low_bitrate":
            return self._low_bitrate(s)
        return ""

    def _no_signal(self, cid, s):
        now = time.time()
        self._ns = {c: t for c, t in self._ns.items()
                    if now - t < GROUP_S and c != cid}
        others = len(self._ns)
        self._ns[cid] = now
        single = self._single(s)
        if others >= 2:
            return (f"груповий збій ({others + 1} каналів за {GROUP_S} с), "
                    f"ймовірно спільна ділянка мережі або джерело; окремо: {single}")
        return single

    @staticmethod
    def _single(s):
        if s["src"] == "wire":           # UDP-мультикаст: бачимо пакети в мережі
            if s["kbps"] < 50:
                return "пакетів немає: обрив джерела або мережі"
            if s["null_pct"] > 90:
                return "у потоці лише null-пакети: кодер не віддає дані"
            if s["cc_min"] > 0:
                return "пакети йдуть із втратами (CC): мережа втрачає пакети"
            return ("пакети йдуть, кадрів немає: пошкоджений чи зашифрований "
                    "потік, змінився кодек або PID")
        err = s["status"].lower()
        for needle, cause in TEXT_RULES:
            if needle in err:
                return cause
        return "причину не визначено"

    @staticmethod
    def _low_bitrate(s):
        if s["src"] == "wire" and s["cc_min"] > 0:
            return "падіння бітрейту разом із втратами пакетів: проблема в мережі"
        if s["kbps"] < 50:
            return "потік майже зупинився"
        return "бітрейт знизився без втрат пакетів: кодер або джерело"