"""
GhostScripter-K1-K2
Core constants used throughout the application.
"""

# Application Info
APP_NAME = "GhostScripter-K1-K2"
APP_VERSION = "3.6.1"
APP_DESCRIPTION = "KotOR Script + Logic IDE"

# Game Targets
GAME_K1 = "K1"
GAME_K2 = "K2"
GAME_CHOICES = [GAME_K1, GAME_K2]

# Script Types
SCRIPT_TYPE_QUEST = "quest"
SCRIPT_TYPE_DIALOGUE = "dialogue"
SCRIPT_TYPE_EVENT = "event"
SCRIPT_TYPE_NPC = "npc"
SCRIPT_TYPES = [SCRIPT_TYPE_QUEST, SCRIPT_TYPE_DIALOGUE, SCRIPT_TYPE_EVENT, SCRIPT_TYPE_NPC]

# Quest Types
QUEST_TYPE_MAIN = "main"
QUEST_TYPE_SIDE = "side"
QUEST_TYPE_COMPANION = "companion"
QUEST_TYPES = [QUEST_TYPE_MAIN, QUEST_TYPE_SIDE, QUEST_TYPE_COMPANION]

# Variable Types
VAR_TYPE_BOOLEAN = "Boolean"
VAR_TYPE_NUMBER = "Number"
VAR_TYPE_STRING = "String"
VAR_TYPES = [VAR_TYPE_BOOLEAN, VAR_TYPE_NUMBER, VAR_TYPE_STRING]

# Quest Templates
QUEST_TEMPLATE_SIMPLE = "SIMPLE_QUEST"
QUEST_TEMPLATE_BRANCHING = "BRANCHING_QUEST"
QUEST_TEMPLATE_NPC_COMPANION = "NPC_COMPANION_QUEST"
QUEST_TEMPLATES = {
    QUEST_TEMPLATE_SIMPLE: "Simple Quest (3 states)",
    QUEST_TEMPLATE_BRANCHING: "Branching Quest (Light/Dark)",
    QUEST_TEMPLATE_NPC_COMPANION: "NPC Companion Recruitment",
}

# File Extensions
EXT_NSS = ".nss"
EXT_NCS = ".ncs"
EXT_DLG = ".dlg"
EXT_2DA = ".2da"
EXT_MDL = ".mdl"
EXT_MDX = ".mdx"
EXT_TPC = ".tpc"
EXT_TGA = ".tga"
EXT_UTC = ".utc"
EXT_ERF = ".erf"
EXT_MOD = ".mod"

# Resource Type Map
RESTYPE_MAP = {
    ".ncs": "NCS",
    ".dlg": "DLG",
    ".2da": "2DA",
    ".mdl": "MDL",
    ".mdx": "MDX",
    ".tpc": "TPC",
    ".tga": "TGA",
    ".utc": "UTC",
}

# IPC Config — GhostWorks pipeline ports (canonical source: ghostscripter.ipc.ports)
from ghostscripter.ipc.ports import (   # noqa: E402
    GHOSTRIGGER_REST_LEGACY as IPC_PORT_GHOSTRIGGER,
    GHOSTSCRIPTER_REST as IPC_PORT_GHOSTSCRIPTER,
    GMODULAR_REST as IPC_PORT_GMODULAR,
)
IPC_DEFAULT_PORT = IPC_PORT_GHOSTSCRIPTER
IPC_HOST = "localhost"

# Colors (matching KotorModTools dark theme)
COLOR_BACKGROUND = "#1e1e1e"
COLOR_PANEL = "#252526"
COLOR_PANEL_HEADER = "#2d2d30"
COLOR_BORDER = "#3c3c3c"
COLOR_TEXT = "#d4d4d4"
COLOR_TEXT_DIM = "#858585"
COLOR_ACCENT = "#0078d4"
COLOR_ACCENT_HOVER = "#1a8fe0"
COLOR_SELECTION = "#094771"
COLOR_ERROR = "#f48771"
COLOR_SUCCESS = "#4ec9b0"
COLOR_WARNING = "#dcdcaa"

# NSS Syntax Colors
COLOR_NSS_KEYWORD = "#569cd6"
COLOR_NSS_FUNCTION = "#dcdcaa"
COLOR_NSS_COMMENT = "#57a64a"
COLOR_NSS_STRING = "#ce9178"
COLOR_NSS_NUMBER = "#b5cea8"
COLOR_NSS_TYPE = "#4ec9b0"
COLOR_NSS_CONSTANT = "#9cdcfe"

# NWScript keywords
NWSCRIPT_KEYWORDS = [
    "void", "int", "float", "string", "object", "effect", "event",
    "location", "talent", "vector", "struct", "return", "if", "else",
    "for", "while", "do", "switch", "case", "break", "continue",
    "default", "TRUE", "FALSE", "OBJECT_SELF", "OBJECT_INVALID",
    "ACTION_INVALID", "LOCATION_INVALID"
]

NWSCRIPT_TYPES = [
    "void", "int", "float", "string", "object", "effect", "event",
    "location", "talent", "vector", "struct", "action", "itemproperty",
    "command", "json", "sqlquery", "cassowary"
]

# Common KotOR Functions
KOTOR_COMMON_FUNCTIONS = {
    "Quest / Global Variables": [
        {"name": "SetGlobalNumber", "params": ["string sVarname", "int nValue"],
         "returns": "void", "description": "Set a global number variable.",
         "example": 'SetGlobalNumber("K_SWG_MYQUEST", 1);'},
        {"name": "GetGlobalNumber", "params": ["string sVarname"],
         "returns": "int", "description": "Get a global number variable.",
         "example": 'int nState = GetGlobalNumber("K_SWG_MYQUEST");'},
        {"name": "SetGlobalBoolean", "params": ["string sVarname", "int bValue"],
         "returns": "void", "description": "Set a global boolean variable.",
         "example": 'SetGlobalBoolean("K_SWG_QUEST_ACTIVE", TRUE);'},
        {"name": "GetGlobalBoolean", "params": ["string sVarname"],
         "returns": "int", "description": "Get a global boolean variable.",
         "example": 'if (GetGlobalBoolean("K_SWG_QUEST_ACTIVE")) { }'},
        {"name": "SetGlobalString", "params": ["string sVarname", "string sValue"],
         "returns": "void", "description": "Set a global string variable.",
         "example": 'SetGlobalString("K_SWG_PLAYER_CHOICE", "light");'},
        {"name": "GetGlobalString", "params": ["string sVarname"],
         "returns": "string", "description": "Get a global string variable.",
         "example": 'string sChoice = GetGlobalString("K_SWG_PLAYER_CHOICE");'},
    ],
    "Object / NPC": [
        {"name": "GetObjectByTag", "params": ["string sTag", "int nNthObject"],
         "returns": "object", "description": "Get object by tag.",
         "example": 'object oNPC = GetObjectByTag("k_npc_001", 0);'},
        {"name": "CreateObject", "params": ["int nObjectType", "string sTemplate", "location lLocation", "int bUseAppearAnimation"],
         "returns": "object", "description": "Create an object at location.",
         "example": 'object oNew = CreateObject(OBJECT_TYPE_CREATURE, "k_npc_001", GetLocation(OBJECT_SELF));'},
        {"name": "DestroyObject", "params": ["object oDestroy", "float fDelay"],
         "returns": "void", "description": "Destroy an object.",
         "example": 'DestroyObject(oNPC, 0.0f);'},
        {"name": "GetIsObjectValid", "params": ["object oObject"],
         "returns": "int", "description": "Check if object is valid.",
         "example": 'if (GetIsObjectValid(oNPC)) { }'},
        {"name": "GetTag", "params": ["object oObject"],
         "returns": "string", "description": "Get an object tag.",
         "example": 'string sTag = GetTag(oNPC);'},
    ],
    "Conversation / Dialogue": [
        {"name": "BeginConversation", "params": ["string sResRef", "object oTarget"],
         "returns": "void", "description": "Begin a dialogue with target.",
         "example": 'BeginConversation("k_npc_dialogue", oNPC);'},
        {"name": "ActionStartConversation", "params": ["object oObjectToConverse", "string sDialogResRef", "int bPrivateConversation"],
         "returns": "void", "description": "Start a conversation action.",
         "example": 'ActionStartConversation(oNPC, "k_dialogue_001", FALSE);'},
    ],
    "Party": [
        {"name": "AddPartyMember", "params": ["int nNPC", "object oCreature"],
         "returns": "int", "description": "Add NPC to party.",
         "example": 'AddPartyMember(NPC_ATTON, oAtton);'},
        {"name": "RemovePartyMember", "params": ["int nNPC"],
         "returns": "void", "description": "Remove NPC from party.",
         "example": 'RemovePartyMember(NPC_ATTON);'},
        {"name": "IsObjectPartyMember", "params": ["object oCreature"],
         "returns": "int", "description": "Check if object is party member.",
         "example": 'if (IsObjectPartyMember(oNPC)) { }'},
    ],
    "Combat / Effects": [
        {"name": "EffectDamage", "params": ["int nDamageAmount", "int nDamageType", "int nDamagePower"],
         "returns": "effect", "description": "Create a damage effect.",
         "example": 'effect eDmg = EffectDamage(10, DAMAGE_TYPE_BLUDGEONING, DAMAGE_POWER_NORMAL);'},
        {"name": "ApplyEffectToObject", "params": ["int nDurationType", "effect eEffect", "object oTarget", "float fDuration"],
         "returns": "void", "description": "Apply an effect to an object.",
         "example": 'ApplyEffectToObject(DURATION_TYPE_INSTANT, eDmg, oEnemy, 0.0f);'},
        {"name": "EffectHeal", "params": ["int nDamageToHeal"],
         "returns": "effect", "description": "Create a healing effect.",
         "example": 'ApplyEffectToObject(DURATION_TYPE_INSTANT, EffectHeal(20), oPC, 0.0f);'},
    ],
    "Alignment": [
        {"name": "GetGoodEvilValue", "params": ["object oCreature"],
         "returns": "int", "description": "Get Light/Dark side points (0-100).",
         "example": 'int nAlign = GetGoodEvilValue(GetFirstPC());'},
        {"name": "AdjustAlignment", "params": ["object oCreature", "int nAlignment", "int nShift", "int bAllPartyMembers"],
         "returns": "void", "description": "Adjust creature alignment.",
         "example": 'AdjustAlignment(GetFirstPC(), ALIGNMENT_LIGHT_SIDE, 10, FALSE);'},
    ],
}
