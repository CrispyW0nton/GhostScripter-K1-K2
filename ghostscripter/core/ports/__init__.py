"""
GhostScripter — Core Ports (Abstract Interfaces)
=================================================
Implements the Ports & Adapters (Hexagonal Architecture) pattern from
"Balancing Coupling in Software Design" by Vlad Khononov.

Coupling model applied
----------------------
  Layer distance  : HIGH  (MCP tools → Core readers, UI widgets → Core models)
  Integration strength : CONTRACT (this module)  — only interfaces, no
                         implementation details, no concrete class knowledge
  Volatility       : LOW  (these protocols are the stable contract)

  ∴ Balance = (LOW strength XOR HIGH distance) OR NOT LOW volatility = TRUE ✓

These protocols (structural subtypes via typing.Protocol) define what each
subsystem *provides* to callers without coupling callers to concrete
implementations.  They can be satisfied by the real implementations (duck-
typed) or by test doubles, with zero inheritance required.

Principle: "Deep Modules" (Parnas, 1984 / Ousterhout, 2021)
  — A large hidden complexity behind a small, stable surface.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Protocol, runtime_checkable


# ── Resource access port ───────────────────────────────────────────────────────

@runtime_checkable
class ResourceReaderPort(Protocol):
    """
    Contract for any component that can locate and read KotOR binary resources.

    Downstream consumers (MCP tools, UI widgets, tests) depend only on this
    interface — never on ResourceManager's concrete implementation.  Fulfils
    Contract Coupling at high distance.
    """

    def read(self, filename: str) -> bytes | None:
        """Return the raw bytes of *filename* (e.g. 'appearance.2da'), or None."""
        ...

    def list_by_type(self, extension: str) -> List[Any]:
        """Return ResourceEntry-like objects for all resources of the given type."""
        ...

    def load_game(self, game_dir: Path) -> bool:
        """Load the game installation at *game_dir*.  Returns True on success."""
        ...


# ── GFF reader port ────────────────────────────────────────────────────────────

@runtime_checkable
class GFFReaderPort(Protocol):
    """
    Contract for parsing GFF V3.2 binary data into a Python dict.

    Hides the binary layout, field-type dispatch, and struct traversal
    from all callers — they only need to know the dict they get back.
    """

    def parse(self) -> Dict[str, Any]:
        """Parse the GFF binary and return a field dict."""
        ...


# ── 2DA port ───────────────────────────────────────────────────────────────────

@runtime_checkable
class TwoDAPort(Protocol):
    """
    Contract for reading KotOR 2DA (two-dimensional array) tables.

    Callers must not care whether the underlying file is text (V2.0) or
    binary (V2.b); the port hides that decision.
    """

    @property
    def columns(self) -> List[str]:
        """Ordered list of column names."""
        ...

    @property
    def rows(self) -> List[Any]:
        """Ordered list of row objects, each exposing .label and .data dict."""
        ...

    def get_cell(self, row: int | str, column: str) -> str | None:
        """
        Return the cell value at (row, column).

        *row* may be an integer index or a string label.
        Returns None when the row/column pair does not exist.
        """
        ...


# ── Dialogue port ──────────────────────────────────────────────────────────────

@runtime_checkable
class DialoguePort(Protocol):
    """
    Contract for a loaded KotOR dialogue (DLG).

    Callers should only observe entries, replies, and starters; they must
    not depend on the internal GFF field numbering or binary layout.
    """

    @property
    def entries(self) -> List[Any]:
        """NPC-spoken dialogue nodes."""
        ...

    @property
    def replies(self) -> List[Any]:
        """Player-choice dialogue nodes."""
        ...

    @property
    def starters(self) -> List[Any]:
        """Branch links that define the root of the conversation."""
        ...


# ── Journal port ───────────────────────────────────────────────────────────────

@runtime_checkable
class JournalPort(Protocol):
    """
    Contract for a loaded KotOR journal (JRL).
    """

    @property
    def categories(self) -> List[Any]:
        """Quest categories, each exposing .tag, .name, and .entries."""
        ...


# ── NWScript database port ─────────────────────────────────────────────────────

@runtime_checkable
class NWScriptDBPort(Protocol):
    """
    Contract for the NWScript function/constant database.

    Separates the search / autocomplete behaviour from the nwscript.nss
    parsing implementation.
    """

    def search_functions(self, query: str) -> List[Any]:
        """Return functions whose names contain *query* (case-insensitive)."""
        ...

    def search_constants(self, query: str) -> List[Any]:
        """Return constants whose names contain *query* (case-insensitive)."""
        ...

    def get_function(self, name: str) -> Any | None:
        """Return the function with exactly this *name*, or None."""
        ...

    def autocomplete(self, prefix: str, max_results: int = 30) -> List[str]:
        """Return names that start with *prefix*, sorted alphabetically."""
        ...


# ── Serialiser ports ───────────────────────────────────────────────────────────

@runtime_checkable
class DLGSerialiserPort(Protocol):
    """
    Contract for reading *or* writing DLG binary data.
    Keeps the MCP writeDLG / readDLG tools independent of GFF internals.
    """

    def export(self, dialogue: Any, target_game: str = "K1") -> bytes:
        """Serialise *dialogue* to GFF V3.2 binary bytes."""
        ...


@runtime_checkable
class GFFWriterPort(Protocol):
    """
    Minimal contract for building a generic GFF binary.
    """

    def build(self) -> bytes:
        """Return the fully serialised GFF bytes."""
        ...
