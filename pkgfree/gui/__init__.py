"""Fluent (Windows 11 style) GUI built with PySide6-Fluent-Widgets."""

import sys

ACCENT = "#0078D4"


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import setTheme, setThemeColor

    from .config import cfg, load_config

    app = QApplication.instance() or QApplication(sys.argv)
    load_config()
    setThemeColor(ACCENT)
    setTheme(cfg.get(cfg.themeMode))
    cfg.themeChanged.connect(setTheme)

    from .window import MainWindow

    win = MainWindow()
    win.show()
    return app.exec()
