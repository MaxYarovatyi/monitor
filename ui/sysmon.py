from datetime import datetime

import psutil
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

try:
    import pynvml
    pynvml.nvmlInit()
    _H = pynvml.nvmlDeviceGetHandleByIndex(0)
except Exception:
    _H = None
    
def _color(v,warn, err):
    return "#ff3333" if v>=err else "#ffaa00" if v>= warn else "#888888"

class SysMonBar(QWidget):
    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0,0,8,0)
        lay.setSpacing(16)
        self.lbl = {}
        for k in ("clock", "cpu", "ram", "gpu", "dec"):
            l = QLabel()
            lay.addWidget(l)
            self.lbl[k] = l
        psutil.cpu_percent(None)
        self._tick()
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(1000)
    
    def _set(self, key, text, color="#888888"):
        self.lbl[key].setText(text)
        self.lbl[key].setStyleSheet(f"font: 9pt Consolas; color:{color};")
    
    def _tick(self):
        self._set("clock", datetime.now().strftime("%d.%m.%Y %H:%M:%S"), "#e0e0e0")
        cpu = psutil.cpu_percent(None)
        ram = psutil.virtual_memory().percent
        self._set("cpu", f"CPU {cpu:3.0f}%", _color(cpu,60,85))
        self._set("ram", f"RAM {ram:3.0f}%", _color(ram,70,85))
        if _H is None:
            self._set("gpu", "GPU n/a")
            self.lbl["dec"].hide()
            return
        try:
            import pynvml as nv
            g = nv.nvmlDeviceGetUtilizationRates(_H).gpu
            self._set("gpu", f"GPU {g:3.0f}%", _color(g,60,85))
        except Exception:
            self._set("gpu", "GPU n/a")
        try:
            d = nv.nvmlDeviceGetDecoderUtilization(_H)[0]
            self._set("dec", f"DEC {d:3.0f}%", _color(d, 70,90))
        except Exception:
            self.lbl["dec"].hide()