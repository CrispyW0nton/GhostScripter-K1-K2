"""
GhostScripter-K1-K2 — Quest Model
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Any


_RESREF_RE = re.compile(r"[^a-z0-9_]")
_GLOBAL_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
QUEST_FILE_SCHEMA_VERSION = 1


@dataclass
class GlobalVariable:
    variable_name: str
    variable_type: str = "Boolean"   # Boolean | Number | String
    default_value: Any = False
    description: str = ""

    @property
    def globalcat_entry(self) -> str:
        return f"{self.variable_name}    {self.variable_type}"


@dataclass
class QuestState:
    state_id: int
    state_name: str
    description: str = ""
    entry_dialogue: str | None = None
    entry_script: str | None = None
    spawned_npcs: List[str] = field(default_factory=list)
    spawned_placeables: List[str] = field(default_factory=list)
    available_objectives: List[str] = field(default_factory=list)


@dataclass
class QuestTrigger:
    trigger_type: str           # dialogue_choice | item_acquired | npc_death | etc
    condition: str = ""
    target_state: int = 0
    action_script: str | None = None


@dataclass
class QuestDefinition:
    quest_id: str = ""
    quest_name: str = ""
    description: str = ""
    target_game: str = "K1"

    variables: List[GlobalVariable] = field(default_factory=list)
    states: List[QuestState] = field(default_factory=list)
    triggers: List[QuestTrigger] = field(default_factory=list)
    dialogues: List[str] = field(default_factory=list)
    scripts: List[str] = field(default_factory=list)

    quest_type: str = "side"        # main | side | companion
    priority: int = 5
    repeatable: bool = False
    conflicts_with: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)

    # Project-local artifact path.  This is storage metadata, not part of the
    # portable quest definition, and is therefore intentionally not serialized.
    file_path: Path | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        """Return the complete, JSON-safe quest definition.

        Older versions returned display summaries and converted defaults to
        strings.  That made a project reload incapable of reconstructing the
        quest.  This representation contains every modeled field and preserves
        Boolean/number/string defaults as their original JSON types.
        """
        return {
            "schema_version": QUEST_FILE_SCHEMA_VERSION,
            "quest_id": self.quest_id,
            "quest_name": self.quest_name,
            "description": self.description,
            "target_game": self.target_game,
            "quest_type": self.quest_type,
            "priority": self.priority,
            "repeatable": self.repeatable,
            "conflicts_with": list(self.conflicts_with),
            "dependencies": list(self.dependencies),
            "variables": [
                {
                    "variable_name": v.variable_name,
                    "variable_type": v.variable_type,
                    "default_value": v.default_value,
                    "description": v.description,
                }
                for v in self.variables
            ],
            "states": [
                {
                    "state_id": s.state_id,
                    "state_name": s.state_name,
                    "description": s.description,
                    "entry_dialogue": s.entry_dialogue,
                    "entry_script": s.entry_script,
                    "spawned_npcs": list(s.spawned_npcs),
                    "spawned_placeables": list(s.spawned_placeables),
                    "available_objectives": list(s.available_objectives),
                }
                for s in self.states
            ],
            "triggers": [
                {
                    "trigger_type": t.trigger_type,
                    "condition": t.condition,
                    "target_state": t.target_state,
                    "action_script": t.action_script,
                }
                for t in self.triggers
            ],
            "dialogues": list(self.dialogues),
            "scripts": list(self.scripts),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QuestDefinition":
        """Reconstruct a quest, accepting both current and legacy field names."""
        if not isinstance(data, dict):
            raise TypeError("Quest data must be a JSON object")

        variables = []
        for item in data.get("variables", []):
            variables.append(GlobalVariable(
                variable_name=item.get("variable_name", item.get("name", "")),
                variable_type=item.get("variable_type", item.get("type", "Boolean")),
                default_value=item.get("default_value", item.get("default", False)),
                description=item.get("description", ""),
            ))

        states = []
        for item in data.get("states", []):
            states.append(QuestState(
                state_id=int(item.get("state_id", item.get("id", 0))),
                state_name=item.get("state_name", item.get("name", "")),
                description=item.get("description", ""),
                entry_dialogue=item.get("entry_dialogue"),
                entry_script=item.get("entry_script"),
                spawned_npcs=list(item.get("spawned_npcs", [])),
                spawned_placeables=list(item.get("spawned_placeables", [])),
                available_objectives=list(item.get("available_objectives", [])),
            ))

        triggers = []
        for item in data.get("triggers", []):
            triggers.append(QuestTrigger(
                trigger_type=item.get("trigger_type", ""),
                condition=item.get("condition", ""),
                target_state=int(item.get("target_state", 0)),
                action_script=item.get("action_script"),
            ))

        return cls(
            quest_id=data.get("quest_id", ""),
            quest_name=data.get("quest_name", ""),
            description=data.get("description", ""),
            target_game=data.get("target_game", "K1"),
            variables=variables,
            states=states,
            triggers=triggers,
            dialogues=list(data.get("dialogues", [])),
            scripts=list(data.get("scripts", [])),
            quest_type=data.get("quest_type", "side"),
            priority=int(data.get("priority", 5)),
            repeatable=bool(data.get("repeatable", False)),
            conflicts_with=list(data.get("conflicts_with", [])),
            dependencies=list(data.get("dependencies", [])),
        )

    def save_to_file(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # json.dumps first ensures unsupported defaults fail before the old
        # artifact is opened/truncated.
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        path.write_text(payload + "\n", encoding="utf-8")
        self.file_path = path
        return path

    @classmethod
    def load_from_file(cls, path: str | Path) -> "QuestDefinition":
        path = Path(path)
        quest = cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        quest.file_path = path
        return quest

    def __str__(self):
        return f"QuestDefinition({self.quest_id!r})"


# ── Templates ──────────────────────────────────────────────────

QUEST_TEMPLATES = {
    "SIMPLE_QUEST": {
        "display": "Simple Quest (3 states)",
        "states": [
            {"id": 0, "name": "Not Started", "description": "Quest has not been initiated."},
            {"id": 1, "name": "Active", "description": "Quest is in progress."},
            {"id": 2, "name": "Complete", "description": "Quest is finished."},
        ],
        "variables": [
            {"name": "K_SWG_{UPPER}", "type": "Boolean", "default": False,
             "description": "Is quest active?"},
            {"name": "K_SWG_{UPPER}_STATE", "type": "Number", "default": 0,
             "description": "Quest progression state."},
        ],
    },
    "BRANCHING_QUEST": {
        "display": "Branching Quest (Light/Dark)",
        "states": [
            {"id": 0, "name": "Not Started"},
            {"id": 1, "name": "Active - Light Side Path"},
            {"id": 2, "name": "Active - Dark Side Path"},
            {"id": 3, "name": "Complete - Light Side"},
            {"id": 4, "name": "Complete - Dark Side"},
        ],
        "variables": [
            {"name": "K_SWG_{UPPER}", "type": "Boolean", "default": False,
             "description": "Is quest active?"},
            {"name": "K_SWG_{UPPER}_STATE", "type": "Number", "default": 0,
             "description": "Quest state (0-4)."},
            {"name": "K_SWG_{UPPER}_CHOICE", "type": "Number", "default": 0,
             "description": "Player alignment choice (1=light, 2=dark)."},
        ],
    },
    "NPC_COMPANION_QUEST": {
        "display": "NPC Companion Recruitment",
        "states": [
            {"id": 0, "name": "Not Recruited"},
            {"id": 1, "name": "Recruited"},
            {"id": 2, "name": "Companion Quest Active"},
            {"id": 3, "name": "Companion Quest Complete"},
        ],
        "variables": [
            {"name": "K_SWG_{UPPER}_RECRUITED", "type": "Boolean", "default": False,
             "description": "Has NPC been recruited?"},
            {"name": "K_SWG_{UPPER}_QUEST", "type": "Number", "default": 0,
             "description": "Companion quest state."},
        ],
    },
}


def make_quest_script_resref(quest_id: str, state_id: int) -> str:
    """Return a legal, deterministic KotOR script ResRef (at most 16 chars).

    Short names stay readable.  Long names retain a five-character prefix and
    use ten hexadecimal SHA-256 characters derived from the complete intended
    name, so distinct long quest/state pairs do not merely truncate to the same
    ResRef.  KotOR ResRefs are case-insensitive, hence the lowercase canonical
    form.
    """
    if int(state_id) < 0:
        raise ValueError("Quest state IDs must be non-negative")
    base = _RESREF_RE.sub("_", (quest_id or "quest").strip().lower()).strip("_")
    base = base or "quest"
    intended = f"{base}_{int(state_id):02d}"
    if len(intended) <= 16:
        return intended
    digest = hashlib.sha256(intended.encode("utf-8")).hexdigest()[:10]
    return f"{base[:5]}_{digest}"


def _state_variable(quest: QuestDefinition) -> str | None:
    numeric = [
        var.variable_name for var in quest.variables
        if var.variable_type.strip().lower() == "number"
    ]
    if not numeric:
        return None
    preferred = next((name for name in numeric if name.upper().endswith("_STATE")), None)
    variable = preferred or numeric[0]
    if not _GLOBAL_NAME_RE.fullmatch(variable):
        raise ValueError(
            f"Global variable {variable!r} cannot be embedded safely in NWScript"
        )
    return variable


def generate_quest_script_files(
    quest: QuestDefinition,
    script_dir: str | Path,
    *,
    overwrite: bool = False,
) -> List[Any]:
    """Create compileable state-action scripts and return ``ScriptFile`` models.

    Existing files are preserved by default and loaded into the returned model
    rather than overwritten.  This makes repeated generation safe for scripts
    that a mod author has already customized.
    """
    from ghostscripter.core.models.script import (
        ScriptFile,
        make_quest_complete_template,
        make_quest_start_template,
        make_quest_state_template,
        make_void_main_template,
    )

    directory = Path(script_dir)
    directory.mkdir(parents=True, exist_ok=True)
    state_ids = [state.state_id for state in quest.states]
    if len(state_ids) != len(set(state_ids)):
        raise ValueError("Quest state IDs must be unique before scripts can be generated")

    names = [make_quest_script_resref(quest.quest_id, state.state_id)
             for state in quest.states]
    if len(names) != len(set(names)):
        raise ValueError("Generated script ResRefs collided; rename the quest or its states")

    variable = _state_variable(quest)
    last_state_id = max(state_ids) if state_ids else None
    result = []
    for state, name in zip(quest.states, names):
        path = directory / f"{name}.nss"
        if path.exists() and not overwrite:
            source = path.read_text(encoding="utf-8", errors="replace")
        elif variable is None:
            source = make_void_main_template().replace(
                "// Your code here",
                "// No Number global is defined for this quest; add state logic here",
            )
        elif state.state_id == 1:
            source = make_quest_start_template(variable, state.state_id)
        elif last_state_id is not None and state.state_id == last_state_id:
            source = make_quest_complete_template(variable, state.state_id)
        else:
            source = make_quest_state_template(
                variable, state.state_id, state.state_name,
            )

        script = ScriptFile(
            name=name,
            file_path=path,
            source_code=source,
            script_type="quest",
            associated_quest=quest.quest_id,
        )
        if (overwrite or not path.exists()) and not script.save_to_disk():
            raise OSError(f"Could not write generated script: {path}")
        result.append(script)

    quest.scripts = names
    return result


def create_quest_from_template(
    template_key: str,
    quest_name: str,
    target_game: str,
) -> QuestDefinition:
    """Generate a full quest scaffold from a template.

    ``K_SWG_`` is retained as GhostScripter's legacy default namespace for
    backward compatibility.  It is not a game or community-wide requirement;
    authors may replace it with their own unique mod prefix.
    """
    template = QUEST_TEMPLATES.get(template_key, QUEST_TEMPLATES["SIMPLE_QUEST"])
    safe_name = re.sub(r"[^A-Za-z0-9_]", "", quest_name).upper() or "QUEST"
    quest_slug = _RESREF_RE.sub("_", quest_name.strip().lower()).strip("_") or "quest"
    quest_id = f"k_swg_{quest_slug}"

    quest = QuestDefinition(
        quest_id=quest_id,
        quest_name=quest_name,
        target_game=target_game,
    )

    # Create variables
    for vt in template["variables"]:
        var_name = vt["name"].replace("{UPPER}", safe_name)
        quest.variables.append(GlobalVariable(
            variable_name=var_name,
            variable_type=vt["type"],
            default_value=vt["default"],
            description=vt.get("description", ""),
        ))

    # Create states
    for st in template["states"]:
        quest.states.append(QuestState(
            state_id=st["id"],
            state_name=st["name"],
            description=st.get("description", ""),
        ))

    # Script stubs
    for state in quest.states:
        quest.scripts.append(make_quest_script_resref(quest.quest_id, state.state_id))

    return quest
