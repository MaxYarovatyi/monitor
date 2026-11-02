from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget


class VideoView(QWidget):
    def __init__(self):
        super().__init__()
        self._img = None
        self._text, self._color = "", "#888888"
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setMinimumSize(80, 45)

    def set_frame(self, img):
        self._img, self._text = img, ""
        self.update()

    def set_text(self, text, color):
        self._img, self._text, self._color = None, text, color
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        if self._img is not None:
            w, h = self.width(), self.height()
            s = min(w / self._img.width(), h / self._img.height())
            tw, th = int(self._img.width() * s), int(self._img.height() * s)
            p.drawImage(QRect((w - tw) // 2, (h - th) // 2, tw, th), self._img)
        elif self._text:
            p.setPen(QColor(self._color))
            p.setFont(QFont("Consolas", 14, QFont.Bold))
            p.drawText(self.rect(), Qt.AlignCenter, self._text)