import html
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)

from alarms.logger import LOGS_DIR, format_event

COLORS = {"ALARM": "#ff3333", "WARN": "#ffaa00", "OK": "#00cc44"}


class AlarmLogWindow(QWidget):
    event_sig = Signal(object)

    def __init__(self, bus, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Журнал алярмів")
        self.resize(640, 420)
        self.setStyleSheet("background:#0d0d0d; color:#e0e0e0;")
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet("background:#141414; font: 9pt Consolas;")
        self.text.document().setMaximumBlockCount(3000)

        btn_dir = QPushButton("Відкрити папку логів")
        btn_dir.clicked.connect(lambda: os.startfile(str(LOGS_DIR)))
        btn_clr = QPushButton("Очистити вікно")
        btn_clr.clicked.connect(self.text.clear)
        row = QHBoxLayout()
        row.addWidget(btn_dir)
        row.addStretch(1)
        row.addWidget(btn_clr)

        lay = QVBoxLayout(self)
        lay.addWidget(self.text, 1)
        lay.addLayout(row)

        self.event_sig.connect(self._add)
        bus.subscribe("alarm", None, lambda cid, ev: self.event_sig.emit(ev))

    def _add(self, ev):
        color = COLORS.get(ev["level"], "#e0e0e0")
        self.text.append(
            f'<span style="color:{color}">{html.escape(format_event(ev))}</span>')

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()