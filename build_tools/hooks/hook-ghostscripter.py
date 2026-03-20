# hook-ghostscripter.py
# PyInstaller runtime hook — run BEFORE the app starts inside the frozen bundle.
# Fixes path resolution, Qt plugin paths, and stdlib sqlite3 availability.

import os
import sys


def _fix_paths():
    """
    When running as a frozen PyInstaller bundle, __file__ and sys.argv[0]
    point into the unpacked temp dir.  We set a GHOSTSCRIPTER_ROOT env-var
    so the app can find bundled data files (dark.qss, icons, etc.) reliably.
    """
    if getattr(sys, 'frozen', False):
        # sys._MEIPASS is the temp folder where PyInstaller unpacks everything
        bundle_dir = sys._MEIPASS
        os.environ['GHOSTSCRIPTER_ROOT'] = bundle_dir

        # Make sure the bundle dir is first on sys.path so our package wins
        if bundle_dir not in sys.path:
            sys.path.insert(0, bundle_dir)


def _fix_qt():
    """
    Tell Qt where its plugins live inside the frozen bundle.
    Without this PyQt5 fails to find platform/imageformat plugins on Windows.
    """
    if getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS
        qt_plugin_path = os.path.join(bundle_dir, 'PyQt5', 'Qt5', 'plugins')
        if not os.path.isdir(qt_plugin_path):
            qt_plugin_path = os.path.join(bundle_dir, 'PyQt5', 'plugins')
        if os.path.isdir(qt_plugin_path):
            os.environ['QT_PLUGIN_PATH'] = qt_plugin_path
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(
                qt_plugin_path, 'platforms'
            )


def _fix_sqlite():
    """
    Ensure the stdlib sqlite3 DLL is loadable.  On some Windows builds
    PyInstaller doesn't auto-detect _sqlite3.pyd.
    """
    try:
        import sqlite3  # noqa: F401
    except ImportError:
        pass  # will surface as a clear error later


_fix_paths()
_fix_qt()
_fix_sqlite()
