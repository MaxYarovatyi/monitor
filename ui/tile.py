from PySide6.QtCore import Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFrame, QVBoxLayout

from ingest.pipeline import TILE_H, TILE_W
from ui.video_view import VideoView

SHORT = {"no_signal": "NO SIGNAL", "low_bitrate": "БІТРЕЙТ", "cc_errors": "CC",
         "silence": "ТИША", "black": "BLACK", "freeze": "FREEZE"}
LV = {"WARN": 1, "ALARM": 2}
STATS_COLOR = {2: "#ff5c5c", 1: "#ffc247", 0: "#7fd0ff"}


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
        self.m = monitor
        state = monitor.get_state(cid)
        self._down = state.down
        self._alarms = dict(monitor.active_alarms(cid))
        self._name = state.name
        self._q = monitor.current_quality(cid)
        self._latest, self._pending = None, False

        self.video = VideoView()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.video)

        self.video.set_status(state.status)
        self._render_title()
        self._render_alarms()
        self._overlay("NO SIGNAL" if self._down else "CONNECTING…",
                      "#ff3333" if self._down else "#888888")

        self.frame_sig.connect(self._show_frame)
        self.quality_sig.connect(self._set_quality)
        self.status_sig.connect(self._on_status)
        self.audio_sig.connect(self.video.set_db)
        self.metrics_sig.connect(self._on_metrics)
        self.alarm_sig.connect(self._on_alarm)
        bus = monitor.bus
        bus.subscribe("frame", cid, self._on_frame_bus)
        bus.subscribe("quality", cid, lambda c, q: self.quality_sig.emit(q))
        bus.subscribe("status", cid, lambda c, s: self.status_sig.emit(s))
        bus.subscribe("audio", cid, lambda c, db: self.audio_sig.emit(db))
        bus.subscribe("metrics", cid, lambda c, m: self.metrics_sig.emit(m))
        bus.subscribe("alarm", cid, lambda c, ev: self.alarm_sig.emit(ev))

    def _render_title(self):
        self.video.set_title(self._name if self._q == "full"
                             else f"{self._name} ·{self._q}")

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
        self.video.set_alarms(" ".join(SHORT[k] for k in self._alarms), self._worst())

    def _on_alarm(self, ev):
        if ev["level"] == "OK":
            self._alarms.pop(ev["key"], None)
        else:
            self._alarms[ev["key"]] = ev["level"]
        self._render_alarms()

    def _overlay(self, text, color):
        self.video.set_text(text, color)

    def _on_status(self, text):
        self.video.set_status(text)
        if text.startswith("NO_SIGNAL"):
            self._down = True
            self.video.reset_vu()
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
        self.video.set_frame(img)

    def _on_metrics(self, m):
        w = self._worst(("low_bitrate", "cc_errors"))
        text = f"{m['kbps']:.0f} kbps"
        if m["src"] == "wire":
            text += f"  null {m['null_pct']:.0f}%  CC {m['cc_total']}"
        if m["reconnects"]:
            text += f"  ↺{m['reconnects']}"
        self.video.set_stats(text, STATS_COLOR[w])