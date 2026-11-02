from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout)

from ingest.pipeline import TILE_H, TILE_W
from ui.vu import VuMeter
from ui.video_view import VideoView


SHORT = {"no_signal": "NO SIGNAL", "low_bitrate": "БІТРЕЙТ",
         "cc_errors": "CC", "silence": "ТИША","black": "BLACK", "freeze": "FREEZE"}
LV = {"WARN": 1, "ALARM": 2}
BORDER = {0: "#2a2a2a", 1: "#ffaa00", 2: "#ff3333"}


class Tile(QFrame):
    """Лише відображення: усі дані приходять з Monitor через шину подій."""
    frame_sig = Signal()
    quality_sig = Signal(str)
    status_sig = Signal(str)
    audio_sig = Signal(float)
    metrics_sig = Signal(object)
    alarm_sig = Signal(object)

    def __init__(self, monitor, cid):
        super().__init__()
        self.cid = cid
        self.setObjectName("tile")
        state = monitor.get_state(cid)
        self._down = state.down
        self._alarms = dict(monitor.active_alarms(cid))

        self.m = monitor
        self._name = state.name
        self._q = monitor.current_quality(cid)
        self._latest, self._pending = None, False

        self.title = QLabel()
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font: bold 11pt Consolas;")
        self._render_title()
        
        # self.video = QLabel()
        # self.video.setAlignment(Qt.AlignCenter)
        # self.video.setStyleSheet("background:black;")
        # self.video.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        # self.video.setMinimumSize(80, 45)
        self.video = VideoView()
        self.vu = VuMeter()
        mid = QHBoxLayout()
        mid.setSpacing(2)
        mid.addWidget(self.video, 1)
        mid.addWidget(self.vu)

        self.status = QLabel(state.status)
        self.status.setStyleSheet("font: 8pt Consolas; color:#888;")
        self.alarm_lbl = QLabel("")
        self.stats = QLabel("— kbps")

        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.alarm_lbl)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(1)
        lay.addWidget(self.title)
        lay.addLayout(mid, 1)
        lay.addLayout(bottom)
        lay.addWidget(self.stats)

        self.frame_sig.connect(self._show_frame)
        self.status_sig.connect(self._on_status)
        self.audio_sig.connect(self.vu.set_db)
        self.metrics_sig.connect(self._on_metrics)
        self.alarm_sig.connect(self._on_alarm)
        bus = monitor.bus
        bus.subscribe("frame", cid, self._on_frame_bus)
        bus.subscribe("quality", cid, lambda c, q: self.quality_sig.emit(q))
        bus.subscribe("status", cid, lambda c, s: self.status_sig.emit(s))
        bus.subscribe("audio", cid, lambda c, db: self.audio_sig.emit(db))
        bus.subscribe("metrics", cid, lambda c, m: self.metrics_sig.emit(m))
        bus.subscribe("alarm", cid, lambda c, ev: self.alarm_sig.emit(ev))
        self.quality_sig.connect(self._set_quality)
        self._render_alarms()
        self._overlay("NO SIGNAL" if self._down else "CONNECTING", "#ff3333" if self._down else "#888888")

    def _render_title(self):
        self.title.setText(self._name if self._q == "full"
                           else f"{self._name}  ·{self._q}")


    def set_name(self, name):
        self._name = name
        self._render_title()

    def _set_quality(self, q):
        self._q = q
        self._render_title()

    def mouseDoubleClickEvent(self, e):
        self.m.toggle_boost(self.cid)

    def _on_frame_bus(self, cid, d):
        self._latest = d                  # у черзі Qt не більше одного сигналу на плитку
        if not self._pending:
            self._pending = True
            self.frame_sig.emit()

    def _worst(self, keys=None):
        return max((LV[v] for k, v in self._alarms.items()
                    if keys is None or k in keys), default=0)

    def _render_alarms(self):
        w = self._worst()
        self.setStyleSheet(f"#tile{{background:#141414; border:2px solid {BORDER[w]};}}"
                           "QLabel{color:#e0e0e0;}")
        self.alarm_lbl.setText(" ".join(SHORT[k] for k in self._alarms))
        self.alarm_lbl.setStyleSheet(
            f"font: bold 8pt Consolas; color:{'#ff3333' if w == 2 else '#ffaa00'};")

    def _on_alarm(self, ev):
        if ev["level"] == "OK":
            self._alarms.pop(ev["key"], None)
        else:
            self._alarms[ev["key"]] = ev["level"]
        self._render_alarms()

    def _overlay(self, text, color):
        self.video.set_text(text,color)
        # self.video.clear()
        # self.video.setText(text)
        # self.video.setStyleSheet(
        #     f"background:black; color:{color}; font: bold 14pt Consolas;")

    def _on_status(self, text):
        self.status.setText(text)
        if text.startswith("NO_SIGNAL"):
            self._down = True
            self.vu.reset()
            self._overlay("NO SIGNAL", "#ff3333")
        elif text.startswith("OK"):
            self._down = False
        elif text.startswith("CONNECTING") and not self._down:
            self._overlay("CONNECTING…", "#888888")

    def _show_frame(self):
        self._pending = False
        data = self._latest
        if self._down or data is None:
            return
        img = QImage(data, TILE_W, TILE_H, TILE_W * 3, QImage.Format_RGB888).copy()
        # pix = QPixmap.fromImage(img).scaled(
        #     self.video.size(), Qt.KeepAspectRatio, Qt.FastTransformation)
        # self.video.setPixmap(pix)
        self.video.set_frame(img)

    def _on_metrics(self, m):
        w = self._worst(("low_bitrate", "cc_errors"))
        color = {2: "#ff3333", 1: "#ffaa00", 0: "#00aaff"}[w]
        text = f"{m['kbps']:6.0f} kbps"
        if m["src"] == "wire":
            text += f"  null {m['null_pct']:.0f}%  CC {m['cc_total']}"
        if m["reconnects"]:
            text += f"  ↺{m['reconnects']}"
        self.stats.setText(text)
        self.stats.setStyleSheet(f"font: 8pt Consolas; color:{color};")