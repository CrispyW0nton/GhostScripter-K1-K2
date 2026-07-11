"""
GhostScripter-K1-K2 — Core Data Models
project.py: ModProject definition
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


@dataclass
class ModDependency:
    name: str
    version: str
    description: str = ""


@dataclass
class ModelReference:
    name: str
    file_path: Path
    mdx_path: Path | None = None
    texture_paths: List[Path] = field(default_factory=list)
    appearance_2da_id: int = -1

    def get_files(self) -> List[Path]:
        files = [self.file_path]
        if self.mdx_path and self.mdx_path.exists():
            files.append(self.mdx_path)
        files.extend(self.texture_paths)
        return files


@dataclass
class ModProject:
    """Represents a complete GhostScripter mod project."""

    project_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    target_game: str = "K1"
    created_date: datetime = field(default_factory=datetime.now)
    modified_date: datetime = field(default_factory=datetime.now)

    # Folder structure
    root_dir: Path | None = None
    script_dir: Path | None = None
    dialogue_dir: Path | None = None
    quest_dir: Path | None = None
    module_dir: Path | None = None
    twoda_dir: Path | None = None
    texture_dir: Path | None = None
    model_dir: Path | None = None
    template_dir: Path | None = None
    export_dir: Path | None = None

    # Project state (lazy lists)
    quests: List[Any] = field(default_factory=list)
    dialogues: List[Any] = field(default_factory=list)
    scripts: List[Any] = field(default_factory=list)
    modules: List[Any] = field(default_factory=list)
    twoda_edits: Dict[str, Dict] = field(default_factory=dict)
    models: List[ModelReference] = field(default_factory=list)
    dependencies: List[ModDependency] = field(default_factory=list)

    # Metadata
    tags: List[str] = field(default_factory=list)
    category: str = "Quest"
    compatibility: List[str] = field(default_factory=list)

    # Non-fatal artifact load failures are retained for the UI/audit log.  The
    # source files are never deleted or rewritten merely because they could not
    # be parsed during project discovery.
    artifact_warnings: List[str] = field(default_factory=list, repr=False)

    # ──────────────────────────────────────────────────────────

    @classmethod
    def create_new(cls, name: str, author: str, target_game: str,
                   root_directory: Path, description: str = "") -> "ModProject":
        """Create a fresh project workspace on disk."""
        project = cls(
            name=name,
            author=author,
            description=description,
            target_game=target_game,
            root_dir=root_directory,
        )
        project._init_folders()
        project.save()
        return project

    def _init_folders(self):
        """Create folder structure."""
        if not self.root_dir:
            return
        folders = {
            "script_dir": "scripts",
            "dialogue_dir": "dialogues",
            "quest_dir": "quests",
            "module_dir": "modules",
            "twoda_dir": "2da",
            "texture_dir": "textures",
            "model_dir": "models",
            "template_dir": "templates",
            "export_dir": "export",
        }
        for attr, name in folders.items():
            path = self.root_dir / name
            path.mkdir(parents=True, exist_ok=True)
            setattr(self, attr, path)

    def save(self):
        """Persist the project manifest and its editable artifacts to disk."""
        if not self.root_dir:
            return
        self._init_folders()
        self.modified_date = datetime.now()

        script_artifacts = []
        used_script_paths: set[Path] = set()
        seen_script_objects: set[int] = set()
        for script in self.scripts:
            if id(script) in seen_script_objects:
                continue
            seen_script_objects.add(id(script))
            path = self._persist_script(script, used_paths=used_script_paths)
            if path is None:
                continue
            used_script_paths.add(path.resolve())
            script_artifacts.append({
                "path": self._manifest_path(path),
                "name": getattr(script, "name", path.stem),
                "script_type": getattr(script, "script_type", "quest"),
                "associated_quest": getattr(script, "associated_quest", None),
                "dependencies": list(getattr(script, "dependencies", [])),
                "global_variables": list(getattr(script, "global_variables", [])),
                "functions_called": list(getattr(script, "functions_called", [])),
                "created": self._date_text(getattr(script, "created_date", None)),
                "modified": self._date_text(getattr(script, "modified_date", None)),
            })

        quest_artifacts = []
        used_quest_paths: set[Path] = set()
        for quest in self.quests:
            path = self.save_quest(quest, used_paths=used_quest_paths)
            used_quest_paths.add(path.resolve())
            quest_artifacts.append({"path": self._manifest_path(path)})

        dialogue_artifacts = []
        used_dialogue_paths: set[Path] = set()
        seen_dialogue_objects: set[int] = set()
        for dialogue in self.dialogues:
            if id(dialogue) in seen_dialogue_objects:
                continue
            seen_dialogue_objects.add(id(dialogue))
            path = self._persist_dialogue(
                dialogue, used_paths=used_dialogue_paths,
            )
            if path is not None:
                used_dialogue_paths.add(path.resolve())
                dialogue_artifacts.append({
                    "path": self._manifest_path(path),
                    "name": getattr(dialogue, "name", path.stem),
                })

        manifest = {
            "schema_version": 2,
            "project_id": self.project_id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "target_game": self.target_game,
            "created": self.created_date.isoformat(),
            "modified": self.modified_date.isoformat(),
            "category": self.category,
            "tags": self.tags,
            "compatibility": self.compatibility,
            "twoda_edits": self.twoda_edits,
            "dependencies": [
                {
                    "name": dependency.name,
                    "version": dependency.version,
                    "description": dependency.description,
                }
                for dependency in self.dependencies
            ],
            "models": [
                {
                    "name": model.name,
                    "file_path": self._manifest_path(model.file_path),
                    "mdx_path": (
                        self._manifest_path(model.mdx_path)
                        if model.mdx_path else None
                    ),
                    "texture_paths": [
                        self._manifest_path(path) for path in model.texture_paths
                    ],
                    "appearance_2da_id": model.appearance_2da_id,
                }
                for model in self.models
            ],
            "artifacts": {
                "scripts": script_artifacts,
                "quests": quest_artifacts,
                "dialogues": dialogue_artifacts,
            },
        }
        manifest_path = self.root_dir / "project.json"
        payload = json.dumps(manifest, indent=2, ensure_ascii=False)
        temporary_path = manifest_path.with_suffix(".json.tmp")
        temporary_path.write_text(payload + "\n", encoding="utf-8")
        temporary_path.replace(manifest_path)

    @staticmethod
    def _date_text(value: Any) -> str | None:
        return value.isoformat() if isinstance(value, datetime) else None

    @staticmethod
    def _safe_stem(value: str, fallback: str) -> str:
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._")
        return stem or fallback

    def _manifest_path(self, path: str | Path) -> str:
        candidate = Path(path)
        if self.root_dir:
            try:
                return candidate.resolve().relative_to(self.root_dir.resolve()).as_posix()
            except ValueError:
                pass
        return str(candidate.resolve())

    def _resolve_artifact_path(self, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            if not self.root_dir:
                raise ValueError("Cannot resolve a relative artifact without a project root")
            path = self.root_dir / path
        return path

    def _persist_script(
        self,
        script: Any,
        *,
        used_paths: set[Path] | None = None,
    ) -> Path | None:
        if not self.script_dir:
            return None
        raw_path = getattr(script, "file_path", None)
        if raw_path:
            path = Path(raw_path)
        else:
            name = self._safe_stem(getattr(script, "name", ""), "untitled")
            path = self.script_dir / f"{name}.nss"
            script.file_path = path
        if used_paths and path.resolve() in used_paths:
            raise ValueError(
                f"Multiple project scripts resolve to the same file: {path}"
            )

        # An empty lazily-discovered model must not erase a real source file.
        source = getattr(script, "source_code", "")
        if path.exists() and not source:
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(script, "save_to_disk"):
            if not script.save_to_disk():
                raise OSError(f"Could not save project script: {path}")
        else:
            path.write_text(str(source), encoding="utf-8")
        return path

    def save_quest(
        self,
        quest: Any,
        *,
        used_paths: set[Path] | None = None,
    ) -> Path:
        """Write one complete QuestDefinition JSON artifact."""
        if not self.quest_dir:
            raise ValueError("Project has no quest directory")
        raw_path = getattr(quest, "file_path", None)
        if raw_path:
            path = Path(raw_path)
        else:
            source_name = getattr(quest, "quest_id", "") or getattr(
                quest, "quest_name", ""
            )
            stem = self._safe_stem(source_name, "quest")
            path = self.quest_dir / f"{stem}.json"
            ordinal = 1
            while path.exists() or (used_paths and path.resolve() in used_paths):
                suffix = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{source_name}\0{getattr(quest, 'quest_name', '')}\0{ordinal}",
                ).hex[:8]
                path = self.quest_dir / f"{stem}_{suffix}.json"
                ordinal += 1

        if hasattr(quest, "save_to_file"):
            return quest.save_to_file(path)
        payload = json.dumps(quest.to_dict(), indent=2, ensure_ascii=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
        return path

    def _persist_dialogue(
        self,
        dialogue: Any,
        *,
        used_paths: set[Path] | None = None,
    ) -> Path | None:
        if not self.dialogue_dir:
            return None
        raw_path = getattr(dialogue, "file_path", None)
        if raw_path:
            path = Path(raw_path)
        else:
            name = self._safe_stem(getattr(dialogue, "name", ""), "dialogue")
            path = self.dialogue_dir / f"{name}.dlg"
            dialogue.file_path = path
        if used_paths and path.resolve() in used_paths:
            raise ValueError(
                f"Multiple project dialogues resolve to the same file: {path}"
            )

        # A placeholder represents an artifact that failed to parse.  Keep the
        # path in the manifest but never overwrite its source bytes.
        if getattr(dialogue, "_project_load_error", None):
            return path

        from ghostscripter.core.export.dlg_writer import DLGExporter

        game = getattr(dialogue, "source_game", None) or self.target_game
        data = DLGExporter().export(dialogue, target_game=game)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        dialogue.file_path = path
        return path

    @classmethod
    def load(cls, project_path: Path) -> "ModProject":
        """Load an existing project from disk."""
        manifest_file = project_path / "project.json"
        if not manifest_file.exists():
            raise FileNotFoundError(f"No project.json found at {project_path}")
        with open(manifest_file, encoding="utf-8") as f:
            data = json.load(f)

        project = cls(
            project_id=data.get("project_id", str(uuid.uuid4())),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            description=data.get("description", ""),
            target_game=data.get("target_game", "K1"),
            created_date=datetime.fromisoformat(data.get("created", datetime.now().isoformat())),
            modified_date=datetime.fromisoformat(data.get("modified", datetime.now().isoformat())),
            category=data.get("category", "Quest"),
            tags=data.get("tags", []),
            compatibility=data.get("compatibility", []),
            twoda_edits=data.get("twoda_edits", {}),
            root_dir=project_path,
        )
        project._init_folders()
        project.dependencies = [
            ModDependency(
                name=item.get("name", ""),
                version=item.get("version", ""),
                description=item.get("description", ""),
            )
            for item in data.get("dependencies", [])
            if isinstance(item, dict)
        ]
        project.models = [
            ModelReference(
                name=item.get("name", ""),
                file_path=project._resolve_artifact_path(item.get("file_path", "")),
                mdx_path=(
                    project._resolve_artifact_path(item["mdx_path"])
                    if item.get("mdx_path") else None
                ),
                texture_paths=[
                    project._resolve_artifact_path(path)
                    for path in item.get("texture_paths", [])
                ],
                appearance_2da_id=int(item.get("appearance_2da_id", -1)),
            )
            for item in data.get("models", [])
            if isinstance(item, dict) and item.get("file_path")
        ]
        project._load_artifacts(data.get("artifacts", {}))
        return project

    @staticmethod
    def _artifact_entry_path(entry: Any) -> str | None:
        if isinstance(entry, str):
            return entry
        if isinstance(entry, dict):
            value = entry.get("path")
            return str(value) if value else None
        return None

    @staticmethod
    def _path_key(path: Path) -> str:
        return str(path.resolve()).casefold()

    def _declared_artifacts(self, artifacts: dict, kind: str) -> Dict[str, dict]:
        declared = {}
        values = artifacts.get(kind, []) if isinstance(artifacts, dict) else []
        for entry in values:
            raw_path = self._artifact_entry_path(entry)
            if not raw_path:
                continue
            path = self._resolve_artifact_path(raw_path)
            declared[self._path_key(path)] = entry if isinstance(entry, dict) else {
                "path": entry,
            }
        return declared

    def _discover_paths(
        self,
        declared: Dict[str, dict],
        directory: Path | None,
        pattern: str,
    ) -> Dict[str, Path]:
        paths: Dict[str, Path] = {}
        for entry in declared.values():
            raw_path = self._artifact_entry_path(entry)
            if raw_path:
                path = self._resolve_artifact_path(raw_path)
                if path.is_file():
                    paths[self._path_key(path)] = path
        if directory and directory.is_dir():
            for path in directory.rglob(pattern):
                if path.is_file():
                    paths.setdefault(self._path_key(path), path)
        return paths

    @staticmethod
    def _parse_date(value: Any) -> datetime:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                pass
        return datetime.now()

    def _load_artifacts(self, artifacts: dict) -> None:
        """Load declared artifacts, while also recovering unlisted disk files."""
        from ghostscripter.core.models.script import ScriptFile
        from ghostscripter.core.models.quest import QuestDefinition

        script_meta = self._declared_artifacts(artifacts, "scripts")
        for key, path in sorted(
            self._discover_paths(script_meta, self.script_dir, "*.nss").items()
        ):
            meta = script_meta.get(key, {})
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                self.scripts.append(ScriptFile(
                    name=meta.get("name", path.stem),
                    file_path=path,
                    source_code=source,
                    created_date=self._parse_date(meta.get("created")),
                    modified_date=self._parse_date(meta.get("modified")),
                    dependencies=list(meta.get("dependencies", [])),
                    global_variables=list(meta.get("global_variables", [])),
                    functions_called=list(meta.get("functions_called", [])),
                    script_type=meta.get("script_type", "quest"),
                    associated_quest=meta.get("associated_quest"),
                ))
            except OSError as exc:
                self.artifact_warnings.append(f"Could not load script {path}: {exc}")

        quest_meta = self._declared_artifacts(artifacts, "quests")
        for _, path in sorted(
            self._discover_paths(quest_meta, self.quest_dir, "*.json").items()
        ):
            try:
                self.quests.append(QuestDefinition.load_from_file(path))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                self.artifact_warnings.append(f"Could not load quest {path}: {exc}")

        dialogue_meta = self._declared_artifacts(artifacts, "dialogues")
        dialogue_paths = self._discover_paths(
            dialogue_meta, self.dialogue_dir, "*.dlg"
        )
        if dialogue_paths:
            from ghostscripter.core.export.dlg_reader import DLGImporter
            from ghostscripter.core.models.dialogue import DialogueFile

            importer = DLGImporter()
            for _, path in sorted(dialogue_paths.items()):
                try:
                    self.dialogues.append(importer.import_from_file(path))
                except Exception as exc:
                    # Keep an explicit non-writable placeholder in the project
                    # so a parse failure does not make the artifact disappear.
                    placeholder = DialogueFile(name=path.stem, file_path=str(path))
                    placeholder._project_load_error = str(exc)
                    self.dialogues.append(placeholder)
                    self.artifact_warnings.append(
                        f"Could not parse dialogue {path}: {exc}"
                    )

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "target_game": self.target_game,
            "category": self.category,
            "tags": self.tags,
            "script_count": len(self.scripts),
            "quest_count": len(self.quests),
            "dialogue_count": len(self.dialogues),
        }

    def __str__(self):
        return f"ModProject({self.name!r}, {self.target_game}, {self.version})"
