import math
from ui.stream_editor import StreamEditor

from PySide6.QtWidgets import QSizePolicy
from ui.stats_window import StatsWindow
from ui.sysmon import SysMonBar

from PySide6.QtWidgets import QGridLayout, QMainWindow, QWidget

from ui.alarm_log import AlarmLogWindow
from ui.tile import Tile
from PySide6.QtCore import Signal


class MainWindow(QMainWindow):
    channels_sig = Signal(object, str)

    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.tiles = {}
        self.setWindowTitle(f"Broadcast Multiview ({monitor.decoder})")
        self.setStyleSheet("background:#0d0d0d; color:#e0e0e0;")

        central = QWidget()
        self.grid = QGridLayout(central)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setSpacing(2)
        self.setCentralWidget(central)

        self.alarm_log = AlarmLogWindow(monitor.bus, self)
        self.editor = StreamEditor(monitor, self)
        self.stats_win = StatsWindow(monitor, self)
        tb = self.addToolBar("main")
        tb.setMovable(False)
        tb.addAction("⚠ Журнал алярмів").triggered.connect(self.alarm_log.toggle)
        tb.addAction("⚙ Потоки").triggered.connect(self.editor.toggle)
        tb.addAction("📊 Статистика").triggered.connect(self.stats_win.toggle)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)                 # відсуває панель вправо
        self.sysmon = SysMonBar()
        tb.addWidget(self.sysmon)
        

        self.channels_sig.connect(self._on_channel_event)
        monitor.bus.subscribe("channels", None,
                              lambda cid, ev: self.channels_sig.emit(cid, ev))
        for cid in monitor.channel_ids():
            self.tiles[cid] = Tile(monitor, cid)
        self._relayout()

    def _on_channel_event(self, cid, ev):
        if ev == "added" and cid not in self.tiles:
            self.tiles[cid] = Tile(self.monitor, cid)
        elif ev == "removed":
            tile = self.tiles.pop(cid, None)
            if tile:
                self.grid.removeWidget(tile)
                tile.setParent(None)
                tile.deleteLater()
        elif ev == "updated" and cid in self.tiles:
            self.tiles[cid].set_name(self.monitor.get_state(cid).name)
        self._relayout()

    def _relayout(self):
        for t in self.tiles.values():
            self.grid.removeWidget(t)
        for r in range(self.grid.rowCount()):
            self.grid.setRowStretch(r, 0)
        for c in range(self.grid.columnCount()):
            self.grid.setColumnStretch(c, 0)
        ids = [c for c in self.monitor.channel_ids() if c in self.tiles]
        cols = min(5, max(1, math.ceil(math.sqrt(len(ids)))))
        for i, cid in enumerate(ids):
            self.grid.addWidget(self.tiles[cid], i // cols, i % cols)
            self.tiles[cid].show()
        for r in range((len(ids) + cols - 1) // cols):
            self.grid.setRowStretch(r, 1)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)