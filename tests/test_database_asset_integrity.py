"""Focused regressions for audited database and Asset Library integrity gaps."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _project(game: str = "K2") -> SimpleNamespace:
    return SimpleNamespace(
        target_game=game,
        scripts=[],
        quests=[],
        dialogues=[],
        models=[],
        script_dir=None,
    )


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - environment-specific skip
        pytest.skip(f"Qt unavailable: {exc}")
    return QApplication.instance() or QApplication([])


def _template_item(widget, key: str):
    from qtpy.QtCore import Qt

    for row in range(widget.template_list.count()):
        item = widget.template_list.item(row)
        if item.data(Qt.UserRole) == key:
            return item
    raise AssertionError(f"Template {key!r} is not advertised")


def test_quest_snapshot_listing_returns_stored_json():
    from ghostscripter.core.database.manager import DatabaseManager

    class Quest:
        quest_id = "audit_quest"

        @staticmethod
        def to_dict():
            return {"quest_id": "audit_quest", "target_game": "K2", "states": [0, 1]}

    with DatabaseManager(db_path=":memory:") as db:
        db.save_quest_snapshot("audit_project", Quest())
        snapshots = db.get_quest_snapshots("audit_project", "audit_quest")

    assert len(snapshots) == 1
    assert json.loads(snapshots[0]["data_json"]) == Quest.to_dict()


def test_new_quest_uses_live_project_game(qapp, monkeypatch):
    from ghostscripter.ui.widgets.asset_library_widget import (
        AssetLibraryWidget,
        QInputDialog,
    )

    project = _project("K2")
    widget = AssetLibraryWidget(project=project, target_game="K1")
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("K2 Quest", True))

    widget._new_quest()

    assert len(project.quests) == 1
    assert project.quests[0].target_game == "K2"


@pytest.mark.parametrize(
    "template_key",
    ["NPC_COMPANION_QUEST", "SIMPLE_QUEST", "BRANCHING_QUEST"],
)
def test_advertised_quest_templates_create_quests(
    qapp, monkeypatch, template_key
):
    from ghostscripter.ui.widgets.asset_library_widget import (
        AssetLibraryWidget,
        QInputDialog,
    )

    project = _project("K2")
    widget = AssetLibraryWidget(project=project)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("Template Quest", True))

    widget._use_template(_template_item(widget, template_key))

    assert len(project.quests) == 1
    assert project.quests[0].target_game == "K2"
    assert project.quests[0].quest_name == "Template Quest"


@pytest.mark.parametrize(
    ("template_key", "expected_source"),
    [
        ("script_void_main", "void main()"),
        ("script_conditional", "int StartingConditional()"),
    ],
)
def test_advertised_script_templates_create_real_source(
    qapp, monkeypatch, template_key, expected_source
):
    from ghostscripter.ui.widgets.asset_library_widget import (
        AssetLibraryWidget,
        QInputDialog,
    )

    project = _project()
    widget = AssetLibraryWidget(project=project)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("audit_script.nss", True))

    widget._use_template(_template_item(widget, template_key))

    assert len(project.scripts) == 1
    assert project.scripts[0].name == "audit_script"
    assert expected_source in project.scripts[0].source_code


def test_greeting_template_label_and_factory_both_report_two_nodes(qapp, monkeypatch):
    from ghostscripter.ui.widgets.asset_library_widget import (
        AssetLibraryWidget,
        QInputDialog,
    )

    project = _project()
    widget = AssetLibraryWidget(project=project)
    item = _template_item(widget, "dialogue_greeting")
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("audit_greeting", True))

    assert "(2 nodes)" in item.text()
    widget._use_template(item)

    assert len(project.dialogues) == 1
    dialogue = project.dialogues[0]
    assert len(dialogue.entries) + len(dialogue.replies) == 2
    assert "(2 nodes)" in widget.detail_text.toPlainText()


def test_asset_library_follows_main_window_game_context_without_project(qapp):
    from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget

    widget = AssetLibraryWidget(target_game="K1")
    widget.set_target_game("K2")
    assert widget._current_target_game() == "K2"
