"""
GhostScripter-K1-K2 — Screenshot capture for demo
"""
import os
import sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '/home/user/webapp')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QPixmap

app = QApplication(sys.argv)

from ghostscripter.ui.main_window import MainWindow
w = MainWindow()
w.resize(1280, 800)
w.show()

# Open some demo tabs
from ghostscripter.core.models.script import ScriptFile, make_void_main_template
from ghostscripter.core.models.quest import create_quest_from_template
from ghostscripter.core.models.dialogue import create_simple_dialogue
from ghostscripter.ui.widgets.script_editor_widget import ScriptEditorWidget
from ghostscripter.ui.widgets.quest_builder_widget import QuestBuilderWidget
from ghostscripter.ui.widgets.dialogue_editor_widget import DialogueEditorWidget

# Add demo script tab
script = ScriptFile(name="k_swg_demo_start",
                    source_code='''// Quest Start Script — GhostScripter-K1-K2
// Sets quest to active state

void main() {
    // Activate the demo quest
    SetGlobalBoolean("K_SWG_DEMO", TRUE);
    SetGlobalNumber("K_SWG_DEMO_STATE", 1);
    
    // Get the PC
    object oPC = GetFirstPC();
    
    // Check alignment
    int nAlign = GetGoodEvilValue(oPC);
    if (nAlign > 75) {
        // Light side bonus
        AdjustAlignment(oPC, ALIGNMENT_LIGHT_SIDE, 5, FALSE);
    }
    
    // Spawn quest NPC
    object oNPC = GetObjectByTag("k_npc_questgiver", 0);
    if (GetIsObjectValid(oNPC)) {
        ActionStartConversation(oNPC, "k_demo_dialogue", FALSE);
    }
}
''',
                    script_type="quest")
editor = ScriptEditorWidget(script=script)
w.editor_tabs.addTab(editor, "✎ k_swg_demo_start.nss")

# Add demo quest
quest = create_quest_from_template("BRANCHING_QUEST", "DemoQuest", "K1")
quest_editor = QuestBuilderWidget(quest=quest)
w.editor_tabs.addTab(quest_editor, "⚔ DemoQuest")

# Add dialogue
dlg = create_simple_dialogue("k_demo_dialogue", "k_npc_questgiver")
dlg_editor = DialogueEditorWidget(dialogue=dlg)
w.editor_tabs.addTab(dlg_editor, "🗨 k_demo_dialogue.dlg")

# Switch to script tab
w.editor_tabs.setCurrentIndex(1)

app.processEvents()

# Grab screenshot
screen = app.primaryScreen()
screenshot = screen.grabWindow(w.winId())
screenshot.save('/home/user/webapp/screenshot.png', 'PNG')
print("Screenshot saved: /home/user/webapp/screenshot.png")
