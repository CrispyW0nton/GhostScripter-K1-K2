"""
GhostScripter-K1-K2 — Quest Model
"""
from dataclasses import dataclass, field
from typing import List, Optional, Any


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
    entry_dialogue: Optional[str] = None
    entry_script: Optional[str] = None
    spawned_npcs: List[str] = field(default_factory=list)
    spawned_placeables: List[str] = field(default_factory=list)
    available_objectives: List[str] = field(default_factory=list)


@dataclass
class QuestTrigger:
    trigger_type: str           # dialogue_choice | item_acquired | npc_death | etc
    condition: str = ""
    target_state: int = 0
    action_script: Optional[str] = None


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

    def to_dict(self) -> dict:
        return {
            "quest_id": self.quest_id,
            "quest_name": self.quest_name,
            "description": self.description,
            "target_game": self.target_game,
            "quest_type": self.quest_type,
            "state_count": len(self.states),
            "variable_count": len(self.variables),
            "variables": [
                {"name": v.variable_name, "type": v.variable_type,
                 "default": str(v.default_value), "description": v.description}
                for v in self.variables
            ],
            "states": [
                {"id": s.state_id, "name": s.state_name, "description": s.description}
                for s in self.states
            ],
        }

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


def create_quest_from_template(
    template_key: str,
    quest_name: str,
    target_game: str,
) -> QuestDefinition:
    """Generate a full quest scaffold from a template."""
    template = QUEST_TEMPLATES.get(template_key, QUEST_TEMPLATES["SIMPLE_QUEST"])
    safe_name = "".join(c for c in quest_name if c.isalnum() or c == "_").upper()
    quest_id = f"k_swg_{quest_name.lower().replace(' ', '_')}"

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
        script_name = f"k_swg_{quest_name.lower().replace(' ', '_')}_{state.state_id:02d}"
        quest.scripts.append(script_name)

    return quest
