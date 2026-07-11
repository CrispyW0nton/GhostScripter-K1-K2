#!/usr/bin/env python3
"""
build_tools/build.py
====================
Cross-platform build script for GhostScripter-K1-K2.

Usage
-----
    python build_tools/build.py              # full build (clean → version → pyinstaller → package)
    python build_tools/build.py --clean      # remove dist/ and build/ only
    python build_tools/build.py --no-zip     # build but skip ZIP archive
    python build_tools/build.py --onefile    # single-file EXE (slower launch, easier distribute)
    python build_tools/build.py --no-clean   # retain an earlier artefact in dist/
    python build_tools/build.py --debug      # console=True for traceback visibility
    python build_tools/build.py --version    # print resolved version and exit

All output lands in  dist/GhostScripter-K1-K2/   (folder mode, default)
or                   dist/GhostScripter-K1-K2.exe (--onefile).

The script must be run from the repository root.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# ── Repo root ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
BUILD_TOOLS = ROOT / "build_tools"
SPEC_FILE   = ROOT / "GhostScripter.spec"
DIST_DIR    = ROOT / "dist"
BUILD_DIR   = ROOT / "build"

# ── App identity ─────────────────────────────────────────────────────────────
APP_NAME    = "GhostScripter-K1-K2"
APP_EXE     = "GhostScripter-K1-K2"       # no spaces — safe for shell
ENTRY_POINT = ROOT / "ghostscripter" / "main.py"

# ── Version pulled from constants.py ─────────────────────────────────────────
def _read_version() -> str:
    constants = ROOT / "ghostscripter" / "core" / "constants.py"
    if constants.exists():
        for line in constants.read_text(encoding="utf-8").splitlines():
            if line.startswith("APP_VERSION"):
                # APP_VERSION = "1.0.0"
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "1.0.0"


VERSION = _read_version()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _log(msg: str, *, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    colours = {"INFO": "\033[36m", "OK": "\033[32m", "WARN": "\033[33m",
                "ERR": "\033[31m", "STEP": "\033[35m"}
    reset = "\033[0m"
    col = colours.get(level, "")
    print(f"  {col}[{level}]{reset} {ts}  {msg}", flush=True)


def _run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> int:
    _log(" ".join(str(c) for c in cmd), level="STEP")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, cwd=cwd or ROOT, check=check, env=env)
    return result.returncode


def _clean() -> None:
    _log("Cleaning previous build artefacts…", level="STEP")
    for d in (DIST_DIR, BUILD_DIR):
        if d.exists():
            shutil.rmtree(d)
            _log(f"  Removed {d.relative_to(ROOT)}", level="OK")
    # Remove stale .spec-generated __pycache__
    for p in ROOT.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def _ensure_icon() -> Path:
    ico = ROOT / "resources" / "icons" / "ghostscripter.ico"
    if ico.exists():
        return ico
    _log("Icon not found — attempting to regenerate…", level="WARN")
    gen = ROOT / "build_tools" / "gen_icon.py"
    if gen.exists():
        _run([sys.executable, str(gen)])
    return ico if ico.exists() else None


def _generate_version_file() -> Path | None:
    """Generate a Windows VERSIONINFO resource file via version_info.py."""
    gen = BUILD_TOOLS / "version_info.py"
    if not gen.exists():
        _log("version_info.py not found — skipping VERSIONINFO", level="WARN")
        return None
    out = BUILD_TOOLS / "version_info.txt"
    _run([sys.executable, str(gen), "--output", str(out), "--version", VERSION])
    return out if out.exists() else None


def _pyinstaller(*, onefile: bool, debug: bool, version_file: Path | None) -> None:
    ico = _ensure_icon()
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        f"--name={APP_EXE}",
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
        # data files
        f"--add-data={ROOT / 'ghostscripter' / 'ui' / 'styles' / 'dark.qss'}{os.pathsep}ghostscripter/ui/styles",
        f"--add-data={ROOT / 'resources' / 'icons'}{os.pathsep}resources/icons",
        f"--add-data={ROOT / 'resources' / 'scripts'}{os.pathsep}resources/scripts",
        f"--add-data={ROOT / 'README.md'}{os.pathsep}.",
        f"--add-data={ROOT / 'CREDITS.md'}{os.pathsep}.",
        # hooks
        f"--additional-hooks-dir={BUILD_TOOLS / 'hooks'}",
        f"--runtime-hook={BUILD_TOOLS / 'hooks' / 'rthook_ghostscripter.py'}",
        # hidden imports
        "--hidden-import=ghostscripter",
        "--hidden-import=ghostscripter.core",
        "--hidden-import=ghostscripter.core.constants",
        "--hidden-import=ghostscripter.core.gff_codec",
        "--hidden-import=ghostscripter.core.lip",
        "--hidden-import=ghostscripter.core.ssf",
        "--hidden-import=ghostscripter.core.services",
        "--hidden-import=ghostscripter.core.nwscript.compiler_defs",
        "--hidden-import=ghostscripter.core.database.manager",
        "--hidden-import=ghostscripter.core.export.erf_writer",
        "--hidden-import=ghostscripter.core.export.dlg_writer",
        "--hidden-import=ghostscripter.core.resource_manager.resource_manager",
        "--hidden-import=ghostscripter.ipc.ghostrigger_bridge",
        "--hidden-import=ghostscripter.ui.main_window",
        "--hidden-import=ghostscripter.ui.widgets.script_editor_widget",
        "--hidden-import=ghostscripter.ui.widgets.dialogue_editor_widget",
        "--hidden-import=ghostscripter.ui.widgets.lip_editor_widget",
        "--hidden-import=ghostscripter.ui.widgets.quest_builder_widget",
        "--hidden-import=ghostscripter.ui.widgets.twoda_manager_widget",
        "--hidden-import=ghostscripter.ui.widgets.asset_library_widget",
        "--hidden-import=ghostscripter.mcp",
        "--hidden-import=ghostscripter.mcp.__main__",
        "--hidden-import=ghostscripter.mcp.server",
        "--hidden-import=ghostscripter.mcp.tools",
        "--hidden-import=ghostscripter.mcp.tools_pkg",
        "--hidden-import=ghostscripter.mcp.tools_pkg._helpers",
        "--hidden-import=ghostscripter.mcp.tools_pkg.handlers_composite",
        "--hidden-import=ghostscripter.mcp.tools_pkg.handlers_query",
        "--hidden-import=ghostscripter.mcp.tools_pkg.handlers_read",
        "--hidden-import=ghostscripter.mcp.tools_pkg.handlers_write",
        "--hidden-import=ghostscripter.mcp.tools_pkg.tool_defs",
        "--hidden-import=PyQt5",
        "--hidden-import=PyQt5.QtCore",
        "--hidden-import=PyQt5.QtGui",
        "--hidden-import=PyQt5.QtWidgets",
        "--hidden-import=PyQt5.QtNetwork",
        "--hidden-import=PyQt5.sip",
        "--hidden-import=flask",
        "--hidden-import=werkzeug",
        "--hidden-import=jinja2",
        "--hidden-import=requests",
        "--hidden-import=sqlalchemy",
        "--hidden-import=sqlalchemy.dialects.sqlite",
        "--hidden-import=_sqlite3",
        "--hidden-import=sqlite3",
        "--hidden-import=mcp.server.stdio",
        "--hidden-import=mcp.server.sse",
        "--hidden-import=mcp.server.streamable_http_manager",
        "--hidden-import=pykotor.extract.savedata",
        "--hidden-import=pykotor.resource.formats.ncs.compilers",
        "--hidden-import=pykotor.resource.formats.ncs.decompiler",
        "--hidden-import=pykotor.resource.generics.utc",
        # exclusions (keep bundle lean)
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
        "--exclude-module=numpy",
        "--exclude-module=pandas",
        "--exclude-module=scipy",
        "--exclude-module=IPython",
        "--exclude-module=pytest",
        "--exclude-module=PyQt5.QtBluetooth",
        "--exclude-module=PyQt5.QtDesigner",
        "--exclude-module=PyQt5.QtHelp",
        "--exclude-module=PyQt5.QtMultimedia",
        "--exclude-module=PyQt5.QtSql",
        "--exclude-module=PyQt5.QtTest",
        "--exclude-module=PyQt5.QtXml",
    ]

    if ico and ico.exists():
        cmd.append(f"--icon={ico}")

    if version_file and version_file.exists() and platform.system() == "Windows":
        cmd.append(f"--version-file={version_file}")

    if onefile:
        cmd.append("--onefile")
        cmd.append("--windowed")
    else:
        cmd.append("--onedir")
        cmd.append("--windowed")

    if debug:
        # Remove --windowed so we get a console for stack traces
        cmd = [c for c in cmd if c not in ("--windowed",)]
        cmd.append("--console")

    cmd.append(str(ENTRY_POINT))
    _run(cmd)


def _zip_output(onefile: bool) -> Path | None:
    """Package the dist folder (or single exe) into a ZIP for distribution."""
    tag = f"{APP_NAME}-v{VERSION}-{platform.system().lower()}"
    if platform.system() == "Windows" and not onefile:
        tag += "-portable"
    zip_path = DIST_DIR / f"{tag}.zip"

    if onefile:
        src = DIST_DIR / f"{APP_EXE}.exe" if platform.system() == "Windows" \
              else DIST_DIR / APP_EXE
        if not src.exists():
            _log(f"EXE not found at {src} — skipping ZIP", level="WARN")
            return None
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(src, src.name)
    else:
        src_dir = DIST_DIR / APP_EXE
        if not src_dir.exists():
            _log(f"dist folder not found at {src_dir} — skipping ZIP", level="WARN")
            return None
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in src_dir.rglob("*"):
                if file.is_file():
                    zf.write(file, Path(APP_NAME) / file.relative_to(src_dir))

    size_mb = zip_path.stat().st_size / 1_048_576
    _log(f"Packaged → {zip_path.name}  ({size_mb:.1f} MB)", level="OK")
    return zip_path


def _print_summary(zip_path: Path | None, onefile: bool, elapsed: float) -> None:
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print(f"  ║  {APP_NAME} v{VERSION} build complete".ljust(54) + "  ║")
    print(f"  ║  Platform : {platform.system()} {platform.machine()}".ljust(55) + " ║")
    print(f"  ║  Elapsed  : {elapsed:.1f}s".ljust(55) + " ║")
    if onefile:
        exe = (DIST_DIR / f"{APP_EXE}.exe") if platform.system() == "Windows" \
              else (DIST_DIR / APP_EXE)
        print(f"  ║  EXE      : dist/{exe.name}".ljust(55) + " ║")
    else:
        print(f"  ║  Folder   : dist/{APP_EXE}/".ljust(55) + " ║")
    if zip_path:
        print(f"  ║  Archive  : dist/{zip_path.name}".ljust(55) + " ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=f"Build {APP_NAME} into a standalone executable."
    )
    p.add_argument("--clean",    action="store_true", help="Clean build artefacts and exit")
    p.add_argument("--no-zip",   action="store_true", help="Skip creating ZIP archive")
    p.add_argument("--onefile",  action="store_true", help="Single-file EXE (slower startup)")
    p.add_argument("--debug",    action="store_true", help="Console-mode build (shows tracebacks)")
    p.add_argument("--no-clean", action="store_true", help="Keep existing dist/build artefacts")
    p.add_argument("--version",  action="store_true", help="Print version and exit")
    return p.parse_args()


def main() -> None:
    import time
    # Windows runners and redirected desktop terminals may default to a legacy
    # code page that cannot encode the progress glyphs used below.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    args = _parse_args()

    os.chdir(ROOT)   # ensure CWD is repo root

    if args.version:
        print(f"{APP_NAME} {VERSION}")
        return

    print()
    print(f"  ╔══════════════════════════════════════════════════════╗")
    print(f"  ║   GhostScripter-K1-K2  Build System                 ║")
    print(f"  ║   Version {VERSION}  •  {platform.system()} {platform.machine()}".ljust(55) + " ║")
    print(f"  ╚══════════════════════════════════════════════════════╝")
    print()

    t0 = time.monotonic()

    if not args.no_clean:
        _clean()
    if args.clean:
        _log("--clean requested; stopping after clean.", level="OK")
        return

    version_file = _generate_version_file() if platform.system() == "Windows" else None

    _log(f"Running PyInstaller  (onefile={args.onefile}, debug={args.debug})…", level="STEP")
    _pyinstaller(onefile=args.onefile, debug=args.debug, version_file=version_file)

    zip_path = None
    if not args.no_zip:
        _log("Packaging ZIP…", level="STEP")
        zip_path = _zip_output(args.onefile)

    elapsed = time.monotonic() - t0
    _print_summary(zip_path, args.onefile, elapsed)


if __name__ == "__main__":
    main()
