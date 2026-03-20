"""
GhostScripter-K1-K2 — Application Entry Point
"""
import sys
import os
import traceback
from pathlib import Path


# ── Logging — must be configured FIRST, before any other gs imports ──────────
from ghostscripter.utils.log_setup import setup_logging, get_log_path

_gs_log = setup_logging()   # sets up file + stderr + ring buffer handlers
import logging as _logging
_log = _logging.getLogger("ghostscripter.main")


# ── Crash logger ───────────────────────────────────────────────
def _crash_log_path() -> Path:
    return get_log_path().parent / "ghostscripter_crash.log"


def _write_crash(exc_text: str):
    try:
        _crash_log_path().write_text(exc_text, encoding="utf-8")
    except Exception:
        pass


# ── Resource path helper (PyInstaller _MEIPASS) ────────────────
def _res(relative: str) -> str:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent.parent
    return str(base / relative)


# ── Qt platform fix ────────────────────────────────────────────
if sys.platform == "linux" and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")


def _load_stylesheet(app) -> None:
    try:
        qss_path = _res("ghostscripter/ui/styles/dark.qss")
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except Exception:
        pass


def create_splash(app):
    from qtpy.QtWidgets import QSplashScreen
    from qtpy.QtCore import Qt
    from qtpy.QtGui import QPixmap, QPainter, QColor, QFont
    from ghostscripter.core.constants import APP_NAME, APP_VERSION

    pix = QPixmap(500, 280)
    pix.fill(QColor("#1e1e1e"))
    painter = QPainter(pix)
    painter.setPen(QColor("#9cdcfe"))
    painter.setFont(QFont("Segoe UI", 22, QFont.Bold))
    painter.drawText(pix.rect().adjusted(0, 60, 0, 0),
                     Qt.AlignHCenter | Qt.AlignTop, APP_NAME)
    painter.setPen(QColor("#569cd6"))
    painter.setFont(QFont("Segoe UI", 11))
    painter.drawText(pix.rect().adjusted(0, 120, 0, 0),
                     Qt.AlignHCenter | Qt.AlignTop, "KotOR 1 & 2 TSL Modding IDE")
    painter.setPen(QColor("#4ec9b0"))
    painter.setFont(QFont("Segoe UI", 9))
    painter.drawText(pix.rect().adjusted(0, 180, 0, 0),
                     Qt.AlignHCenter | Qt.AlignTop,
                     f"Version {APP_VERSION}")
    painter.setPen(QColor("#666666"))
    painter.setFont(QFont("Segoe UI", 8))
    painter.drawText(pix.rect().adjusted(0, 240, 0, 0),
                     Qt.AlignHCenter | Qt.AlignTop, "Open source — GPL-3.0")
    painter.end()

    splash = QSplashScreen(pix)
    splash.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint)
    return splash


def main():
    from qtpy.QtWidgets import QApplication, QMessageBox
    from qtpy.QtCore import Qt, QTimer
    from qtpy.QtGui import QFont
    from ghostscripter.core.constants import APP_NAME, APP_VERSION

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("GhostScripter")
    app.setFont(QFont("Segoe UI", 9))

    _load_stylesheet(app)

    # Splash screen
    splash = None
    try:
        splash = create_splash(app)
        splash.show()
        app.processEvents()
    except Exception:
        splash = None

    # ── Main window ────────────────────────────────────────────
    try:
        from ghostscripter.ui.main_window import MainWindow
        _log.info("Creating MainWindow")
        window = MainWindow()
        _log.info("MainWindow created OK")
    except Exception:
        tb = traceback.format_exc()
        _log.critical("MainWindow creation FAILED:\n%s", tb)
        _write_crash(tb)
        if splash:
            splash.close()
        msg = QMessageBox()
        msg.setWindowTitle("GhostScripter — Startup Error")
        msg.setIcon(QMessageBox.Critical)
        msg.setText(
            "GhostScripter failed to start.\n\n"
            f"Crash log: {_crash_log_path()}\n\n"
            "Please report this on the GitHub issue tracker."
        )
        msg.setDetailedText(tb)
        msg.exec()
        sys.exit(1)

    if splash:
        QTimer.singleShot(1400, splash.close)
    window.show()
    window.raise_()
    window.activateWindow()

    # Show tutorial guide on first launch (or if user opted in)
    QTimer.singleShot(600, window.show_tutorial_on_startup)

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        _write_crash(tb)
        raise
