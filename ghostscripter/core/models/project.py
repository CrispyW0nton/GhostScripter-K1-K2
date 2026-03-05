"""
GhostScripter-K1-K2 — Core Data Models
project.py: ModProject definition
"""
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any


@dataclass
class ModDependency:
    name: str
    version: str
    description: str = ""


@dataclass
class ModelReference:
    name: str
    file_path: Path
    mdx_path: Optional[Path] = None
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
    root_dir: Optional[Path] = None
    script_dir: Optional[Path] = None
    dialogue_dir: Optional[Path] = None
    quest_dir: Optional[Path] = None
    module_dir: Optional[Path] = None
    twoda_dir: Optional[Path] = None
    texture_dir: Optional[Path] = None
    model_dir: Optional[Path] = None
    template_dir: Optional[Path] = None
    export_dir: Optional[Path] = None

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
        """Persist project manifest to disk."""
        if not self.root_dir:
            return
        self.modified_date = datetime.now()
        manifest = {
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
        }
        manifest_path = self.root_dir / "project.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

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
            root_dir=project_path,
        )
        project._init_folders()
        return project

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
