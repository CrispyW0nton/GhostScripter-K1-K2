"""
GhostScripter-K1-K2 — Dialogue Model
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Any, Tuple


@dataclass
class DialogueConditional:
    condition_type: str = "global_var"  # global_var | quest_state | skill_check | alignment
    parameter1: str = ""
    parameter2: Optional[str] = None
    operator: str = "=="          # == | != | > | < | >= | <=
    script_ref: Optional[str] = None

    def describe(self) -> str:
        if self.script_ref:
            return f"Script: {self.script_ref}"
        return f"{self.parameter1} {self.operator} {self.parameter2 or '?'}"


@dataclass
class DialogueAction:
    action_type: str = "set_global"  # set_global | run_script | quest_advance | etc
    target: str = ""
    value: Any = None
    script_file: Optional[str] = None

    def describe(self) -> str:
        if self.script_file:
            return f"Run: {self.script_file}"
        return f"Set {self.target} = {self.value}"


@dataclass
class DialogueBranch:
    branch_id: int = 0
    text: str = ""
    text_strref: int = -1
    conditionals: List[DialogueConditional] = field(default_factory=list)
    target_node_id: int = -1


@dataclass
class DialogueNode:
    node_id: int = 0
    speaker: str = ""            # NPC tag or "Player"
    text: str = ""
    text_strref: int = -1
    voice_over: Optional[str] = None

    position_x: float = 0.0
    position_y: float = 0.0

    conditionals: List[DialogueConditional] = field(default_factory=list)
    script_actions: List[DialogueAction] = field(default_factory=list)
    wait_flags: int = 0
    camera_id: int = -1
    camera_model: Optional[str] = None

    branches: List[DialogueBranch] = field(default_factory=list)
    parent_node_id: Optional[int] = None

    quest_update: Optional[str] = None
    alignment_check: Optional[Tuple[str, int]] = None

    def add_branch(self, text: str, target_node_id: int = -1) -> DialogueBranch:
        branch = DialogueBranch(
            branch_id=len(self.branches),
            text=text,
            target_node_id=target_node_id,
        )
        self.branches.append(branch)
        return branch

    def short_text(self) -> str:
        return (self.text[:60] + "…") if len(self.text) > 60 else self.text


@dataclass
class DialogueFile:
    name: str = ""
    file_path: Optional[Path] = None

    nodes: List[DialogueNode] = field(default_factory=list)
    start_node_id: int = 0

    speaker_tag: str = ""
    quest_link: Optional[str] = None

    def add_node(self, node: DialogueNode) -> int:
        node.node_id = len(self.nodes)
        self.nodes.append(node)
        return node.node_id

    def remove_node(self, node_id: int):
        self.nodes = [n for n in self.nodes if n.node_id != node_id]
        # Clean up branch references
        for node in self.nodes:
            node.branches = [b for b in node.branches if b.target_node_id != node_id]

    def get_node(self, node_id: int) -> Optional[DialogueNode]:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def get_root_node(self) -> Optional[DialogueNode]:
        return self.get_node(self.start_node_id)

    def get_player_nodes(self) -> List[DialogueNode]:
        return [n for n in self.nodes if n.speaker == "Player"]

    def get_npc_nodes(self) -> List[DialogueNode]:
        return [n for n in self.nodes if n.speaker != "Player"]

    def validate_tree(self) -> List[str]:
        """Return list of validation issues."""
        issues = []
        node_ids = {n.node_id for n in self.nodes}

        for node in self.nodes:
            for branch in node.branches:
                if branch.target_node_id not in node_ids and branch.target_node_id != -1:
                    issues.append(
                        f"Node {node.node_id}: branch targets non-existent node {branch.target_node_id}"
                    )
            if not node.text.strip():
                issues.append(f"Node {node.node_id}: empty text")

        return issues

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file_path": str(self.file_path) if self.file_path else None,
            "node_count": len(self.nodes),
            "speaker_tag": self.speaker_tag,
            "quest_link": self.quest_link,
        }

    def __str__(self):
        return f"DialogueFile({self.name!r}, {len(self.nodes)} nodes)"


# ── Factory helpers ───────────────────────────────────────────

def create_simple_dialogue(name: str, npc_tag: str) -> DialogueFile:
    """Create a minimal 2-node dialogue skeleton."""
    dlg = DialogueFile(name=name, speaker_tag=npc_tag)

    # NPC greeting
    greeting = DialogueNode(
        node_id=0,
        speaker=npc_tag,
        text="Greetings, traveler.",
    )
    # Player response
    reply = DialogueNode(
        node_id=1,
        speaker="Player",
        text="Hello.",
    )
    # End node
    end = DialogueNode(
        node_id=2,
        speaker=npc_tag,
        text="May the Force be with you.",
    )

    greeting.add_branch("Hello.", target_node_id=2)
    reply.parent_node_id = 0
    end.parent_node_id = 1

    dlg.nodes = [greeting, reply, end]
    dlg.start_node_id = 0
    return dlg
