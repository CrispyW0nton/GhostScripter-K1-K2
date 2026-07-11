from __future__ import annotations

import json
import re

import pytest

from ghostscripter.core.models.dialogue import create_simple_dialogue
from ghostscripter.core.models.project import ModDependency, ModProject
from ghostscripter.core.models.quest import (
    GlobalVariable,
    QuestDefinition,
    QuestState,
    QuestTrigger,
    create_quest_from_template,
    generate_quest_script_files,
    make_quest_script_resref,
)
from ghostscripter.core.models.script import ScriptFile


def _complete_quest() -> QuestDefinition:
    return QuestDefinition(
        quest_id="author_relic_hunt",
        quest_name="Relic Hunt",
        description="A fully modeled quest.",
        target_game="K2",
        variables=[
            GlobalVariable("AUTHOR_RELIC_ACTIVE", "Boolean", False, "active"),
            GlobalVariable("AUTHOR_RELIC_STATE", "Number", 0, "progress"),
            GlobalVariable("AUTHOR_RELIC_NOTE", "String", "unread", "note"),
        ],
        states=[
            QuestState(
                0,
                "Dormant",
                "Not yet started",
                entry_dialogue="relic_intro",
                entry_script="relic_enter",
                spawned_npcs=["relic_keeper"],
                spawned_placeables=["relic_chest"],
                available_objectives=["Find the keeper"],
            ),
            QuestState(3, "Complete", "Relic recovered"),
        ],
        triggers=[
            QuestTrigger("item_acquired", "relic_item", 3, "relic_finish"),
        ],
        dialogues=["relic_intro", "relic_outro"],
        scripts=["relic_enter", "relic_finish"],
        quest_type="side",
        priority=8,
        repeatable=True,
        conflicts_with=["author_rival_path"],
        dependencies=["author_core"],
    )


def test_quest_json_roundtrip_is_lossless(tmp_path):
    quest = _complete_quest()
    path = quest.save_to_file(tmp_path / "quests" / "relic.json")

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["variables"][0]["default_value"] is False
    assert raw["variables"][1]["default_value"] == 0
    assert "state_count" not in raw

    loaded = QuestDefinition.load_from_file(path)
    assert loaded.to_dict() == quest.to_dict()
    assert loaded.file_path == path
    assert loaded.states[0].spawned_npcs == ["relic_keeper"]
    assert loaded.triggers[0].action_script == "relic_finish"


def test_project_save_and_load_restores_real_artifacts(tmp_path):
    root = tmp_path / "project"
    project = ModProject.create_new("Artifact Test", "Tester", "K2", root)
    quest = _complete_quest()
    project.quests.append(quest)
    project.scripts.append(ScriptFile(
        name="author_state",
        source_code='void main() { SetGlobalNumber("AUTHOR_RELIC_STATE", 3); }\n',
        script_type="quest",
        associated_quest=quest.quest_id,
        dependencies=["helper_inc"],
    ))
    project.dialogues.append(create_simple_dialogue("relic_intro", "keeper"))
    project.dependencies.append(ModDependency("Core Mod", "2.0", "required"))
    project.twoda_edits = {"globalcat.2da": {"AUTHOR_RELIC_STATE": "Number"}}

    project.save()

    loaded = ModProject.load(root)
    assert len(loaded.scripts) == 1
    assert loaded.scripts[0].source_code.startswith("void main()")
    assert loaded.scripts[0].associated_quest == quest.quest_id
    assert loaded.scripts[0].dependencies == ["helper_inc"]
    assert len(loaded.quests) == 1
    assert loaded.quests[0].to_dict() == quest.to_dict()
    assert len(loaded.dialogues) == 1
    assert loaded.dialogues[0].name == "relic_intro"
    assert loaded.dependencies == [ModDependency("Core Mod", "2.0", "required")]
    assert loaded.twoda_edits == project.twoda_edits
    assert loaded.artifact_warnings == []


def test_project_load_discovers_unlisted_artifacts(tmp_path):
    root = tmp_path / "project"
    project = ModProject.create_new("Discovery", "Tester", "K1", root)
    (project.script_dir / "unlisted.nss").write_text(
        "void main() {}\n", encoding="utf-8",
    )
    quest = _complete_quest()
    quest.quest_id = "unlisted_quest"
    quest.save_to_file(project.quest_dir / "custom_filename.json")

    loaded = ModProject.load(root)
    assert [script.name for script in loaded.scripts] == ["unlisted"]
    assert [item.quest_id for item in loaded.quests] == ["unlisted_quest"]
    assert loaded.quests[0].file_path.name == "custom_filename.json"

    # Saving preserves the discovered custom quest filename instead of creating
    # a second artifact based on its quest ID.
    loaded.save()
    assert (project.quest_dir / "custom_filename.json").is_file()
    assert not (project.quest_dir / "unlisted_quest.json").exists()


def test_project_refuses_to_overwrite_colliding_script_models(tmp_path):
    project = ModProject.create_new("Collision", "Tester", "K1", tmp_path)
    project.scripts = [
        ScriptFile(name="same", source_code="void main() { int a = 1; }\n"),
        ScriptFile(name="same", source_code="void main() { int b = 2; }\n"),
    ]

    with pytest.raises(ValueError, match="same file"):
        project.save()
    assert (project.script_dir / "same.nss").read_text(encoding="utf-8") == (
        "void main() { int a = 1; }\n"
    )


def test_long_script_resrefs_are_legal_deterministic_and_distinct():
    first = make_quest_script_resref("k_swg_an_exceptionally_long_quest", 1)
    second = make_quest_script_resref("k_swg_an_exceptionally_long_quest", 2)

    assert first == make_quest_script_resref(
        "k_swg_an_exceptionally_long_quest", 1,
    )
    assert first != second
    assert len(first) <= 16
    assert len(second) <= 16
    assert re.fullmatch(r"[a-z0-9_]+", first)
    assert make_quest_script_resref("short", 1) == "short_01"
    with pytest.raises(ValueError, match="non-negative"):
        make_quest_script_resref("short", -1)


@pytest.mark.parametrize("game_name", ["K1", "K2"])
def test_generated_quest_scripts_are_files_and_compile(tmp_path, game_name):
    from pykotor.common.misc import Game
    from pykotor.resource.formats.ncs import compile_nss

    quest = create_quest_from_template(
        "BRANCHING_QUEST",
        "An Exceptionally Long Quest Name",
        game_name,
    )
    generated = generate_quest_script_files(quest, tmp_path / "scripts")

    assert len(generated) == len(quest.states)
    assert quest.scripts == [script.name for script in generated]
    assert all(len(script.name) <= 16 for script in generated)
    for script in generated:
        assert script.file_path.is_file()
        assert script.file_path.read_text(encoding="utf-8") == script.source_code
        compiled = compile_nss(
            script.source_code,
            Game.K1 if game_name == "K1" else Game.K2,
        )
        assert compiled is not None


def test_generation_preserves_existing_user_script(tmp_path):
    quest = create_quest_from_template("SIMPLE_QUEST", "Long Existing Quest", "K1")
    generated = generate_quest_script_files(quest, tmp_path)
    customized = generated[0].file_path
    customized.write_text("void main() { /* user edit */ }\n", encoding="utf-8")

    regenerated = generate_quest_script_files(quest, tmp_path)

    assert customized.read_text(encoding="utf-8") == "void main() { /* user edit */ }\n"
    assert regenerated[0].source_code == "void main() { /* user edit */ }\n"
