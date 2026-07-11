"""
GhostScripter-K1-K2 — Dialogue Model
Full DLG data model matching the GFF spec used by KotOR 1 & 2.

Field names and structure reverse-engineered from:
  - TK102's DLGEditor v2.3.4 (dlgeditor_234.pl)
  - PyKotor (pykotor/resource/generics/dlg/nodes.py, base.py, links.py)
  - xoreos-tools GFF3 reader
  - KotOR engine LoadDialog / LoadDialogBase addresses

GFF top-level fields (DLG):
  StartingList  LIST  — initial entry links (Active script, Index)
  EntryList     LIST  — NPC lines (DLGEntry)
  ReplyList     LIST  — Player choices (DLGReply)
  EndConversation   RESREF
  EndConverAbort    RESREF
  Skippable         BYTE
  DelayEntry        DWORD
  DelayReply        DWORD
  AmbientTrack      RESREF
  AnimatedCut       BYTE
  CameraModel       RESREF
  ConversationType  INT   (0=Human, 1=Computer, 2=Other)
  ComputerType      BYTE  (0=Modern, 1=Ancient)
  OldHitCheck       BYTE
  UnequipItems      BYTE
  UnequipHItem      BYTE
  NumWords          DWORD (TSL)
  StuntList         LIST  (TSL)

Entry/Reply node fields:
  Text              CEXOLOCSTRING
  Script            RESREF   (script1 — fired on node enter)
  Script2           RESREF   (TSL only)
  Speaker           CEXOSTRING (Entry only)
  Listener          CEXOSTRING
  VO_ResRef         RESREF
  Sound             RESREF
  SoundExists       BYTE
  AnimList          LIST  [{Participant CEXOSTRING, Animation DWORD}]
  Delay             DWORD  (-1 = no delay)
  WaitFlags         DWORD
  Quest             CEXOSTRING
  QuestEntry        DWORD
  PlotIndex         INT    (-1 = none)
  PlotXPPercentage  FLOAT
  FadeType          BYTE
  FadeColor         VECTOR
  FadeDelay         FLOAT
  FadeLength        FLOAT
  CameraAngle       INT
  CameraID          INT    (TSL)
  CameraAnimation   DWORD  (TSL)
  CamFieldOfView    FLOAT  (TSL)
  CamHeightOffset   FLOAT  (TSL)
  CamVidEffect      INT    (TSL)
  TarHeightOffset   FLOAT  (TSL)
  Comment           CEXOSTRING (editor only)
  NodeUnskippable   BYTE   (TSL)
  AlienRaceNode     INT    (TSL)
  Emotion           INT    (TSL)
  FacialAnim        INT    (TSL)
  NodeID            INT    (TSL)
  PostProcNode      INT    (TSL)
  RecordVO          BYTE   (TSL)
  RecordNoVOOverri  BYTE   (TSL)
  VOTextChanged     BYTE   (TSL)
  ActionParam1-5    INT    (TSL script1 params)
  ActionParamStrA   CEXOSTRING (TSL)
  ActionParam1b-5b  INT    (TSL script2 params)
  ActionParamStrB   CEXOSTRING (TSL)

Link fields (inside RepliesList / EntriesList / StartingList struct):
  Index             DWORD  — index into EntryList or ReplyList
  Active            RESREF — conditional script (show/hide this option)
  Active2           RESREF (TSL)
  IsChild           BYTE   — 1 = shared node (same node, multiple parents)
  LinkComment       CEXOSTRING (editor only)
  DisplayInactive   BYTE   (TSL)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple


# ``Index`` fields in DLG link structs are unsigned DWORDs.  BioWare uses
# 0xFFFFFFFF as the on-disk sentinel for an explicit end-of-conversation link;
# the editor model exposes that value as the much safer/saner Python value -1.
END_NODE_ID = -1

# ── Optional graph-analysis dependency ────────────────────────
try:
    import networkx as nx  # type: ignore
    _HAS_NX = True
except ImportError:  # pragma: no cover
    _HAS_NX = False


# ── Animation reference ────────────────────────────────────────

@dataclass
class DLGAnimation:
    """AnimList entry: Participant + Animation ID."""
    participant: str = ""  # CEXOSTRING — NPC tag or "PLAYER"
    animation_id: int = 0  # DWORD — animation row from animations.2da
    # Source GFF struct retained for lossless round-tripping of fields newer
    # than this editor understands.  It is deliberately not part of equality
    # or repr and is populated only for imported files.
    _raw_gff: Any = field(default=None, repr=False, compare=False)
    _source_state: Dict[str, Any] = field(
        default_factory=dict, repr=False, compare=False,
    )


# ── Link (branch connection) ──────────────────────────────────

@dataclass
class DialogueBranch:
    """
    Represents a link between a node and its child.
    In GFF: a struct inside EntriesList or RepliesList.

    Fields written to GFF:
      Index          DWORD
      Active         RESREF  (conditional script)
      Active2        RESREF  (TSL)
      IsChild        BYTE    (1 = shared/copy node)
      LinkComment    CEXOSTRING
      DisplayInactive BYTE  (TSL)
    """
    branch_id: int = 0
    # index into the target list (EntryList or ReplyList)
    target_node_id: int = -1
    # Response text (editor-visible label; NOT written to GFF — comes from target node)
    text: str = ""
    # GFF fields
    active_script: str = ""       # RESREF — conditional script
    active_script2: str = ""      # RESREF — TSL second conditional
    is_child: bool = False        # shared node reference
    link_comment: str = ""        # editor comment
    display_inactive: bool = False  # TSL
    _raw_gff: Any = field(default=None, repr=False, compare=False)
    _source_state: Dict[str, Any] = field(
        default_factory=dict, repr=False, compare=False,
    )

    @property
    def is_end(self) -> bool:
        """Whether this link explicitly terminates the conversation."""
        return self.target_node_id < 0

    def describe(self) -> str:
        active = f" [if {self.active_script}]" if self.active_script else ""
        target = f"→ Node {self.target_node_id}" if self.target_node_id >= 0 else "→ END"
        return f"Branch {self.branch_id}: {target}{active}"


# ── Conditional and Action (legacy editor helpers) ─────────────

@dataclass
class DialogueConditional:
    script: str = ""
    script2: str = ""      # TSL
    param1: int = 0
    param2: int = 0
    param3: int = 0
    param4: int = 0
    param5: int = 0
    param_str: str = ""

    def describe(self) -> str:
        return f"Cond: {self.script}"


@dataclass
class DialogueAction:
    script: str = ""
    script2: str = ""      # TSL
    param1: int = 0
    param2: int = 0
    param3: int = 0
    param4: int = 0
    param5: int = 0
    param_str: str = ""

    def describe(self) -> str:
        return f"Action: {self.script}"


# ── Dialogue Node ─────────────────────────────────────────────

@dataclass
class DialogueNode:
    """
    One line of dialogue — either an NPC entry or a player reply.
    All GFF field names are preserved as attributes.
    """

    node_id: int = 0
    node_type: str = "entry"      # "entry" | "reply"
    speaker: str = ""             # CEXOSTRING (entry only)
    listener: str = ""            # CEXOSTRING
    text: str = ""                # CEXOLOCSTRING (English substring)
    text_strref: int = -1         # TLK string reference (-1 = custom text)

    # Scripts
    script1: str = ""             # RESREF — Script
    script2: str = ""             # RESREF — Script2 (TSL)

    # Audio
    vo_resref: str = ""           # RESREF — voice-over
    sound: str = ""               # RESREF — sound effect
    sound_exists: int = 0         # BYTE

    # Animations
    animations: List[DLGAnimation] = field(default_factory=list)

    # Timing
    delay: int = -1               # DWORD — ms (-1 = engine default)
    wait_flags: int = 0           # DWORD

    # Quest / plot
    quest: str = ""               # CEXOSTRING
    quest_entry: int = 0          # DWORD
    plot_index: int = -1          # INT (-1 = none)
    plot_xp_percentage: float = 1.0  # FLOAT

    # Fade
    fade_type: int = 0            # BYTE
    fade_color_r: float = 0.0
    fade_color_g: float = 0.0
    fade_color_b: float = 0.0
    fade_delay: float = 0.0       # FLOAT
    fade_length: float = 0.0      # FLOAT

    # Camera (K1)
    camera_angle: int = 0         # INT

    # Camera (TSL)
    camera_id: int | None = None         # INT
    camera_animation: int | None = None  # DWORD
    camera_fov: float | None = None      # FLOAT
    camera_height: float | None = None   # FLOAT
    camera_effect: int | None = None     # INT
    target_height: float | None = None   # FLOAT

    # TSL extended fields
    node_unskippable: bool = False
    alien_race_node: int = 0
    emotion_id: int = 0
    facial_id: int = 0
    node_id_tsl: int = 0          # NodeID field (TSL)
    post_proc_node: int = 0
    record_vo: bool = False
    record_no_vo_override: bool = False
    vo_text_changed: bool = False

    # TSL Script1 params
    script1_param1: int = 0
    script1_param2: int = 0
    script1_param3: int = 0
    script1_param4: int = 0
    script1_param5: int = 0
    script1_param_str: str = ""

    # TSL Script2 params
    script2_param1: int = 0
    script2_param2: int = 0
    script2_param3: int = 0
    script2_param4: int = 0
    script2_param5: int = 0
    script2_param_str: str = ""

    # Branches leading OUT of this node
    branches: List[DialogueBranch] = field(default_factory=list)

    # Visual layout (editor only, not written to GFF)
    position_x: float = 0.0
    position_y: float = 0.0

    # Conditionals / actions (editor display helpers)
    conditionals: List[DialogueConditional] = field(default_factory=list)
    script_actions: List[DialogueAction] = field(default_factory=list)

    # Editor comment
    comment: str = ""

    # Original typed GFF struct, if this node came from an imported DLG.  The
    # exporter overlays edited model fields onto a copy of this struct so K2
    # and future/unknown fields are not discarded.
    _raw_gff: Any = field(default=None, repr=False, compare=False)
    _source_state: Dict[str, Any] = field(
        default_factory=dict, repr=False, compare=False,
    )

    def short_text(self, max_len: int = 40, tlk=None) -> str:
        """Return a truncated display string for this node.

        If ``text`` is empty and ``text_strref`` is a valid StrRef (≥ 0),
        attempt to resolve it via *tlk* (a TLKFile-like object that supports
        ``get_string(strref) -> str``).
        """
        t = self.text.strip()
        if not t and tlk is not None:
            strref = self.text_strref
            if strref is not None and strref >= 0:
                try:
                    t = (tlk.get_string(strref) or "").strip()
                except Exception:
                    pass
        if not t and self.text_strref is not None and self.text_strref >= 0:
            # Fallback: show the strref number so editors know there IS text
            return f"[StrRef {self.text_strref}]"
        if len(t) > max_len:
            return t[:max_len - 1] + "…"
        return t

    def add_branch(self, text: str, target_id: int = -1,
                   active_script: str = "") -> DialogueBranch:
        b = DialogueBranch(
            branch_id=len(self.branches),
            target_node_id=target_id,
            text=text,
            active_script=active_script,
        )
        self.branches.append(b)
        return b

    def get_branch(self, branch_id: int) -> DialogueBranch | None:
        for b in self.branches:
            if b.branch_id == branch_id:
                return b
        return None

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "speaker": self.speaker,
            "listener": self.listener,
            "text": self.text,
            "text_strref": self.text_strref,
            "script1": self.script1,
            "script2": self.script2,
            "vo_resref": self.vo_resref,
            "delay": self.delay,
            "branches": len(self.branches),
        }


# ── Dialogue File ─────────────────────────────────────────────

@dataclass
class DialogueFile:
    """
    Represents a .dlg file — a GFF-based conversation tree.

    Top-level GFF fields:
      EntryList / ReplyList / StartingList
      EndConversation / EndConverAbort scripts
      Skippable, DelayEntry, DelayReply
      AmbientTrack, AnimatedCut, CameraModel
      ConversationType (0=Human 1=Computer 2=Other)
      ComputerType (0=Modern 1=Ancient)
    """

    name: str = "new_dialogue"
    file_path: str | None = None

    # All entry nodes (NPC lines)
    entries: List[DialogueNode] = field(default_factory=list)
    # All reply nodes (player choices)
    replies: List[DialogueNode] = field(default_factory=list)

    # Starting links — these point into entries
    starters: List[DialogueBranch] = field(default_factory=list)

    # Top-level scripts
    on_end: str = ""              # EndConversation RESREF
    on_abort: str = ""            # EndConverAbort  RESREF

    # Top-level settings
    skippable: bool = True        # BYTE
    delay_entry: int = 0          # DWORD
    delay_reply: int = 0          # DWORD
    ambient_track: str = ""       # RESREF
    animated_cut: bool = False    # BYTE
    camera_model: str = ""        # RESREF
    conversation_type: int = 0    # INT  0=Human 1=Computer 2=Other
    computer_type: int = 0        # BYTE 0=Modern 1=Ancient
    old_hit_check: bool = False   # BYTE
    unequip_items: bool = False   # BYTE
    unequip_h_item: bool = False  # BYTE
    word_count: int = 0           # DWORD (TSL NumWords)

    # Import provenance used by the fidelity-preserving writer.  ``source_game``
    # also prevents an imported TSL dialogue from being accidentally rewritten
    # through the K1 schema merely because a UI selector still says K1.
    source_game: str | None = None
    _raw_gff: Any = field(default=None, repr=False, compare=False)
    _source_bytes: bytes | None = field(default=None, repr=False, compare=False)
    _source_state: Dict[str, Any] = field(
        default_factory=dict, repr=False, compare=False,
    )
    _unsupported_fidelity_fields: List[str] = field(
        default_factory=list, repr=False, compare=False,
    )

    # ── Unified node access (editor uses "nodes" list) ─────────
    # We keep entries/replies separate (matching GFF structure) but
    # expose a unified view for the graph editor.

    @property
    def nodes(self) -> List[DialogueNode]:
        """All nodes for the graph editor (entries + replies interleaved)."""
        return self.entries + self.replies

    def add_node(self, node: DialogueNode):
        if node.node_type == "reply":
            node.node_id = len(self.replies)
            self.replies.append(node)
        else:
            node.node_id = len(self.entries)
            self.entries.append(node)

    def remove_node(self, node_id: int, node_type: str | None = None):
        """Remove exactly one typed DLG node and repair list-index links.

        Entry and reply IDs occupy separate zero-based namespaces, so deleting
        bare ID ``0`` must never delete both Entry 0 and Reply 0.  Existing
        callers that omit *node_type* remain supported when the ID is
        unambiguous; an ambiguous bare ID now raises a clear error instead of
        silently destroying two nodes.

        Since DLG branch targets are list indices, removing an item also shifts
        all greater targets of the same type down by one and renumbers that
        node list.  Links to the opposite node type are left untouched.
        """
        if node_type is None:
            has_entry = self.get_entry(node_id) is not None
            has_reply = self.get_reply(node_id) is not None
            if has_entry and has_reply:
                raise ValueError(
                    f"Node ID {node_id} is ambiguous; pass node_type='entry' "
                    "or node_type='reply'."
                )
            if not has_entry and not has_reply:
                return
            node_type = "entry" if has_entry else "reply"

        node_type = node_type.lower().strip()
        if node_type not in {"entry", "reply"}:
            raise ValueError("node_type must be 'entry' or 'reply'")

        def repair_links(branches: List[DialogueBranch]) -> List[DialogueBranch]:
            repaired: List[DialogueBranch] = []
            for branch in branches:
                if branch.target_node_id == node_id:
                    continue
                if branch.target_node_id > node_id:
                    branch.target_node_id -= 1
                branch.branch_id = len(repaired)
                repaired.append(branch)
            return repaired

        if node_type == "entry":
            if self.get_entry(node_id) is None:
                return
            self.entries = [n for n in self.entries if n.node_id != node_id]
            for new_id, node in enumerate(self.entries):
                node.node_id = new_id
            # Starters and reply branches target EntryList.
            self.starters = repair_links(self.starters)
            for reply in self.replies:
                reply.branches = repair_links(reply.branches)
        else:
            if self.get_reply(node_id) is None:
                return
            self.replies = [n for n in self.replies if n.node_id != node_id]
            for new_id, node in enumerate(self.replies):
                node.node_id = new_id
            # Entry branches target ReplyList.
            for entry in self.entries:
                entry.branches = repair_links(entry.branches)

    def get_node(self, node_id: int) -> DialogueNode | None:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def get_entry(self, node_id: int) -> "DialogueNode" | None:
        """Return the entry node with the given node_id (not list index)."""
        for n in self.entries:
            if n.node_id == node_id:
                return n
        return None

    def get_reply(self, node_id: int) -> "DialogueNode" | None:
        """Return the reply node with the given node_id (not list index)."""
        for n in self.replies:
            if n.node_id == node_id:
                return n
        return None

    def validate_tree(self) -> List[str]:
        """Basic validation — returns list of issue strings."""
        issues = []
        if not self.starters and not self.entries:
            issues.append("No starting entries defined.")
        # Check for dangling branch targets
        all_entry_ids = {n.node_id for n in self.entries}
        all_reply_ids = {n.node_id for n in self.replies}
        for node in self.entries:
            for b in node.branches:
                if b.target_node_id >= 0 and b.target_node_id not in all_reply_ids:
                    issues.append(
                        f"Entry #{node.node_id} branch → Reply #{b.target_node_id} not found."
                    )
        for node in self.replies:
            for b in node.branches:
                if b.target_node_id >= 0 and b.target_node_id not in all_entry_ids:
                    issues.append(
                        f"Reply #{node.node_id} branch → Entry #{b.target_node_id} not found."
                    )
        # Check for orphaned nodes (not reachable from starters)
        reachable_entries: set[int] = set()
        reachable_replies: set[int] = set()
        # BFS from starters
        from collections import deque
        queue: deque = deque()
        for starter in self.starters:
            if starter.target_node_id >= 0:
                queue.append(("entry", starter.target_node_id))
        while queue:
            kind, nid = queue.popleft()
            if kind == "entry":
                if nid in reachable_entries:
                    continue
                reachable_entries.add(nid)
                entry = self.get_entry(nid)
                if entry:
                    for b in entry.branches:
                        if b.target_node_id >= 0:
                            queue.append(("reply", b.target_node_id))
            else:
                if nid in reachable_replies:
                    continue
                reachable_replies.add(nid)
                reply = self.get_reply(nid)
                if reply:
                    for b in reply.branches:
                        if b.target_node_id >= 0:
                            queue.append(("entry", b.target_node_id))
        orphan_entries = all_entry_ids - reachable_entries
        orphan_replies = all_reply_ids - reachable_replies
        for oid in sorted(orphan_entries):
            issues.append(f"Entry #{oid} is orphaned (unreachable from starters).")
        for oid in sorted(orphan_replies):
            issues.append(f"Reply #{oid} is orphaned (unreachable from starters).")
        return issues

    # ── NetworkX graph helpers ────────────────────────────────

    def to_networkx(self) -> "nx.DiGraph":
        """Build a NetworkX DiGraph of this dialogue tree.

        Node attributes:
          - kind: 'entry' | 'reply'
          - label: short display text
          - speaker: speaker tag (entries only)

        Edge attributes:
          - active: active_script for the branch (conditional)

        Returns:
          nx.DiGraph — or raises ImportError if networkx is unavailable.
        """
        if not _HAS_NX:
            raise ImportError(
                "networkx is required for graph analysis. "
                "Install with: pip install networkx"
            )

        G: nx.DiGraph = nx.DiGraph()

        # Add all nodes
        for n in self.entries:
            G.add_node(
                f"E{n.node_id}",
                kind="entry",
                node_id=n.node_id,
                label=n.short_text(30),
                speaker=n.speaker,
            )
        for n in self.replies:
            G.add_node(
                f"R{n.node_id}",
                kind="reply",
                node_id=n.node_id,
                label=n.short_text(30),
                speaker=n.speaker,
            )

        # Add starter links (virtual source "START")
        G.add_node("START", kind="start", label="START")
        for s in self.starters:
            if s.target_node_id >= 0:
                G.add_edge("START", f"E{s.target_node_id}",
                           active=s.active_script)

        # Add entry → reply edges
        for n in self.entries:
            for b in n.branches:
                if b.target_node_id >= 0:
                    G.add_edge(
                        f"E{n.node_id}", f"R{b.target_node_id}",
                        active=b.active_script,
                    )

        # Add reply → entry edges
        for n in self.replies:
            for b in n.branches:
                if b.target_node_id >= 0:
                    G.add_edge(
                        f"R{n.node_id}", f"E{b.target_node_id}",
                        active=b.active_script,
                    )

        return G

    def graph_stats(self) -> Dict[str, object]:
        """Return graph statistics using NetworkX.

        Returns dict with keys:
          - node_count, edge_count
          - has_cycles (bool)
          - unreachable_nodes (list of node labels)
          - longest_path_length (int, or -1 if cyclic)
          - strongly_connected_components (int count)
        """
        if not _HAS_NX:
            # Fallback: basic stats without networkx
            return {
                "node_count": len(self.entries) + len(self.replies),
                "edge_count": sum(
                    len(n.branches) for n in self.entries + self.replies
                ),
                "has_cycles": None,
                "unreachable_nodes": [],
                "longest_path_length": -1,
                "strongly_connected_components": -1,
            }

        G = self.to_networkx()
        has_cycles = not nx.is_directed_acyclic_graph(G)

        # Nodes reachable from START
        try:
            reachable: Set[str] = nx.descendants(G, "START") | {"START"}
        except nx.NetworkXError:
            reachable = {"START"}
        unreachable = [
            n for n in G.nodes()
            if n not in reachable and n != "START"
        ]

        longest = -1
        if not has_cycles:
            try:
                longest = nx.dag_longest_path_length(G)
            except Exception:
                longest = -1

        scc_count = nx.number_strongly_connected_components(G)

        return {
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
            "has_cycles": has_cycles,
            "unreachable_nodes": unreachable,
            "longest_path_length": longest,
            "strongly_connected_components": scc_count,
        }

    def find_dead_ends(self) -> List[str]:
        """Return node labels (e.g. 'E3', 'R7') that have no outgoing branches
        to another node (i.e. they terminate the conversation or are orphaned).

        These are potential dead-ends that a designer may want to review.
        """
        dead_ends = []
        for n in self.entries:
            if not n.branches or all(b.target_node_id < 0 for b in n.branches):
                dead_ends.append(f"E{n.node_id}: {n.short_text(30)}")
        for n in self.replies:
            if not n.branches or all(b.target_node_id < 0 for b in n.branches):
                dead_ends.append(f"R{n.node_id}: {n.short_text(30)}")
        return dead_ends

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "entries": len(self.entries),
            "replies": len(self.replies),
            "starters": len(self.starters),
            "on_end": self.on_end,
            "on_abort": self.on_abort,
            "skippable": self.skippable,
            "conversation_type": self.conversation_type,
        }


# ── Factory ────────────────────────────────────────────────────

def create_simple_dialogue(name: str, npc_tag: str) -> DialogueFile:
    """Create a basic two-node dialogue: NPC greeting → Player response."""
    dlg = DialogueFile(name=name)

    # Entry 0: NPC greeting
    entry = DialogueNode(
        node_id=0,
        node_type="entry",
        speaker=npc_tag,
        text="Hello there. What can I do for you?",
    )
    # Reply 0: player response
    reply = DialogueNode(
        node_id=0,
        node_type="reply",
        speaker="Player",
        text="Nothing, thanks.",
    )
    # Connect: entry → reply (terminates)
    entry.add_branch(text="Nothing, thanks.", target_id=0)
    # Connect: reply ends conversation (target_id = -1)
    reply.add_branch(text="[END]", target_id=-1)

    dlg.entries.append(entry)
    dlg.replies.append(reply)

    # Starting list: first entry is the starter
    starter = DialogueBranch(branch_id=0, target_node_id=0, text="")
    dlg.starters.append(starter)

    return dlg
