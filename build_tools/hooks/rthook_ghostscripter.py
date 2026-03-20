# runtime_hook.py  — injected by PyInstaller at process start (before main)
# Place in build_tools/hooks/rthook_ghostscripter.py
import os
import sys

# ── Frozen-bundle path setup ──────────────────────────────────────────
if getattr(sys, 'frozen', False):
    _bundle = sys._MEIPASS

    # 1. Root env var so the app can resolve bundled data
    os.environ.setdefault('GHOSTSCRIPTER_ROOT', _bundle)

    # 2. Qt platform plugin path  (Windows needs explicit pointer)
    for _rel in ('PyQt5/Qt5/plugins', 'PyQt5/plugins', 'qt5/plugins'):
        _p = os.path.join(_bundle, *_rel.split('/'))
        if os.path.isdir(_p):
            os.environ['QT_PLUGIN_PATH'] = _p
            _plat = os.path.join(_p, 'platforms')
            if os.path.isdir(_plat):
                os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = _plat
            break

    # 3. Suppress Qt debug spam
    os.environ.setdefault('QT_LOGGING_RULES', '*.debug=false')

    # 4. High-DPI support
    os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')
    os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
