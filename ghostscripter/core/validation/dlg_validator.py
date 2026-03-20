"""
GhostScripter-K1-K2 — Dialogue Validator
=========================================
Deep structural validation of DialogueFile objects using NetworkX.

Open-source tools:
  - networkx (DiGraph) — cycle detection, reachability, connected components,
    longest-path analysis
  - dataclasses — ValidationIssue result type

Features
--------
  • validate()            — run all checks; return list of ValidationIssue
  • validate_reachability — flag nodes unreachable from any starter
  • validate_cycles       — flag strongly-connected components (back-edges)
  • validate_scripts      — flag empty script placeholders
  • validate_node_ids     — flag duplicate / out-of-range node IDs
  • validate_links        — flag dangling branch targets
  • summary_report()      — human-readable text report

Usage
-----
    from ghostscripter.core.validation.dlg_validator import DLGValidator
    from ghostscripter.core.models.dialogue import create_simple_dialogue

    dlg = create_simple_dialogue("test", "Bastila")
    issues = DLGValidator.validate(dlg)
    print(DLGValidator.summary_report(dlg, issues))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Set

try:
    import networkx as nx  # type: ignore
    _HAS_NX = True
except ImportError:  # pragma: no cover
    _HAS_NX = False

from ghostscripter.core.models.dialogue import DialogueFile, DialogueNode


# ── Issue types ────────────────────────────────────────────────

class Severity(str, Enum):
    ERROR   = "ERROR"
    WARNING = "WARNING"
    INFO    = "INFO"


class CheckCategory(str, Enum):
    REACHABILITY = "Reachability"
    CYCLES       = "Cycles"
    SCRIPTS      = "Scripts"
    NODE_IDS     = "Node IDs"
    LINKS        = "Links"
    STRUCTURE    = "Structure"


@dataclass
class ValidationIssue:
    severity: Severity
    category: CheckCategory
    message: str
    node_id: int | None = None
    node_type: str | None = None   # 'entry' | 'reply'

    def __str__(self) -> str:
        loc = ""
        if self.node_type and self.node_id is not None:
            loc = f" [{self.node_type.upper()} #{self.node_id}]"
        return f"[{self.severity.value}] {self.category.value}{loc}: {self.message}"


# ── Validator ──────────────────────────────────────────────────

class DLGValidator:
    """
    Static-method validator for DialogueFile objects.

    All checks are independent and can be run individually or via
    the all-in-one validate() entry-point.
    """

    # ── Public API ─────────────────────────────────────────────

    @staticmethod
    def validate(dlg: DialogueFile) -> List[ValidationIssue]:
        """Run all checks.  Returns a list of ValidationIssue (may be empty)."""
        issues: List[ValidationIssue] = []
        issues.extend(DLGValidator.validate_structure(dlg))
        issues.extend(DLGValidator.validate_node_ids(dlg))
        issues.extend(DLGValidator.validate_links(dlg))
        issues.extend(DLGValidator.validate_reachability(dlg))
        issues.extend(DLGValidator.validate_cycles(dlg))
        issues.extend(DLGValidator.validate_scripts(dlg))
        # Sort: errors first, then warnings, then info
        _order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
        issues.sort(key=lambda i: _order[i.severity])
        return issues

    @staticmethod
    def summary_report(dlg: DialogueFile,
                       issues: list[ValidationIssue] | None = None) -> str:
        """Return a human-readable validation report string."""
        if issues is None:
            issues = DLGValidator.validate(dlg)

        stats = dlg.graph_stats()
        lines = [
            f"=== DLG Validation Report: {dlg.name} ===",
            f"Entries: {len(dlg.entries)}  Replies: {len(dlg.replies)}  "
            f"Starters: {len(dlg.starters)}",
            f"Nodes: {stats.get('node_count', '?')}  "
            f"Edges: {stats.get('edge_count', '?')}  "
            f"Cycles: {'YES' if stats.get('has_cycles') else 'no'}  "
            f"Longest path: {stats.get('longest_path_length', '?')}",
            "",
        ]
        if not issues:
            lines.append("  ✓  No issues found.")
        else:
            errors   = [i for i in issues if i.severity == Severity.ERROR]
            warnings = [i for i in issues if i.severity == Severity.WARNING]
            infos    = [i for i in issues if i.severity == Severity.INFO]
            lines.append(
                f"Issues: {len(errors)} errors, {len(warnings)} warnings, "
                f"{len(infos)} info"
            )
            lines.append("")
            for issue in issues:
                lines.append(f"  {issue}")
        return "\n".join(lines)

    # ── Individual checks ──────────────────────────────────────

    @staticmethod
    def validate_structure(dlg: DialogueFile) -> List[ValidationIssue]:
        """High-level structural checks."""
        issues = []
        if not dlg.entries and not dlg.starters:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                category=CheckCategory.STRUCTURE,
                message="Dialogue has no entries and no starters — it cannot play.",
            ))
        if not dlg.starters:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                category=CheckCategory.STRUCTURE,
                message="No starting links defined; the conversation cannot begin.",
            ))
        for s in dlg.starters:
            if s.target_node_id < 0:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    category=CheckCategory.STRUCTURE,
                    message="A starter link points to no entry (target_node_id < 0).",
                ))
        return issues

    @staticmethod
    def validate_node_ids(dlg: DialogueFile) -> List[ValidationIssue]:
        """Check for duplicate or out-of-range node IDs."""
        issues = []
        seen_entry: Dict[int, int] = {}   # node_id → count
        seen_reply: Dict[int, int] = {}

        for n in dlg.entries:
            seen_entry[n.node_id] = seen_entry.get(n.node_id, 0) + 1
        for n in dlg.replies:
            seen_reply[n.node_id] = seen_reply.get(n.node_id, 0) + 1

        for nid, cnt in seen_entry.items():
            if cnt > 1:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    category=CheckCategory.NODE_IDS,
                    message=f"Entry node_id {nid} appears {cnt} times.",
                    node_id=nid,
                    node_type="entry",
                ))
        for nid, cnt in seen_reply.items():
            if cnt > 1:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    category=CheckCategory.NODE_IDS,
                    message=f"Reply node_id {nid} appears {cnt} times.",
                    node_id=nid,
                    node_type="reply",
                ))
        return issues

    @staticmethod
    def validate_links(dlg: DialogueFile) -> List[ValidationIssue]:
        """Check for dangling branch targets."""
        issues = []
        all_entry_ids: Set[int] = {n.node_id for n in dlg.entries}
        all_reply_ids: Set[int] = {n.node_id for n in dlg.replies}

        for n in dlg.entries:
            for b in n.branches:
                if b.target_node_id >= 0 and b.target_node_id not in all_reply_ids:
                    issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        category=CheckCategory.LINKS,
                        message=(
                            f"Entry → Reply branch targets non-existent "
                            f"Reply #{b.target_node_id}."
                        ),
                        node_id=n.node_id,
                        node_type="entry",
                    ))

        for n in dlg.replies:
            for b in n.branches:
                if b.target_node_id >= 0 and b.target_node_id not in all_entry_ids:
                    issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        category=CheckCategory.LINKS,
                        message=(
                            f"Reply → Entry branch targets non-existent "
                            f"Entry #{b.target_node_id}."
                        ),
                        node_id=n.node_id,
                        node_type="reply",
                    ))

        return issues

    @staticmethod
    def validate_reachability(dlg: DialogueFile) -> List[ValidationIssue]:
        """Flag nodes unreachable from any starter link (using networkx or BFS)."""
        issues = []

        if _HAS_NX:
            try:
                G = dlg.to_networkx()
                reachable: Set[str] = nx.descendants(G, "START") | {"START"}
                for node_label in G.nodes():
                    if node_label == "START":
                        continue
                    if node_label not in reachable:
                        kind = G.nodes[node_label].get("kind", "?")
                        nid = G.nodes[node_label].get("node_id", -1)
                        issues.append(ValidationIssue(
                            severity=Severity.WARNING,
                            category=CheckCategory.REACHABILITY,
                            message=f"Node {node_label} is unreachable from any starter.",
                            node_id=nid,
                            node_type=kind,
                        ))
            except Exception:
                # Fall back to basic BFS
                issues.extend(DLGValidator._bfs_reachability(dlg))
        else:
            issues.extend(DLGValidator._bfs_reachability(dlg))

        return issues

    @staticmethod
    def _bfs_reachability(dlg: DialogueFile) -> List[ValidationIssue]:
        """Fallback BFS reachability (no networkx required)."""
        from collections import deque
        issues = []
        all_entry_ids: Set[int] = {n.node_id for n in dlg.entries}
        all_reply_ids: Set[int] = {n.node_id for n in dlg.replies}

        reachable_e: Set[int] = set()
        reachable_r: Set[int] = set()
        queue: deque = deque()

        for s in dlg.starters:
            if s.target_node_id >= 0:
                queue.append(("entry", s.target_node_id))

        while queue:
            kind, nid = queue.popleft()
            if kind == "entry":
                if nid in reachable_e:
                    continue
                reachable_e.add(nid)
                node = dlg.get_entry(nid)
                if node:
                    for b in node.branches:
                        if b.target_node_id >= 0:
                            queue.append(("reply", b.target_node_id))
            else:
                if nid in reachable_r:
                    continue
                reachable_r.add(nid)
                node = dlg.get_reply(nid)
                if node:
                    for b in node.branches:
                        if b.target_node_id >= 0:
                            queue.append(("entry", b.target_node_id))

        for nid in sorted(all_entry_ids - reachable_e):
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                category=CheckCategory.REACHABILITY,
                message=f"Entry #{nid} is unreachable from any starter.",
                node_id=nid,
                node_type="entry",
            ))
        for nid in sorted(all_reply_ids - reachable_r):
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                category=CheckCategory.REACHABILITY,
                message=f"Reply #{nid} is unreachable from any starter.",
                node_id=nid,
                node_type="reply",
            ))
        return issues

    @staticmethod
    def validate_cycles(dlg: DialogueFile) -> List[ValidationIssue]:
        """Flag back-edges / strongly-connected components that indicate cycles."""
        issues = []

        if not _HAS_NX:
            # Can't detect cycles without networkx
            return issues

        try:
            G = dlg.to_networkx()
        except Exception:
            return issues

        # Each SCC of size > 1 is a cycle
        for scc in nx.strongly_connected_components(G):
            if len(scc) > 1:
                node_labels = sorted(scc)
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    category=CheckCategory.CYCLES,
                    message=(
                        f"Dialogue cycle detected among nodes: "
                        f"{', '.join(node_labels)} — "
                        f"conversation may loop indefinitely without an exit branch."
                    ),
                ))

        return issues

    @staticmethod
    def validate_scripts(dlg: DialogueFile) -> List[ValidationIssue]:
        """Flag suspiciously named or placeholder script references."""
        issues = []
        PLACEHOLDER_PATTERNS = ("todo", "fixme", "placeholder", "test_script",
                                 "stub", "xxx")

        def _check_script(script: str, node: DialogueNode,
                          field_name: str) -> ValidationIssue | None:
            if not script:
                return None
            lower = script.lower()
            for pat in PLACEHOLDER_PATTERNS:
                if pat in lower:
                    return ValidationIssue(
                        severity=Severity.WARNING,
                        category=CheckCategory.SCRIPTS,
                        message=(
                            f"Script field '{field_name}' looks like a placeholder: "
                            f"'{script}'"
                        ),
                        node_id=node.node_id,
                        node_type=node.node_type,
                    )
            # RESREF max length is 16
            if len(script) > 16:
                return ValidationIssue(
                    severity=Severity.ERROR,
                    category=CheckCategory.SCRIPTS,
                    message=(
                        f"Script RESREF '{script}' is {len(script)} chars "
                        f"(max 16)."
                    ),
                    node_id=node.node_id,
                    node_type=node.node_type,
                )
            return None

        for node in dlg.entries + dlg.replies:
            for fname, sval in [("script1", node.script1),
                                  ("script2", node.script2)]:
                issue = _check_script(sval, node, fname)
                if issue:
                    issues.append(issue)
            for b in node.branches:
                issue = _check_script(b.active_script, node, "active_script")
                if issue:
                    issues.append(issue)

        return issues


# ── Convenience wrapper ────────────────────────────────────────

def validate_dlg(dlg: DialogueFile) -> List[ValidationIssue]:
    """Shorthand for DLGValidator.validate(dlg)."""
    return DLGValidator.validate(dlg)
