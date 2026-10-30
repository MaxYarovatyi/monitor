import sys

from PySide6.QtWidgets import QApplication

from core.monitor import Monitor
from ui.main_window import MainWindow


def main():
    decoder = sys.argv[1] if len(sys.argv) > 1 else "auto"   # auto | cuda | cpu
    app = QApplication(sys.argv[:1])
    monitor = Monitor(decoder=decoder)
    win = MainWindow(monitor)
    app.aboutToQuit.connect(monitor.stop)
    win.resize(1400, 820)
    win.show()
    monitor.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()