# -*- mode: python ; coding: utf-8 -*-
# GhostScripter-K1-K2  ·  PyInstaller spec
# ─────────────────────────────────────────────────────────────────────────────
# Preferred entry point:  python build_tools/build.py
# Direct PyInstaller:     pyinstaller GhostScripter.spec
#
# Output locations
#   Windows folder  : dist/GhostScripter-K1-K2/GhostScripter-K1-K2.exe
#   Linux folder    : dist/GhostScripter-K1-K2/GhostScripter-K1-K2
#   macOS app bundle: dist/GhostScripter-K1-K2.app  (darwin only)
#
# For a single-file EXE (slower start, easier to share) use build.py --onefile
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
from pathlib import Path

ROOT = Path(SPECPATH)   # SPECPATH is always the directory containing this file

# ── Helper: skip a data entry if the source doesn't exist ────────────────────
def _d(src: str, dst: str):
    s = ROOT / src
    if s.exists():
        return (str(s), dst)
    return None

def _collect(pairs):
    return [x for x in pairs if x is not None]


# ── Version string (read from constants.py) ──────────────────────────────────
def _version() -> str:
    c = ROOT / "ghostscripter" / "core" / "constants.py"
    if c.exists():
        for line in c.read_text(encoding="utf-8").splitlines():
            if line.startswith("APP_VERSION"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "1.0.0"

VERSION = _version()

# ── Data files bundled into the package ──────────────────────────────────────
datas = _collect([
    # Dark QSS theme
    _d("ghostscripter/ui/styles/dark.qss",       "ghostscripter/ui/styles"),

    # Application icons
    _d("resources/icons/ghostscripter.png",       "resources/icons"),
    _d("resources/icons/ghostscripter.ico",       "resources/icons"),

    # Resource sub-folders (templates, documentation, styles)
    _d("resources/templates",                     "resources/templates"),
    _d("resources/documentation",                 "resources/documentation"),
    _d("resources/styles",                        "resources/styles"),

    # Documentation shipped in the bundle (accessible via About / Help)
    _d("README.md",                               "."),
    _d("CREDITS.md",                              "."),

    # nwnnsscomp.exe — KotOR NWScript compiler (optional; place in tools/)
    _d("tools/nwnnsscomp.exe",                    "tools"),
    _d("tools/nwnnsscomp",                        "tools"),   # Linux/macOS build
])

# ── Hidden imports ─────────────────────────────────────────────────────────────
hiddenimports = [
    # PyQt5
    "PyQt5",
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    "PyQt5.QtNetwork",
    "PyQt5.sip",
    "PyQt5.QtPrintSupport",

    # stdlib
    "_sqlite3",
    "sqlite3",
    "struct",
    "pathlib",
    "dataclasses",
    "uuid",
    "json",
    "datetime",
    "threading",
    "importlib",
    "importlib.util",
    "importlib.metadata",
    "email.mime.text",
    "xml.etree.ElementTree",

    # SQLAlchemy
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.pool",
    "sqlalchemy.orm",
    "sqlalchemy.event",

    # Flask / IPC callback server
    "flask",
    "flask.json",
    "werkzeug",
    "werkzeug.serving",
    "werkzeug.routing",
    "werkzeug.exceptions",
    "jinja2",
    "jinja2.ext",
    "itsdangerous",
    "click",
    "markupsafe",

    # requests (GhostRigger IPC polling)
    "requests",
    "requests.adapters",
    "urllib3",
    "urllib3.util",
    "certifi",
    "charset_normalizer",
    "idna",

    # Imaging (icon generation, texture preview stubs)
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageQt",

    # colorama (coloured console output)
    "colorama",
    "colorama.initialise",

    # Our full package tree
    "ghostscripter",
    "ghostscripter.core",
    "ghostscripter.core.constants",
    "ghostscripter.core.models",
    "ghostscripter.core.models.project",
    "ghostscripter.core.models.script",
    "ghostscripter.core.models.quest",
    "ghostscripter.core.models.dialogue",
    "ghostscripter.core.database",
    "ghostscripter.core.database.manager",
    "ghostscripter.core.export",
    "ghostscripter.core.export.erf_writer",
    "ghostscripter.core.export.dlg_writer",
    "ghostscripter.core.resource_manager",
    "ghostscripter.core.resource_manager.resource_manager",
    "ghostscripter.core.script_system",
    "ghostscripter.core.quest_system",
    "ghostscripter.core.dialogue_system",
    "ghostscripter.ipc",
    "ghostscripter.ipc.ghostrigger_bridge",
    "ghostscripter.ui",
    "ghostscripter.ui.main_window",
    "ghostscripter.ui.dialogs",
    "ghostscripter.ui.dialogs.new_project_dialog",
    "ghostscripter.ui.dialogs.new_quest_dialog",
    "ghostscripter.ui.widgets",
    "ghostscripter.ui.widgets.script_editor_widget",
    "ghostscripter.ui.widgets.dialogue_editor_widget",
    "ghostscripter.ui.widgets.quest_builder_widget",
    "ghostscripter.ui.widgets.twoda_manager_widget",
    "ghostscripter.ui.widgets.asset_library_widget",
    "ghostscripter.ui.styles",
    "ghostscripter.utils",
    "ghostscripter.documentation",
]

# ── Excluded modules (keep the bundle lean) ───────────────────────────────────
excludes = [
    "tkinter", "_tkinter", "tcl", "Tcl", "Tk",
    "matplotlib", "numpy", "pandas", "scipy",
    "IPython", "jupyter", "notebook",
    "test", "unittest", "pydoc", "doctest", "xmlrpc",
    "lib2to3", "distutils", "ensurepip", "venv",
    "setuptools", "pkg_resources",
    "PyQt5.QtBluetooth",
    "PyQt5.QtDesigner",
    "PyQt5.QtHelp",
    "PyQt5.QtLocation",
    "PyQt5.QtMultimedia",
    "PyQt5.QtMultimediaWidgets",
    "PyQt5.QtNfc",
    "PyQt5.QtPositioning",
    "PyQt5.QtSensors",
    "PyQt5.QtSerialPort",
    "PyQt5.QtSql",
    "PyQt5.QtTest",
    "PyQt5.QtWebChannel",
    "PyQt5.QtXml",
    "PyQt5.QtXmlPatterns",
    "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebEngineCore",
]

# ── Runtime hooks ─────────────────────────────────────────────────────────────
runtime_hooks = [
    str(ROOT / "build_tools" / "hooks" / "rthook_ghostscripter.py"),
]

# ── Windows VERSIONINFO resource (auto-generated by version_info.py) ─────────
_ver_file = ROOT / "build_tools" / "version_info.txt"
_ver_file_arg = str(_ver_file) if _ver_file.exists() else None

# ── Application icon ──────────────────────────────────────────────────────────
_icon_path = ROOT / "resources" / "icons" / "ghostscripter.ico"
_icon = str(_icon_path) if _icon_path.exists() else None

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / "ghostscripter" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "build_tools" / "hooks")],
    hooksconfig={},
    runtime_hooks=runtime_hooks,
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# ── PYZ archive ───────────────────────────────────────────────────────────────
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ── EXE (folder / onedir mode by default) ─────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # goes into COLLECT
    name="GhostScripter-K1-K2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        "vcruntime140.dll",
        "python3*.dll",
        "Qt5Core.dll",
        "Qt5Gui.dll",
        "Qt5Widgets.dll",
        "Qt5Network.dll",
    ],
    console=False,                  # no black terminal window for GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
    version=_ver_file_arg,          # Windows VERSIONINFO (None on non-Windows)
)

# ── COLLECT ───────────────────────────────────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        "vcruntime140.dll",
        "python3*.dll",
        "Qt5Core.dll",
        "Qt5Gui.dll",
        "Qt5Widgets.dll",
        "Qt5Network.dll",
    ],
    name="GhostScripter-K1-K2",
)

# ── macOS .app bundle (darwin only) ───────────────────────────────────────────
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="GhostScripter-K1-K2.app",
        icon=_icon,
        bundle_identifier="com.ghostscripter.k1k2",
        info_plist={
            "CFBundleName":               "GhostScripter-K1-K2",
            "CFBundleDisplayName":        "GhostScripter-K1-K2",
            "CFBundleVersion":            VERSION,
            "CFBundleShortVersionString": VERSION,
            "CFBundleIdentifier":         "com.ghostscripter.k1k2",
            "NSHighResolutionCapable":    True,
            "NSRequiresAquaSystemAppearance": False,
            "NSHumanReadableCopyright":   "GPL-3.0 License",
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName":      "KotOR NWScript Source",
                    "CFBundleTypeExtensions": ["nss"],
                    "CFBundleTypeRole":      "Editor",
                },
                {
                    "CFBundleTypeName":      "KotOR Dialogue File",
                    "CFBundleTypeExtensions": ["dlg"],
                    "CFBundleTypeRole":      "Editor",
                },
            ],
        },
    )
