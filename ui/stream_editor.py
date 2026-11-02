import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

from core.config import DEFAULT_THRESHOLDS

KNOWN = ("udp", "srt", "rtmp", "rtmps", "http", "https", "rtsp")
HINT = {
    "min_kbps": "Бітрейт нижче: ALARM",
    "warn_kbps": "Бітрейт нижче: WARN (0 = вимкнено)",
    "cc_warn_per_min": "CC за 60 с: WARN",
    "cc_alarm_per_min": "CC за 60 с: ALARM",
    "silence_db": "Рівень тиші, dBFS",
    "silence_s": "Тиша довше, с (0 = вимкнено)",
    "black_s": "Чорний кадр довше, с (0 = вимкнено)",
    "freeze_s": "Завмирання довше, с (0 = вимкнено)",
    "raise_after_s": "Підтвердження тривоги, с",
}


def _num(text):
    v = float(text.replace(",", "."))
    return int(v) if v.is_integer() else v


class StreamEditor(QWidget):
    def __init__(self, monitor, parent=None):
        super().__init__(parent, Qt.Window)
        self.m = monitor
        self.setWindowTitle("Редактор потоків")
        self.resize(900, 560)
        self.setStyleSheet("background:#0d0d0d; color:#e0e0e0;")

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_select)
        self.name = QLineEdit()
        self.url = QLineEdit()
        self.dec = QComboBox()
        self.dec.addItems(["(за замовчуванням)", "auto", "cuda", "cpu", "cuvid"])
        self.qual = QComboBox()
        self.qual.addItems(["(default)", "full", "smooth", "light"])
        
        form = QFormLayout()
        form.addRow("Назва:", self.name)
        form.addRow("URL:", self.url)
        form.addRow("Декодер:", self.dec)
        form.addRow("Якість:", self.qual)
        self.th_edits = {}
        for k in HINT:
            e = QLineEdit()
            e.setPlaceholderText(f"глобально: {self.m.defaults[k]}")
            e.setToolTip(HINT[k])
            self.th_edits[k] = e
            form.addRow(f"{k}:", e)

        btn_save = QPushButton("💾 Зберегти канал")
        btn_save.clicked.connect(self._save_item)
        btn_add = QPushButton("+ Додати")
        btn_add.clicked.connect(self._add)
        btn_del = QPushButton("− Видалити")
        btn_del.clicked.connect(self._delete)
        btn_up = QPushButton("↑")
        btn_up.clicked.connect(lambda: self._move(-1))
        btn_dn = QPushButton("↓")
        btn_dn.clicked.connect(lambda: self._move(1))
        btn_open = QPushButton("📂 Відкрити плейлист…")
        btn_open.clicked.connect(self._open_file)
        btn_savef = QPushButton("💾 Зберегти плейлист…")
        btn_savef.clicked.connect(self._save_file)

        row1 = QHBoxLayout()
        for b in (btn_add, btn_del, btn_up, btn_dn):
            row1.addWidget(b)
        left = QVBoxLayout()
        left.addWidget(self.list, 1)
        left.addLayout(row1)
        left.addWidget(btn_open)
        left.addWidget(btn_savef)

        self.status = QLabel("")
        self.status.setStyleSheet("color:#888;")
        right = QVBoxLayout()
        right.addLayout(form)
        right.addWidget(btn_save)
        right.addWidget(self.status)
        right.addStretch(1)

        lay = QHBoxLayout(self)
        lay.addLayout(left, 2)
        lay.addLayout(right, 3)
        self._refresh()

    # ── допоміжне ────────────────────────────────────────────────────────────
    def _cid(self):
        r = self.list.currentRow()
        ids = self.m.channel_ids()
        return ids[r] if 0 <= r < len(ids) else None

    def _refresh(self, select=None):
        self.list.blockSignals(True)
        self.list.clear()
        ids = self.m.channel_ids()
        for i, cid in enumerate(ids):
            st = self.m.get_state(cid)
            proto = st.url.split("://")[0].upper() if "://" in st.url else "FILE"
            self.list.addItem(f"{i + 1:>2}. [{proto}] {st.name}")
        self.list.blockSignals(False)
        if ids:
            self.list.setCurrentRow(ids.index(select) if select in ids else 0)
            self._on_select(self.list.currentRow())

    def _on_select(self, _):
        cid = self._cid()
        if cid is None:
            return
        cfg = self.m.channels[cid].cfg
        self.name.setText(cfg.get("name", ""))
        self.url.setText(cfg.get("url", ""))
        d = cfg.get("decoder")
        self.dec.setCurrentIndex(max(0, self.dec.findText(d)) if d else 0)
        qv = cfg.get("quality")
        self.qual.setCurrentIndex(max(0,self.qual.findText(qv)) if qv else 0)
        for k, e in self.th_edits.items():
            e.setText(str(cfg[k]) if k in cfg else "")

    def _say(self, text):
        self.status.setText(text)

    # ── дії ──────────────────────────────────────────────────────────────────
    def _save_item(self):
        cid = self._cid()
        if cid is None:
            return
        url = self.url.text().strip()
        scheme = url.split("://", 1)[0].lower() if "://" in url else ""
        if scheme and scheme not in KNOWN:
            QMessageBox.warning(self, "Протокол",
                                f"«{scheme}://» не впізнано, збережу як є.")
        cfg = {"name": self.name.text().strip(), "url": url}
        if self.dec.currentIndex() > 0:
            cfg["decoder"] = self.dec.currentText()
        if self.qual.currentIndex()>0:
            cfg["quality"] = self.qual.currentText()
        for k, e in self.th_edits.items():
            t = e.text().strip()
            if not t:
                continue
            try:
                cfg[k] = _num(t)
            except ValueError:
                QMessageBox.warning(self, "Помилка", f"{k}: «{t}» не число.")
                return
        self.m.update_channel(cid, cfg)
        self._refresh(cid)
        self._say(f"✔ Збережено: {cfg['name']}")

    def _add(self):
        n = len(self.m.channel_ids()) + 1
        cid = self.m.add_channel({"name": f"Канал {n}",
                                  "url": "udp://@239.255.10.1:5000"})
        self._refresh(cid)

    def _delete(self):
        cid = self._cid()
        if cid is None:
            return
        name = self.m.get_state(cid).name
        if QMessageBox.question(self, "Видалити", f"Видалити «{name}»?") \
                != QMessageBox.Yes:
            return
        self.m.remove_channel(cid)
        self._refresh()
        self._say(f"🗑 Видалено «{name}»")

    def _move(self, delta):
        cid = self._cid()
        if cid is not None:
            self.m.move_channel(cid, delta)
            self._refresh(cid)

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Відкрити плейлист", "", "JSON (*.json);;Усі файли (*.*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            streams = data if isinstance(data, list) else data.get("streams", [])
            if not streams:
                raise ValueError("файл не містить потоків")
        except Exception as e:
            QMessageBox.critical(self, "Помилка", str(e))
            return
        if QMessageBox.question(
                self, "Відкрити",
                f"Замінити поточні канали на {len(streams)} з файлу?") != QMessageBox.Yes:
            return
        self.m.replace_all(streams)
        self._refresh()
        self._say(f"✔ Відкрито {len(streams)} потоків")

    def _save_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Зберегти плейлист", "playlist.json", "JSON (*.json)")
        if not path:
            return
        streams = [self.m.channels[c].cfg for c in self.m.channel_ids()]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(streams, f, ensure_ascii=False, indent=2)
        self._say(f"✔ Збережено: {path}")

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self._refresh()
            self.show()
            self.raise_()