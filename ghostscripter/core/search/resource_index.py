"""
GhostScripter-K1-K2 — Resource Index
======================================
Fast resource name lookup using sortedcontainers.SortedList.

Open-source tools:
  - sortedcontainers (SortedList) — O(log n) prefix search, O(log n) insert/remove
  - cachetools (LRUCache)         — hot-query memoisation

This module provides a ResourceIndex that can be built from any iterable of
resource filenames (resref.ext strings) and supports:
  • prefix_search(prefix)   — all names starting with prefix  (O(log n + k))
  • extension_search(ext)   — all names with a given extension (O(log n + k))
  • fuzzy_search(query)     — substring match                 (O(n) but cached)
  • add() / remove()        — dynamic updates                 (O(log n))
  • __len__() / __contains__()

Usage
-----
    from ghostscripter.core.search.resource_index import ResourceIndex

    idx = ResourceIndex()
    idx.add_many(["appearance.2da", "globalcat.2da", "c_bastila.utc"])
    for name in idx.prefix_search("c_"):
        print(name)
"""

from __future__ import annotations

import bisect
from typing import Iterable, Iterator, List, Optional

# ── Optional dependencies ──────────────────────────────────────
try:
    from sortedcontainers import SortedList  # type: ignore
    _HAS_SORTED = True
except ImportError:  # pragma: no cover
    _HAS_SORTED = False

try:
    from cachetools import LRUCache  # type: ignore
    _HAS_CACHETOOLS = True
except ImportError:  # pragma: no cover
    _HAS_CACHETOOLS = False

_CACHE_SIZE = 256


class ResourceIndex:
    """
    Fast, case-insensitive resource name index.

    Names are stored lower-case internally.  All lookups are case-insensitive.

    If sortedcontainers is installed, prefix_search and extension_search use
    O(log n + k) SortedList.irange() instead of O(n) linear scans.
    """

    def __init__(self):
        # Primary storage: sorted lower-case names
        if _HAS_SORTED:
            self._names: "SortedList[str]" = SortedList()
        else:
            self._names: list = []   # kept sorted via bisect

        # Extension index: ext → sorted list of names
        self._by_ext: dict = {}   # str → list[str]  (not sorted)

        # LRU cache for fuzzy_search
        if _HAS_CACHETOOLS:
            self._fuzzy_cache: LRUCache = LRUCache(maxsize=_CACHE_SIZE)
        else:
            self._fuzzy_cache = None

    # ── Mutation ──────────────────────────────────────────────

    def add(self, name: str) -> None:
        """Add a resource name (case-insensitive storage)."""
        lc = name.lower()
        if lc in self:
            return
        if _HAS_SORTED:
            self._names.add(lc)
        else:
            bisect.insort(self._names, lc)

        ext = _ext(lc)
        self._by_ext.setdefault(ext, [])
        # Keep extension list sorted for extension_search
        bisect.insort(self._by_ext[ext], lc)

        # Invalidate fuzzy cache on any mutation
        if self._fuzzy_cache is not None:
            self._fuzzy_cache.clear()

    def add_many(self, names: Iterable[str]) -> None:
        """Add multiple names at once (slightly faster than repeated add)."""
        for n in names:
            self.add(n)

    def remove(self, name: str) -> bool:
        """Remove a name.  Returns True if it was present."""
        lc = name.lower()
        if lc not in self:
            return False
        if _HAS_SORTED:
            self._names.remove(lc)
        else:
            idx = bisect.bisect_left(self._names, lc)
            if idx < len(self._names) and self._names[idx] == lc:
                self._names.pop(idx)

        ext = _ext(lc)
        if ext in self._by_ext:
            try:
                self._by_ext[ext].remove(lc)
            except ValueError:
                pass

        if self._fuzzy_cache is not None:
            self._fuzzy_cache.clear()
        return True

    def clear(self) -> None:
        """Remove all names."""
        if _HAS_SORTED:
            self._names.clear()
        else:
            self._names.clear()
        self._by_ext.clear()
        if self._fuzzy_cache is not None:
            self._fuzzy_cache.clear()

    # ── Queries ───────────────────────────────────────────────

    def prefix_search(self, prefix: str, max_results: int = 200) -> List[str]:
        """Return names starting with *prefix* (case-insensitive, O(log n + k)).

        Uses SortedList.irange() when available, otherwise bisect on a plain
        sorted list.
        """
        p = prefix.lower()
        if not p:
            return list(self._names[:max_results])

        p_end = p[:-1] + chr(ord(p[-1]) + 1)

        if _HAS_SORTED:
            result = list(self._names.irange(  # type: ignore[attr-defined]
                p, p_end, inclusive=(True, False)
            ))
        else:
            lo = bisect.bisect_left(self._names, p)
            hi = bisect.bisect_left(self._names, p_end)
            result = self._names[lo:hi]

        return result[:max_results]

    def extension_search(self, ext: str, max_results: int = 500) -> List[str]:
        """Return all names with extension *ext* (e.g. '.2da', '.utc').

        O(log n + k) using the per-extension sorted list.
        """
        e = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        names = self._by_ext.get(e, [])
        return names[:max_results]

    def fuzzy_search(self, query: str, max_results: int = 100) -> List[str]:
        """Return names containing *query* anywhere (O(n), but LRU-cached)."""
        q = query.lower()
        if self._fuzzy_cache is not None:
            cached = self._fuzzy_cache.get(q)
            if cached is not None:
                return cached[:max_results]

        result = [n for n in self._names if q in n]
        if self._fuzzy_cache is not None:
            self._fuzzy_cache[q] = result
        return result[:max_results]

    def extensions(self) -> List[str]:
        """Return all extensions present in the index, sorted."""
        return sorted(self._by_ext.keys())

    # ── Standard container methods ────────────────────────────

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        lc = name.lower()
        if _HAS_SORTED:
            return lc in self._names  # type: ignore[operator]
        idx = bisect.bisect_left(self._names, lc)
        return idx < len(self._names) and self._names[idx] == lc

    def __len__(self) -> int:
        return len(self._names)

    def __iter__(self) -> Iterator[str]:
        return iter(self._names)

    def __repr__(self) -> str:
        return f"ResourceIndex({len(self)} names, {len(self._by_ext)} extensions)"


# ── Module-level convenience ───────────────────────────────────

def _ext(name: str) -> str:
    """Return the file extension including dot, or '' if none."""
    dot = name.rfind(".")
    return name[dot:] if dot >= 0 else ""


def build_index_from_manager(resource_manager) -> ResourceIndex:
    """Build a ResourceIndex from a ResourceManager instance.

    Adds all filenames known to the ResourceManager's KEY file and
    override folder.
    """
    idx = ResourceIndex()
    if resource_manager._key:
        for entry in resource_manager._key.entries:
            idx.add(entry.filename)
    for fname in resource_manager._override_files:
        idx.add(fname)
    return idx
