from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

PILL = QColor(0, 0, 0, 150)          # підкладка під текстом; збільште 150 для контрасту
ALARM_COLOR = {1: "#ffc247", 2: "#ff5c5c"}
VU_W, FLOOR = 10, -60.0


class VideoView(QWidget):
    """Кадр на весь віджет; назва, тривоги, статус, статистика, VU і рамка поверх."""

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setMinimumSize(80, 45)
        self._img = None
        self._msg, self._msg_color = "", "#888888"
        self.title = self.status = self.stats = self.alarm_text = ""
        self.stats_color, self.alarm_level = "#7fd0ff", 0
        self._lvl = self._peak = 0.0
        self._hold = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ── дані ────────────────────────────────────────────────────────────────
    def set_frame(self, img):
        self._img, self._msg = img, ""
        self.update()

    def set_text(self, text, color):
        self._img, self._msg, self._msg_color = None, text, color
        self.update()

    def set_title(self, t):
        self.title = t
        self.update()

    def set_status(self, t):
        self.status = t
        self.update()

    def set_stats(self, t, color):
        self.stats, self.stats_color = t, color
        self.update()

    def set_alarms(self, text, level):
        self.alarm_text, self.alarm_level = text, level
        self.update()

    # ── VU ──────────────────────────────────────────────────────────────────
    def set_db(self, db):
        raw = max(0.0, min(1.0, (db - FLOOR) / -FLOOR))
        self._lvl = max(self._lvl, raw)
        if not self._timer.isActive():
            self._timer.start(40)

    def reset_vu(self):
        self._lvl = self._peak = 0.0
        self._hold = 0
        self._timer.stop()
        self.update(self._vu_rect())

    def _tick(self):
        self._lvl = max(0.0, self._lvl - 0.02)
        if self._lvl >= self._peak:
            self._peak, self._hold = self._lvl, 25
        elif self._hold > 0:
            self._hold -= 1
        else:
            self._peak = max(0.0, self._peak - 0.01)
        self.update(self._vu_rect())
        if self._lvl <= 0 and self._peak <= 0:
            self._timer.stop()

    # ── геометрія ───────────────────────────────────────────────────────────
    def _fpx(self):
        return max(10, min(15, self.height() // 13))

    def _picture_rect(self):
        w, h = self.width(), self.height()
        if self._img is None:
            return QRect(0, 0, w, h)
        s = min(w / self._img.width(), h / self._img.height())
        tw, th = int(self._img.width() * s), int(self._img.height() * s)
        return QRect((w - tw) // 2, (h - th) // 2, tw, th)

    def _vu_rect(self):
        pr, fpx = self._picture_rect(), self._fpx()
        top = pr.top() + 2 * fpx + 12
        bottom = pr.bottom() - 2 * fpx - 12
        return QRect(pr.right() - VU_W - 4, top, VU_W, max(10, bottom - top))

    # ── малювання ───────────────────────────────────────────────────────────
    def _pill(self, p, x, y, text, color, font, right=False, max_w=0):
        fm = QFontMetrics(font)
        if max_w:
            text = fm.elidedText(text, Qt.ElideRight, max(10, max_w - 8))
        pw, ph = fm.horizontalAdvance(text) + 8, fm.height() + 2
        if right:
            x -= pw
        p.setPen(Qt.NoPen)
        p.setBrush(PILL)
        p.drawRoundedRect(x, y, pw, ph, 3, 3)
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(x + 4, y + 1 + fm.ascent(), text)
        return pw, ph

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        pr = self._picture_rect()
        if self._img is not None:
            p.drawImage(pr, self._img)
        elif self._msg:
            f = QFont("Consolas")
            f.setPixelSize(max(12, self.height() // 7))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(self._msg_color))
            p.drawText(self.rect(), Qt.AlignCenter, self._msg)

        fpx, m = self._fpx(), 4
        f, fb = QFont("Consolas"), QFont("Consolas")
        f.setPixelSize(fpx)
        fb.setPixelSize(fpx)
        fb.setBold(True)

        aw = 0
        if self.alarm_text:
            acol = ALARM_COLOR.get(self.alarm_level, "#ffc247")
            aw, _ = self._pill(p, pr.right() - m, pr.top() + m, self.alarm_text,
                               acol, fb, right=True)
        if self.title:
            self._pill(p, pr.left() + m, pr.top() + m, self.title, "#ffffff", fb,
                       max_w=pr.width() - aw - 3 * m)

        yb = pr.bottom() - QFontMetrics(f).height() - 2 - m
        sw = 0
        if self.stats:
            sw, _ = self._pill(p, pr.left() + m, yb, self.stats, self.stats_color, f)
        if self.status:
            self._pill(p, pr.right() - m, yb, self.status, "#d8d8d8", f, right=True,
                       max_w=pr.width() - sw - 3 * m)

        r = self._vu_rect()                                  # VU
        p.fillRect(r, PILL)
        fill = int(self._lvl * r.height())
        for lo, hi, col in ((0.0, 0.6, "#00cc44"), (0.6, 0.85, "#ffaa00"),
                            (0.85, 1.0, "#ff3333")):
            bot, top = int(lo * r.height()), min(fill, int(hi * r.height()))
            if top > bot:
                p.fillRect(r.x() + 1, r.bottom() + 1 - top, r.width() - 2,
                           top - bot, QColor(col))
        if self._peak > 0:
            py = r.bottom() - int(self._peak * r.height())
            p.fillRect(r.x(), max(r.top(), py - 1), r.width(), 2, Qt.white)

        if self.alarm_level:                                 # рамка тривоги
            p.setPen(QPen(QColor(ALARM_COLOR[self.alarm_level]), 3))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))