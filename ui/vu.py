from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QTimer

class VuMeter(QWidget):
    FLOOR = -60.0
    
    def __init__(self):
        super().__init__()
        self.setFixedWidth(12)
        self.reset()
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(40)
        
    def reset(self):
        self._lvl = self._peak = 0.0
        self._hold = 0
        self.update()
        
    def set_db(self, db):
        raw = max(0.0, min(1.0, (db-self.FLOOR)/ -self.FLOOR))
        self._lvl = max(self._lvl, raw)
        
    def _tick(self):                           # плавний спад за таймером
        self._lvl = max(0.0, self._lvl - 0.02)
        if self._lvl >= self._peak:
            self._peak, self._hold = self._lvl, 25   # ~1 с
        elif self._hold > 0:
            self._hold -= 1
        else:
            self._peak = max(0.0, self._peak - 0.01)
        self.update()
               
    def paintEvent(self, _):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#0a0a0a"))
        fill = int(self._lvl * h)
        for lo, hi, col in ((0.0, 0.6, "#00cc44"), (0.6,0.85, "#ffaa00"), (0.85, 1.0, "#ff3333")):
            bot, top = int(lo*h), min(fill, int(hi*h))
            if top > bot:
                p.fillRect(1, h-top, w - 2, top - bot, QColor(col))
        py = h - int(self._peak * h)
        p.fillRect(0, max(0, py - 2), w, 2, QColor("#ffffff"))