"""GhostScripter-K1-K2 — UI Widgets package."""

from ghostscripter.ui.widgets.dialogue_editor_widget import (
    DialogueEditorWidget,
    NodeInspector,
    DialoguePropertiesPanel,
    DialogueGraphScene,
    DialogueNodeItem,
)
from ghostscripter.ui.widgets.script_editor_widget import ScriptEditorWidget
from ghostscripter.ui.widgets.twoda_manager_widget import TwoDAManagerWidget
from ghostscripter.ui.widgets.tlk_editor_widget import TLKEditorWidget
from ghostscripter.ui.widgets.erf_packer_widget import ERFPackerWidget
from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
from ghostscripter.ui.widgets.quest_builder_widget import QuestBuilderWidget
from ghostscripter.ui.widgets.gff_template_viewer_widget import GFFTemplateViewerWidget

__all__ = [
    "DialogueEditorWidget",
    "NodeInspector",
    "DialoguePropertiesPanel",
    "DialogueGraphScene",
    "DialogueNodeItem",
    "ScriptEditorWidget",
    "TwoDAManagerWidget",
    "TLKEditorWidget",
    "ERFPackerWidget",
    "AssetLibraryWidget",
    "QuestBuilderWidget",
    "GFFTemplateViewerWidget",
]
