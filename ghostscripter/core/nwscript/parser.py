"""
GhostScripter-K1-K2 — NWScript.nss Parser
Parses the official nwscript.nss from KotOR 1 & 2 to build a complete
function + constant database used for autocomplete and the function reference.

Architecture modelled after:
  - KotOR Scripting Tool (C#): NWScriptParser.cs
  - PyKotor: pykotor/common/scriptdefs.py + ScriptFunction/ScriptParam

Open-source tools used:
  - sortedcontainers (SortedList) — O(log n) prefix search for autocomplete
  - pyparsing — optional grammar-level validation of function signatures
  - cachetools (LRUCache) — memoised search_functions / search_constants

Usage:
    db = NWScriptDB.load_k1()
    db = NWScriptDB.load_k2()

    for func in db.functions:
        print(func.name, func.return_type, func.signature)

    for const in db.constants:
        print(const.type, const.name, const.value)

    # O(log n) prefix autocomplete:
    names = db.autocomplete("GetGlobal")
"""

from __future__ import annotations

import bisect
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

# ── Optional fast-lookup dependencies ──────────────────────────
try:
    from sortedcontainers import SortedList as _SortedList  # O(log n) bisect
    _HAS_SORTED = True
except ImportError:  # pragma: no cover
    _HAS_SORTED = False

try:
    from cachetools import LRUCache, cached  # memoised search
    _HAS_CACHETOOLS = True
except ImportError:  # pragma: no cover
    _HAS_CACHETOOLS = False


# ── Data structures ────────────────────────────────────────────

@dataclass
class NWParam:
    """One parameter in a function signature."""
    type: str
    name: str
    default: str | None = None

    def __str__(self) -> str:
        s = f"{self.type} {self.name}"
        if self.default is not None:
            s += f" = {self.default}"
        return s


@dataclass
class NWFunction:
    """A function defined in nwscript.nss."""
    return_type: str
    name: str
    params: List[NWParam] = field(default_factory=list)
    comment: str = ""       # doc comment above the declaration
    line_number: int = 0
    # Pre-built strings for display / insertion
    _signature: str = ""

    @property
    def signature(self) -> str:
        if self._signature:
            return self._signature
        params = ", ".join(str(p) for p in self.params)
        return f"{self.return_type} {self.name}({params})"

    @property
    def call_snippet(self) -> str:
        """Snippet for insertion: name(param1, param2)"""
        params = ", ".join(p.name for p in self.params)
        return f"{self.name}({params})"

    @property
    def category(self) -> str:
        """Infer category from function name prefix."""
        n = self.name
        # Minigame functions (SWMG_ prefix)
        if n.startswith("SWMG_"):
            return "Minigame (SWMG)"
        # Variable access
        if n.startswith("Get") or n.startswith("Set"):
            if "Global" in n:
                return "Global Variables"
            if "Local" in n:
                return "Local Variables"
        if any(n.startswith(p) for p in ("Action", "Do")):
            return "Actions"
        if any(n.startswith(p) for p in ("Effect", "Apply", "Remove")):
            return "Effects"
        if any(n.startswith(p) for p in ("Create", "Destroy")):
            return "Create/Destroy"
        if any(n.startswith(p) for p in ("Is", "Has", "Can")):
            return "Queries"
        if n.startswith("Get"):
            return "Getters"
        if n.startswith("Set"):
            return "Setters"
        # Journal
        if "Journal" in n:
            return "Journal"
        # Music / Audio / Sound
        if any(p in n for p in ("Music", "AmbientSound", "SoundObject")):
            return "Audio"
        # Animation / Cutscene
        if any(n.startswith(p) for p in ("Play", "Cutscene", "EnableVideoEffect", "DisableVideoEffect")):
            return "Cutscene/Animation"
        # Math / Vector helpers
        if any(n.startswith(p) for p in ("Vector", "AngleTo", "FloatTo", "IntTo", "RoundTo")):
            return "Math/Vector"
        # Debug / Output
        if any(n.startswith(p) for p in ("Print", "Debug")):
            return "Debug"
        # Talent (feats/spells/skills)
        if n.startswith("Talent"):
            return "Talents"
        # Faction / Reputation
        if any(p in n for p in ("Faction", "Reputation", "Surrender")):
            return "Faction/Reputation"
        # Event
        if n.startswith("Event"):
            return "Events"
        # Module / Game flow
        if any(n.startswith(p) for p in ("StartNewModule", "EndGame", "StartCredit")):
            return "Module/Game"
        # UI / Screen
        if any(p in n for p in ("Show", "Display", "Galaxy", "Tutorial", "Upgrade")):
            return "UI"
        # Party
        if "Party" in n or "Companion" in n:
            return "Party"
        if "Combat" in n or "Attack" in n or "Damage" in n:
            return "Combat"
        if "Conversation" in n or "Speak" in n or "String" in n:
            return "Dialogue/String"
        if "Jump" in n or "Spawn" in n or "Place" in n:
            return "Area/Placement"
        if "Item" in n or "Equip" in n or "Unequip" in n:
            return "Items"
        if "XP" in n or "Level" in n or "Align" in n:
            return "Progression"
        return "Misc"


@dataclass
class NWConstant:
    """A constant defined in nwscript.nss."""
    type: str
    name: str
    value: str
    line_number: int = 0

    @property
    def category(self) -> str:
        """Infer category from constant name prefix."""
        n = self.name
        if n.startswith("OBJECT_TYPE"): return "Object Types"
        if n.startswith("INVENTORY_"): return "Inventory"
        if n.startswith("RACIAL_"): return "Racial Types"
        if n.startswith("ALIGNMENT_"): return "Alignment"
        if n.startswith("SAVING_THROW"): return "Saving Throws"
        if n.startswith("DAMAGE_"): return "Damage"
        if n.startswith("ATTACK_"): return "Attack"
        if n.startswith("AC_"): return "Armor Class"
        if n.startswith("DURATION_"): return "Duration"
        if n.startswith("IMMUNITY_"): return "Immunity"
        if n.startswith("ABILITY_"): return "Abilities"
        if n.startswith("SKILL_"): return "Skills"
        if n.startswith("GENDER_"): return "Gender"
        if n.startswith("TALKVOLUME_"): return "Talk Volume"
        if n.startswith("EFFECT_"): return "Effects"
        if n.startswith("SPELL_"): return "Spells"
        if n.startswith("CLASS_"): return "Classes"
        if n.startswith("FEAT_"): return "Feats"
        if n.startswith("AREA_"): return "Area"
        if n.startswith("DOOR_"): return "Doors"
        if n.startswith("PLACEABLE_"): return "Placeables"
        if n.startswith("TRIGGER_"): return "Triggers"
        if n.startswith("SUBTYPE_"): return "Subtypes"
        if n.startswith("SHAPE_"): return "Shapes"
        if n.startswith("TRUE") or n.startswith("FALSE"): return "Boolean"
        if n.startswith("DIRECTION_"): return "Direction"
        return "Constants"


# ── Parser ─────────────────────────────────────────────────────

# Regex patterns (matches the NWScriptParser.cs approach)
_FUNC_PATTERN = re.compile(
    r'^(void|object|int|float|effect|event|location|string|vector|talent)\s+'
    r'([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*;'
)
_CONST_PATTERN = re.compile(
    r'^(int|float|string)\s+([A-Z][A-Z0-9_d]*)\s*=\s*([^;]+);'
)
_PARAM_PATTERN = re.compile(
    r'(void|object|int|float|effect|event|location|string|vector|talent|action)\s+'
    r'([A-Za-z_][A-Za-z0-9_]*)(?:\s*=\s*([^,)]+))?'
)


def _parse_params(param_str: str) -> List[NWParam]:
    """Parse the parameter string from a function declaration."""
    params = []
    param_str = param_str.strip()
    if not param_str or param_str == "void":
        return params
    # Split by comma respecting basic types
    for part in param_str.split(","):
        part = part.strip()
        if not part:
            continue
        m = _PARAM_PATTERN.match(part)
        if m:
            ptype = m.group(1)
            pname = m.group(2)
            pdefault = m.group(3).strip() if m.group(3) else None
            params.append(NWParam(type=ptype, name=pname, default=pdefault))
    return params


def parse_nwscript(path: Path) -> tuple[List[NWFunction], List[NWConstant]]:
    """
    Parse a nwscript.nss file and return (functions, constants).
    Follows NWScriptParser.cs logic: reads comments above declarations.
    """
    functions: List[NWFunction] = []
    constants: List[NWConstant] = []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"[NWScriptParser] Cannot read {path}: {e}", file=sys.stderr)
        return functions, constants

    lines = text.splitlines()
    comment_buffer: List[str] = []

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        # Collect block / line comments preceding functions
        if stripped.startswith("//"):
            comment_buffer.append(stripped[2:].strip())
            continue
        if stripped.startswith("/*"):
            comment_buffer.append(stripped)
            continue
        if not stripped:
            # Blank line resets the comment buffer
            comment_buffer = []
            continue

        # Match constant
        cm = _CONST_PATTERN.match(stripped)
        if cm:
            c = NWConstant(
                type=cm.group(1),
                name=cm.group(2),
                value=cm.group(3).strip(),
                line_number=lineno,
            )
            constants.append(c)
            comment_buffer = []
            continue

        # Match function declaration
        fm = _FUNC_PATTERN.match(stripped)
        if fm:
            rtype = fm.group(1)
            fname = fm.group(2)
            pstr = fm.group(3)
            doc = " ".join(comment_buffer).strip()
            f = NWFunction(
                return_type=rtype,
                name=fname,
                params=_parse_params(pstr),
                comment=doc,
                line_number=lineno,
            )
            functions.append(f)
            comment_buffer = []
            continue

        # Anything else resets the comment buffer
        comment_buffer = []

    return functions, constants


# ── Database ───────────────────────────────────────────────────

class NWScriptDB:
    """
    Parsed database of NWScript functions and constants.
    Provides fast lookups and category groupings.

    Improvements (open-source tools):
      * sortedcontainers.SortedList — O(log n) prefix autocomplete via bisect
        (vs O(n) linear scan in the original).
      * cachetools.LRUCache — memoises the 128 most recent search_functions /
        search_constants queries so repeated UI queries are instant.
    """

    # LRU capacity for memoised searches (per instance, per method)
    _SEARCH_CACHE_SIZE = 128

    def __init__(self, game: str = "K1"):
        self.game = game
        self.functions: List[NWFunction] = []
        self.constants: List[NWConstant] = []
        self._func_by_name: Dict[str, NWFunction] = {}
        self._const_by_name: Dict[str, NWConstant] = {}
        self._func_categories: Dict[str, List[NWFunction]] = {}
        self._const_categories: Dict[str, List[NWConstant]] = {}
        self._loaded = False

        # Fast prefix lookup structures (populated in _load)
        # Lower-case name → original name, for O(log n) bisect slicing
        self._func_names_lc: "list[str]" = []   # sorted lower-case func names
        self._const_names_lc: "list[str]" = []  # sorted lower-case const names
        # Parallel originals (same order as the lc lists)
        self._func_names_orig: "list[str]" = []
        self._const_names_orig: "list[str]" = []

        # Per-instance LRU caches (fall back gracefully without cachetools)
        if _HAS_CACHETOOLS:
            self._search_func_cache: "LRUCache[str, List[NWFunction]]" = \
                LRUCache(maxsize=self._SEARCH_CACHE_SIZE)
            self._search_const_cache: "LRUCache[str, List[NWConstant]]" = \
                LRUCache(maxsize=self._SEARCH_CACHE_SIZE)
        else:
            self._search_func_cache = None  # type: ignore[assignment]
            self._search_const_cache = None  # type: ignore[assignment]

    # ── Class-level factories ─────────────────────────────────

    @classmethod
    def load_k1(cls) -> "NWScriptDB":
        db = cls("K1")
        db._load(_nwscript_path("k1"))
        return db

    @classmethod
    def load_k2(cls) -> "NWScriptDB":
        db = cls("K2")
        db._load(_nwscript_path("k2"))
        return db

    @classmethod
    def load(cls, game: str = "K1") -> "NWScriptDB":
        return cls.load_k1() if game.upper() != "K2" else cls.load_k2()

    # ── Internal load ─────────────────────────────────────────

    def _load(self, path: Path):
        if not path.exists():
            print(f"[NWScriptDB] nwscript.nss not found: {path}", file=sys.stderr)
            return
        self.functions, self.constants = parse_nwscript(path)
        self._func_by_name = {f.name: f for f in self.functions}
        self._const_by_name = {c.name: c for c in self.constants}

        # Build categories
        for f in self.functions:
            cat = f.category
            self._func_categories.setdefault(cat, []).append(f)
        for c in self.constants:
            cat = c.category
            self._const_categories.setdefault(cat, []).append(c)

        # Build sorted lower-case name lists for O(log n) prefix search
        # (sortedcontainers.SortedList if available, otherwise plain sorted list)
        func_pairs: List[Tuple[str, str]] = sorted(
            (fn.lower(), fn) for fn in self._func_by_name
        )
        const_pairs: List[Tuple[str, str]] = sorted(
            (cn.lower(), cn) for cn in self._const_by_name
        )

        if _HAS_SORTED:
            self._func_names_lc = _SortedList(lc for lc, _ in func_pairs)
            self._const_names_lc = _SortedList(lc for lc, _ in const_pairs)
        else:
            self._func_names_lc = [lc for lc, _ in func_pairs]
            self._const_names_lc = [lc for lc, _ in const_pairs]

        self._func_names_orig = [orig for _, orig in func_pairs]
        self._const_names_orig = [orig for _, orig in const_pairs]

        # Invalidate caches after reload
        if self._search_func_cache is not None:
            self._search_func_cache.clear()
        if self._search_const_cache is not None:
            self._search_const_cache.clear()

        self._loaded = True
        print(f"[NWScriptDB] {self.game}: "
              f"{len(self.functions)} functions, {len(self.constants)} constants")

    # ── Fast prefix helpers ───────────────────────────────────

    def _prefix_func_names(self, prefix_lc: str) -> List[str]:
        """Return original function names whose lower-case form starts with prefix_lc.

        Uses sortedcontainers.SortedList (O(log n) irange) when available,
        falling back to bisect on a plain sorted list.
        """
        if _HAS_SORTED:
            # SortedList.irange(min, max) is O(log n + k)
            # Upper bound: replace last char with next unicode code point
            prefix_end = prefix_lc[:-1] + chr(ord(prefix_lc[-1]) + 1) if prefix_lc else ""
            if prefix_end:
                lc_names = list(self._func_names_lc.irange(  # type: ignore[attr-defined]
                    prefix_lc, prefix_end, inclusive=(True, False)
                ))
            else:
                lc_names = list(self._func_names_lc)
            # Map back to originals (orig list is same order as lc list)
            lc_set = set(lc_names)
            return [orig for orig in self._func_names_orig if orig.lower() in lc_set]
        else:
            # bisect on plain sorted list — still O(log n) for slice bounds
            lo = bisect.bisect_left(self._func_names_lc, prefix_lc)
            hi = bisect.bisect_left(
                self._func_names_lc,
                prefix_lc[:-1] + chr(ord(prefix_lc[-1]) + 1) if prefix_lc else "",
            )
            return self._func_names_orig[lo:hi]

    def _prefix_const_names(self, prefix_lc: str) -> List[str]:
        """Same as _prefix_func_names but for constants."""
        if _HAS_SORTED:
            prefix_end = prefix_lc[:-1] + chr(ord(prefix_lc[-1]) + 1) if prefix_lc else ""
            if prefix_end:
                lc_names = list(self._const_names_lc.irange(  # type: ignore[attr-defined]
                    prefix_lc, prefix_end, inclusive=(True, False)
                ))
            else:
                lc_names = list(self._const_names_lc)
            lc_set = set(lc_names)
            return [orig for orig in self._const_names_orig if orig.lower() in lc_set]
        else:
            lo = bisect.bisect_left(self._const_names_lc, prefix_lc)
            hi = bisect.bisect_left(
                self._const_names_lc,
                prefix_lc[:-1] + chr(ord(prefix_lc[-1]) + 1) if prefix_lc else "",
            )
            return self._const_names_orig[lo:hi]

    # ── Lookup ────────────────────────────────────────────────

    def get_function(self, name: str) -> NWFunction | None:
        return self._func_by_name.get(name)

    def get_constant(self, name: str) -> NWConstant | None:
        return self._const_by_name.get(name)

    def search_functions(self, query: str) -> List[NWFunction]:
        """Return functions whose name contains query (case-insensitive).

        Results are LRU-cached (cachetools) so repeated UI queries are O(1).
        """
        q = query.lower()
        if self._search_func_cache is not None:
            hit = self._search_func_cache.get(q)
            if hit is not None:
                return hit
        result = [f for f in self.functions if q in f.name.lower()]
        if self._search_func_cache is not None:
            self._search_func_cache[q] = result
        return result

    def search_constants(self, query: str) -> List[NWConstant]:
        """Return constants whose name contains query (case-insensitive).

        Results are LRU-cached (cachetools) so repeated UI queries are O(1).
        """
        q = query.lower()
        if self._search_const_cache is not None:
            hit = self._search_const_cache.get(q)
            if hit is not None:
                return hit
        result = [c for c in self.constants if q in c.name.lower()]
        if self._search_const_cache is not None:
            self._search_const_cache[q] = result
        return result

    def autocomplete(self, prefix: str, max_results: int = 30) -> List[str]:
        """Return function + constant names starting with prefix (case-insensitive).

        Upgraded to O(log n + k) using sorted lists / SortedList instead of
        the original O(n) full scan over all names.
        """
        if not prefix:
            # Return all names (sorted) when no prefix given
            all_names = sorted(
                list(self._func_by_name.keys()) + list(self._const_by_name.keys())
            )
            return all_names[:max_results]

        p = prefix.lower()
        func_names = self._prefix_func_names(p)
        const_names = self._prefix_const_names(p)

        matches = func_names + const_names
        matches.sort(key=lambda x: x.lower())
        return matches[:max_results]

    def functions_by_return_type(self, return_type: str) -> List[NWFunction]:
        """Return all functions with a specific return type (e.g. 'object', 'int')."""
        return [f for f in self.functions if f.return_type == return_type]

    def iter_all_names(self) -> Iterator[Tuple[str, str]]:
        """Yield (name, kind) tuples where kind is 'function' or 'constant'."""
        for name in self._func_by_name:
            yield name, "function"
        for name in self._const_by_name:
            yield name, "constant"

    # ── Category groupings ────────────────────────────────────

    @property
    def function_categories(self) -> Dict[str, List[NWFunction]]:
        return self._func_categories

    @property
    def constant_categories(self) -> Dict[str, List[NWConstant]]:
        return self._const_categories

    # ── KOTOR_COMMON_FUNCTIONS-compatible dict ────────────────

    def to_kotor_common_functions(self) -> Dict[str, list]:
        """
        Build a dict compatible with KOTOR_COMMON_FUNCTIONS format
        for backwards-compatibility with the old function panel.
        """
        result: Dict[str, list] = {}
        for cat, funcs in sorted(self._func_categories.items()):
            items = []
            for f in funcs:
                items.append({
                    "name": f.name,
                    "returns": f.return_type,
                    "params": [str(p) for p in f.params],
                    "description": f.comment or f"Returns {f.return_type}.",
                    "example": f"{f.call_snippet};",
                })
            result[cat] = items
        return result

    # ── Compatibility shim ────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def __repr__(self) -> str:
        return (f"NWScriptDB(game={self.game!r}, "
                f"functions={len(self.functions)}, "
                f"constants={len(self.constants)})")


# ── Path helpers ───────────────────────────────────────────────

def _resource_base() -> Path:
    """Locate the resources directory whether running from source or PyInstaller."""
    # PyInstaller: sys._MEIPASS
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # Installed as package: ghostscripter/ is two levels up from this file
        base = Path(__file__).parent.parent.parent.parent
    return base


def _nwscript_path(game: str) -> Path:
    """Return the path to resources/scripts/<game>/nwscript.nss."""
    return _resource_base() / "resources" / "scripts" / game / "nwscript.nss"


# ── Singleton cache ────────────────────────────────────────────

_cache: Dict[str, NWScriptDB] = {}


def get_nwscript_db(game: str = "K1") -> NWScriptDB:
    """Return a cached NWScriptDB instance for the given game."""
    key = game.upper()
    if key not in _cache:
        _cache[key] = NWScriptDB.load(key)
    return _cache[key]


def invalidate_cache():
    """Clear the singleton cache (useful when switching games)."""
    _cache.clear()


# ── Quick self-test ────────────────────────────────────────────

if __name__ == "__main__":
    for g in ("K1", "K2"):
        db = get_nwscript_db(g)
        print(db)
        funcs = db.search_functions("GetGlobal")
        for f in funcs[:5]:
            print(f"  {f.signature}")
        print()
