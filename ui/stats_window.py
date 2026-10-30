import csv
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from analytics.stats import KEYS, PERIODS, compute

HEAD = ["Канал", "Інцидентів", "NO SIGNAL", "Бітрейт", "CC", "Тиша", "Чорний",
        "Freeze", "Простій", "Доступн. %", "MTBF", "Сер. kbps", "Мін. kbps"]
TABLE_CSS = ("QTableWidget{background:#141414; gridline-color:#2a2a2a;"
             " font:9pt Consolas;}"
             "QHeaderView::section{background:#1c1c1c; color:#e0e0e0;"
             " border:1px solid #2a2a2a; padding:3px;}")


def fmt_dur(s):
    s = int(s)
    if s < 60:
        return f"{s} с"
    if s < 3600:
        return f"{s // 60} хв {s % 60:02d} с"
    return f"{s // 3600} г {s % 3600 // 60:02d} хв"


class Num(QTableWidgetItem):
    """Елемент таблиці з числовим сортуванням (None передавати як -1)."""
    def __init__(self, value, text):
        super().__init__(text)
        self.v = value
        self.setFlags(self.flags() & ~Qt.ItemIsEditable)

    def __lt__(self, other):
        try:
            return self.v < other.v
        except (AttributeError, TypeError):
            return False


def _table():
    t = QTableWidget()
    t.setStyleSheet(TABLE_CSS)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    return t


class StatsWindow(QWidget):
    done_sig = Signal(object)

    def __init__(self, monitor, parent=None):
        super().__init__(parent, Qt.Window)
        self.m = monitor
        self._busy = False
        self._data = None
        self.setWindowTitle("Статистика")
        self.resize(1100, 560)
        self.setStyleSheet("background:#0d0d0d; color:#e0e0e0;")

        self.period = QComboBox()
        self.period.addItems(list(PERIODS))
        self.period.setCurrentIndex(1)
        self.period.currentIndexChanged.connect(lambda _: self.refresh())
        btn_ref = QPushButton("↻ Оновити")
        btn_ref.clicked.connect(self.refresh)
        btn_csv = QPushButton("Експорт CSV…")
        btn_csv.clicked.connect(self._export)
        self.info = QLabel("")
        self.info.setStyleSheet("color:#888;")
        top = QHBoxLayout()
        top.addWidget(QLabel("Період:"))
        top.addWidget(self.period)
        top.addWidget(btn_ref)
        top.addWidget(btn_csv)
        top.addWidget(self.info, 1)

        self.summary = _table()
        self.summary.setColumnCount(len(HEAD))
        self.summary.setHorizontalHeaderLabels(HEAD)
        self.heat = _table()
        self.heat.setColumnCount(24)
        self.heat.setHorizontalHeaderLabels([f"{h:02d}" for h in range(24)])
        self.heat.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        tabs = QTabWidget()
        tabs.addTab(self.summary, "Підсумок")
        tabs.addTab(self.heat, "Теплова карта (за годинами доби)")
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(tabs, 1)

        self.done_sig.connect(self._fill)

    def refresh(self):
        if self._busy:
            return
        self._busy = True
        self.info.setText("Рахую…")
        secs = PERIODS[self.period.currentText()]
        path = self.m.storage.path

        def work():
            try:
                res = compute(path, secs)
            except Exception as e:
                res = {"error": str(e)}
            self.done_sig.emit(res)
        threading.Thread(target=work, daemon=True).start()

    def _fill(self, data):
        self._busy = False
        if "error" in data:
            self.info.setText(f"Помилка: {data['error']}")
            return
        self._data = data
        rows = data["rows"]
        self.info.setText(f"Спостережуваний час: {fmt_dur(data['observed'])}"
                          f"  •  каналів: {len(rows)}")

        t = self.summary
        t.setSortingEnabled(False)
        t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            cells = [Num(r["name"], r["name"]), Num(r["total"], str(r["total"]))]
            cells += [Num(r["inc"][k], str(r["inc"][k])) for k in KEYS]
            cells += [
                Num(r["down_s"], fmt_dur(r["down_s"]) if r["down_s"] else "—"),
                Num(r["avail"], f"{r['avail']:.2f}"),
                Num(r["mtbf"] if r["mtbf"] else -1,
                    fmt_dur(r["mtbf"]) if r["mtbf"] else "—"),
                Num(r["avg_kbps"] if r["avg_kbps"] is not None else -1,
                    f"{r['avg_kbps']:.0f}" if r["avg_kbps"] is not None else "—"),
                Num(r["min_kbps"] if r["min_kbps"] is not None else -1,
                    f"{r['min_kbps']:.0f}" if r["min_kbps"] is not None else "—"),
            ]
            if r["avail"] < 99.9:
                cells[9].setForeground(QColor("#ff3333" if r["avail"] < 99 else "#ffaa00"))
            for j, c in enumerate(cells):
                t.setItem(i, j, c)
        t.resizeColumnsToContents()
        t.setSortingEnabled(True)

        h = self.heat
        h.setRowCount(len(rows))
        h.setVerticalHeaderLabels([r["name"] for r in rows])
        mx = max((max(r["hours"]) for r in rows), default=0)
        for i, r in enumerate(rows):
            for hour, c in enumerate(r["hours"]):
                it = QTableWidgetItem(str(c) if c else "")
                it.setTextAlignment(Qt.AlignCenter)
                x = c / mx if mx else 0
                it.setBackground(QColor(int(20 + 215 * x), int(20 + 10 * (1 - x)), 20))
                h.setItem(i, hour, it)

    def _export(self):
        if not self._data:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Експорт статистики", "stats.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")      # крапка з комою для українського Excel
            w.writerow(HEAD)
            for r in self._data["rows"]:
                w.writerow([r["name"], r["total"], *[r["inc"][k] for k in KEYS],
                            round(r["down_s"]), f"{r['avail']:.2f}",
                            round(r["mtbf"]) if r["mtbf"] else "",
                            round(r["avg_kbps"]) if r["avg_kbps"] is not None else "",
                            round(r["min_kbps"]) if r["min_kbps"] is not None else ""])

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.refresh()