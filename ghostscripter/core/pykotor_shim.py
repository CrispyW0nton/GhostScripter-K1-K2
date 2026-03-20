"""
GhostScripter-K1-K2 — PyKotor Compatibility Shim
=================================================
Provides a pykotor-like API surface on top of GhostScripter's internal
ResourceManager.  Once the full pykotor library is added as a dependency
(Phase 1 completion), this module will delegate to the real pykotor classes
instead of our internal implementations.

Usage (drop-in within GhostScripter MCP handlers):

    from ghostscripter.core.pykotor_shim import ShimInstallation

    install = ShimInstallation(game_path)
    data = install.resource("appearance", "2da")
    # → bytes or None

Architecture note
-----------------
This shim mirrors the pykotor.extract.Installation API so that when we
eventually ``import pykotor`` for real, we only need to change this one
file.  All callers will remain unchanged.

References
----------
- OldRepublicDevs/PyKotor Libraries/PyKotor/src/pykotor/extract/installation.py
- OldRepublicDevs/PyKotor Libraries/PyKotor/src/pykotor/extract/capsule.py
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# ── Try to import the real pykotor first ─────────────────────────────────────
_PYKOTOR_AVAILABLE = False
try:
    from pykotor.extract.installation import Installation as _PKInstallation  # type: ignore
    from pykotor.extract.file import ResourceIdentifier as _PKResourceIdentifier  # type: ignore
    from pykotor.resource.type import ResourceType as _PKResourceType  # type: ignore
    _PYKOTOR_AVAILABLE = True
    log.debug("pykotor library found — ShimInstallation will delegate to real Installation")
except ImportError:
    log.debug("pykotor library not installed — ShimInstallation using internal ResourceManager")


class ShimInstallation:
    """Drop-in replacement for pykotor.extract.installation.Installation.

    When pykotor is installed this is a thin wrapper around the real
    Installation class.  When it is not installed we fall back to
    GhostScripter's own ResourceManager.

    Supported methods mirror pykotor's Installation API:
      - resource(resref, restype_str) → bytes | None
      - list_by_type(restype_str) → list[str]  (resrefs)
      - override_path() → Path | None
      - chitin_path() → Path | None

    Parameters
    ----------
    path:
        Root directory of the KotOR installation (must contain chitin.key).
    game_id:
        'K1' or 'K2' — used only by the fallback ResourceManager.
    """

    def __init__(self, path: str | Path, game_id: str = "K1") -> None:
        self._path = Path(path) if path else Path(".")
        self._game_id = game_id.upper()
        self._real: object | None = None
        self._rm: object | None = None

        if _PYKOTOR_AVAILABLE and self._path.is_dir():
            try:
                self._real = _PKInstallation(self._path)
                log.debug("ShimInstallation backed by real pykotor.Installation at %s", self._path)
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("pykotor.Installation init failed (%s), falling back to internal RM", exc)

        # Fallback: use GhostScripter's own ResourceManager
        if self._path.is_dir():
            from ghostscripter.core.resource_manager import ResourceManager
            rm = ResourceManager()
            rm.load_game(self._path)
            self._rm = rm
            log.debug("ShimInstallation backed by internal ResourceManager at %s", self._path)

    # ── Core API ──────────────────────────────────────────────────────────────

    def resource(self, resref: str, restype_str: str) -> bytes | None:
        """Return raw bytes for (resref, restype_str), or None if not found.

        Parameters
        ----------
        resref:
            Resource name without extension (e.g. 'appearance').
        restype_str:
            Extension string without dot (e.g. '2da', 'dlg', 'utc').
        """
        if self._real is not None and _PYKOTOR_AVAILABLE:
            try:
                rt = _PKResourceType.from_extension(restype_str)
                result = self._real.resource(resref, rt)  # type: ignore[attr-defined]
                return result.data if result is not None else None
            except Exception as exc:  # noqa: BLE001
                log.warning("ShimInstallation.resource pykotor call failed: %s", exc)

        if self._rm is not None:
            try:
                filename = f"{resref}.{restype_str.lstrip('.')}"
                return self._rm.read(filename)  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                log.debug("ShimInstallation.resource RM fallback failed: %s", exc)

        return None

    def list_by_type(self, restype_str: str) -> list[str]:
        """Return sorted list of resrefs for a given resource type extension."""
        if self._real is not None and _PYKOTOR_AVAILABLE:
            try:
                rt = _PKResourceType.from_extension(restype_str)
                # pykotor returns FileResource objects
                resources = self._real.resources_by_type(rt)  # type: ignore[attr-defined]
                return sorted({r.resname for r in resources})
            except Exception as exc:  # noqa: BLE001
                log.warning("ShimInstallation.list_by_type pykotor call failed: %s", exc)

        if self._rm is not None:
            try:
                entries = self._rm.list_by_type(restype_str)  # type: ignore[attr-defined]
                return sorted({e.resref for e in entries})
            except Exception as exc:  # noqa: BLE001
                log.debug("ShimInstallation.list_by_type RM fallback failed: %s", exc)

        return []

    def override_path(self) -> Path | None:
        """Return the Override directory path, or None if not available."""
        if self._real is not None and _PYKOTOR_AVAILABLE:
            try:
                p = self._real.override_path()  # type: ignore[attr-defined]
                return Path(p) if p else None
            except Exception:  # noqa: BLE001
                pass

        candidate = self._path / "override"
        return candidate if candidate.is_dir() else None

    def chitin_path(self) -> Path | None:
        """Return the chitin.key path, or None if not present."""
        candidate = self._path / "chitin.key"
        return candidate if candidate.is_file() else None

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def backed_by_pykotor(self) -> bool:
        """True if the real pykotor.Installation is being used."""
        return self._real is not None

    @property
    def path(self) -> Path:
        """Root installation path."""
        return self._path

    def __repr__(self) -> str:  # pragma: no cover
        backend = "pykotor" if self.backed_by_pykotor else "internal-rm"
        return f"ShimInstallation(path={self._path!r}, backend={backend!r})"


def get_installation(game_id: str, path: str | None = None) -> ShimInstallation | None:
    """Convenience factory — resolves path from env vars if not supplied.

    Parameters
    ----------
    game_id:
        'K1' or 'K2'.
    path:
        Explicit path override; if None the standard env-var search is used.

    Returns
    -------
    ShimInstallation or None if no valid installation path is found.
    """
    from ghostscripter.mcp.tools_pkg._helpers import _find_game_path

    resolved = Path(path) if path else _find_game_path(game_id.upper())
    if resolved is None or not resolved.is_dir():
        return None
    return ShimInstallation(resolved, game_id)
