"""
GhostScripter-K1-K2 — Application Entry Point
"""
import sys
import os
from pathlib import Path

# ── Qt platform plugin fix for headless environments ──────────
# Set Qt offscreen platform if DISPLAY not available
if sys.platform == "linux" and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PyQt5.QtWidgets import QApplication, QSplashScreen, QLabel
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap, QPainter, QColor

from ghostscripter.core.constants import APP_NAME, APP_VERSION


def create_splash(app: QApplication):
    """Create a simple splash screen."""
    pix = QPixmap(500, 280)
    pix.fill(QColor("#1e1e1e"))

    painter = QPainter(pix)
    painter.setPen(QColor("#9cdcfe"))
    painter.setFont(QFont("Segoe UI", 22, QFont.Bold))
    painter.drawText(pix.rect().adjusted(0, 60, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                     APP_NAME)
    painter.setPen(QColor("#569cd6"))
    painter.setFont(QFont("Segoe UI", 11))
    painter.drawText(pix.rect().adjusted(0, 120, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                     "KotOR 1 & 2 TSL Modding IDE")
    painter.setPen(QColor("#4ec9b0"))
    painter.setFont(QFont("Segoe UI", 9))
    painter.drawText(pix.rect().adjusted(0, 180, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                     f"Version {APP_VERSION}  •  GPL-3.0")
    painter.setPen(QColor("#666666"))
    painter.setFont(QFont("Segoe UI", 8))
    painter.drawText(pix.rect().adjusted(0, 240, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                     "Loading…")
    painter.end()

    splash = QSplashScreen(pix)
    splash.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint)
    return splash


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("GhostScripter")

    # Set application-wide font
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    # Show splash
    try:
        splash = create_splash(app)
        splash.show()
        app.processEvents()
    except Exception:
        splash = None

    # Import and create main window
    from ghostscripter.ui.main_window import MainWindow
    window = MainWindow()

    # Close splash and show main window
    if splash:
        QTimer.singleShot(1200, splash.close)
    QTimer.singleShot(1300, window.show)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
