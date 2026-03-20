"""
GhostScripter-K1-K2 — SQLite Database Manager
Provides persistent storage for:
  • Project registry (recently opened projects)
  • Script history / revision log
  • Quest snapshots
  • Dialogue snapshots
  • User preferences
  • Export history

Uses plain sqlite3 for simplicity and portability.
Database file: ~/.ghostscripter/ghostscripter.db

Improvements:
  • WAL checkpoint helper (checkpoint_wal) for long-running sessions
  • prune_script_history() — keep only latest N revisions per script
  • get_dialogue_snapshots() — paginated snapshot listing
  • Context-manager support (__enter__ / __exit__)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────
APP_DATA_DIR = Path.home() / ".ghostscripter"
DB_PATH = APP_DATA_DIR / "ghostscripter.db"


# ── Schema DDL ─────────────────────────────────────────────────
SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS recent_projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    path        TEXT NOT NULL,
    game        TEXT NOT NULL DEFAULT 'K1',
    last_opened TEXT NOT NULL,
    created     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS script_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    script_name TEXT NOT NULL,
    content     TEXT NOT NULL,
    saved_at    TEXT NOT NULL,
    revision    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS quest_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    quest_id    TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    saved_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dialogue_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    dlg_name    TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    saved_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS export_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    export_type TEXT NOT NULL,  -- 'override' | 'erf'
    output_path TEXT NOT NULL,
    files_count INTEGER NOT NULL DEFAULT 0,
    exported_at TEXT NOT NULL,
    success     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS user_prefs (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

CURRENT_SCHEMA_VERSION = 2


class DatabaseManager:
    """
    Manages the GhostScripter SQLite database.
    Thread-safe: uses one connection per instance (call from main thread).
    """

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._conn: sqlite3.Connection | None = None
        self._ensure_dir()
        self._connect()
        self._init_schema()

    # ── Setup ─────────────────────────────────────────────────

    def _ensure_dir(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self):
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        log.info(f"Database connected: {self.db_path}")

    def _init_schema(self):
        cur = self._conn.cursor()
        cur.executescript(SCHEMA_SQL)
        # Check/set version
        row = cur.execute("SELECT version FROM schema_version").fetchone()
        if not row:
            cur.execute("INSERT INTO schema_version VALUES (?)",
                        (CURRENT_SCHEMA_VERSION,))
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Recent Projects ────────────────────────────────────────

    def save_recent_project(self, project) -> None:
        """Upsert a project record in recent_projects."""
        now = datetime.now().isoformat()
        self._conn.execute("""
            INSERT INTO recent_projects
                (project_id, name, path, game, last_opened, created)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                name=excluded.name,
                path=excluded.path,
                game=excluded.game,
                last_opened=excluded.last_opened
        """, (
            project.project_id,
            project.name,
            str(project.root_dir),
            project.target_game,
            now,
            project.created_date.isoformat()
            if hasattr(project.created_date, "isoformat")
            else str(project.created_date),
        ))
        self._conn.commit()
        log.debug(f"Saved recent project: {project.name}")

    def get_recent_projects(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return list of recently opened projects, newest first."""
        rows = self._conn.execute("""
            SELECT project_id, name, path, game, last_opened, created
            FROM recent_projects
            ORDER BY last_opened DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def remove_recent_project(self, project_id: str) -> None:
        self._conn.execute(
            "DELETE FROM recent_projects WHERE project_id = ?", (project_id,)
        )
        self._conn.commit()

    # ── Script History ─────────────────────────────────────────

    def save_script_revision(self, project_id: str, script_name: str,
                              content: str) -> int:
        """Save a new revision. Returns the revision number."""
        row = self._conn.execute("""
            SELECT MAX(revision) FROM script_history
            WHERE project_id = ? AND script_name = ?
        """, (project_id, script_name)).fetchone()
        next_rev = (row[0] or 0) + 1
        self._conn.execute("""
            INSERT INTO script_history
                (project_id, script_name, content, saved_at, revision)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, script_name, content,
              datetime.now().isoformat(), next_rev))
        self._conn.commit()
        return next_rev

    def get_script_revisions(self, project_id: str,
                              script_name: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute("""
            SELECT id, revision, saved_at, length(content) as size_chars
            FROM script_history
            WHERE project_id = ? AND script_name = ?
            ORDER BY revision DESC
        """, (project_id, script_name)).fetchall()
        return [dict(r) for r in rows]

    def get_script_at_revision(self, project_id: str, script_name: str,
                                revision: int) -> str | None:
        row = self._conn.execute("""
            SELECT content FROM script_history
            WHERE project_id = ? AND script_name = ? AND revision = ?
        """, (project_id, script_name, revision)).fetchone()
        return row["content"] if row else None

    # ── Quest Snapshots ───────────────────────────────────────

    def save_quest_snapshot(self, project_id: str, quest) -> None:
        if not hasattr(quest, "to_dict"):
            return
        self._conn.execute("""
            INSERT INTO quest_snapshots (project_id, quest_id, data_json, saved_at)
            VALUES (?, ?, ?, ?)
        """, (project_id, quest.quest_id,
              json.dumps(quest.to_dict(), default=str),
              datetime.now().isoformat()))
        self._conn.commit()

    def get_quest_snapshots(self, project_id: str,
                             quest_id: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute("""
            SELECT id, saved_at FROM quest_snapshots
            WHERE project_id = ? AND quest_id = ?
            ORDER BY saved_at DESC
        """, (project_id, quest_id)).fetchall()
        return [dict(r) for r in rows]

    # ── Dialogue Snapshots ────────────────────────────────────

    def save_dialogue_snapshot(self, project_id: str, dialogue) -> None:
        if not hasattr(dialogue, "to_dict"):
            return
        self._conn.execute("""
            INSERT INTO dialogue_snapshots (project_id, dlg_name, data_json, saved_at)
            VALUES (?, ?, ?, ?)
        """, (project_id, dialogue.name,
              json.dumps(dialogue.to_dict(), default=str),
              datetime.now().isoformat()))
        self._conn.commit()

    # ── Export History ────────────────────────────────────────

    def log_export(self, project_id: str, export_type: str,
                   output_path: str, files_count: int,
                   success: bool = True) -> None:
        self._conn.execute("""
            INSERT INTO export_history
                (project_id, export_type, output_path,
                 files_count, exported_at, success)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project_id, export_type, output_path,
              files_count, datetime.now().isoformat(), int(success)))
        self._conn.commit()

    def get_export_history(self, project_id: str,
                           limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._conn.execute("""
            SELECT export_type, output_path, files_count, exported_at, success
            FROM export_history
            WHERE project_id = ?
            ORDER BY exported_at DESC LIMIT ?
        """, (project_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ── User Preferences ─────────────────────────────────────

    def set_pref(self, key: str, value: Any) -> None:
        self._conn.execute("""
            INSERT INTO user_prefs (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, json.dumps(value)))
        self._conn.commit()

    def get_pref(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM user_prefs WHERE key = ?", (key,)
        ).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]
        return default

    def get_all_prefs(self) -> Dict[str, Any]:
        rows = self._conn.execute("SELECT key, value FROM user_prefs").fetchall()
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except Exception:
                result[r["key"]] = r["value"]
        return result

    # ── Stats ─────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, int]:
        return {
            "recent_projects": self._conn.execute(
                "SELECT COUNT(*) FROM recent_projects").fetchone()[0],
            "script_revisions": self._conn.execute(
                "SELECT COUNT(*) FROM script_history").fetchone()[0],
            "quest_snapshots": self._conn.execute(
                "SELECT COUNT(*) FROM quest_snapshots").fetchone()[0],
            "exports": self._conn.execute(
                "SELECT COUNT(*) FROM export_history").fetchone()[0],
        }


    # ── Context manager ───────────────────────────────────────

    def __enter__(self) -> "DatabaseManager":
        """Support `with DatabaseManager() as db:` usage."""
        return self

    def __exit__(self, *exc_info) -> None:
        """Auto-close connection on context-manager exit."""
        self.close()

    # ── WAL checkpoint ────────────────────────────────────────

    def checkpoint_wal(self) -> None:
        """Run a WAL checkpoint to merge the WAL file back into the main DB.

        Useful to call periodically in long-running sessions so the WAL
        file doesn't grow unbounded.
        """
        self._conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
        self._conn.commit()
        log.debug("WAL checkpoint completed")

    # ── Maintenance ───────────────────────────────────────────

    def prune_script_history(self, project_id: str, script_name: str,
                              keep: int = 20) -> int:
        """Delete all but the latest *keep* revisions for a script.

        Returns the number of rows deleted.
        """
        row = self._conn.execute("""
            SELECT id FROM script_history
            WHERE project_id = ? AND script_name = ?
            ORDER BY revision DESC
            LIMIT -1 OFFSET ?
        """, (project_id, script_name, keep)).fetchall()

        if not row:
            return 0

        ids_to_delete = [r[0] for r in row]
        placeholders = ",".join("?" * len(ids_to_delete))
        self._conn.execute(
            f"DELETE FROM script_history WHERE id IN ({placeholders})",
            ids_to_delete
        )
        self._conn.commit()
        log.debug(f"Pruned {len(ids_to_delete)} script revisions for {script_name}")
        return len(ids_to_delete)

    def prune_export_history(self, project_id: str, keep: int = 100) -> int:
        """Delete all but the latest *keep* export records for a project."""
        row = self._conn.execute("""
            SELECT id FROM export_history
            WHERE project_id = ?
            ORDER BY exported_at DESC
            LIMIT -1 OFFSET ?
        """, (project_id, keep)).fetchall()

        if not row:
            return 0

        ids_to_delete = [r[0] for r in row]
        placeholders = ",".join("?" * len(ids_to_delete))
        self._conn.execute(
            f"DELETE FROM export_history WHERE id IN ({placeholders})",
            ids_to_delete
        )
        self._conn.commit()
        return len(ids_to_delete)

    # ── Paginated Dialogue Snapshots ──────────────────────────

    def get_dialogue_snapshots(self, project_id: str,
                                dlg_name: str = "",
                                limit: int = 50,
                                offset: int = 0) -> List[Dict[str, Any]]:
        """Return dialogue snapshots for a project, newest first.

        Optionally filter by *dlg_name*.  Supports pagination via *limit*
        and *offset* for large snapshot histories.
        """
        if dlg_name:
            rows = self._conn.execute("""
                SELECT id, dlg_name, saved_at,
                       length(data_json) as json_size
                FROM dialogue_snapshots
                WHERE project_id = ? AND dlg_name = ?
                ORDER BY saved_at DESC
                LIMIT ? OFFSET ?
            """, (project_id, dlg_name, limit, offset)).fetchall()
        else:
            rows = self._conn.execute("""
                SELECT id, dlg_name, saved_at,
                       length(data_json) as json_size
                FROM dialogue_snapshots
                WHERE project_id = ?
                ORDER BY saved_at DESC
                LIMIT ? OFFSET ?
            """, (project_id, limit, offset)).fetchall()
        return [dict(r) for r in rows]

    def get_dialogue_snapshot_data(self, snapshot_id: int) -> str | None:
        """Return the JSON data for a specific dialogue snapshot."""
        row = self._conn.execute(
            "SELECT data_json FROM dialogue_snapshots WHERE id = ?",
            (snapshot_id,)
        ).fetchone()
        return row["data_json"] if row else None

    def count_dialogue_snapshots(self, project_id: str,
                                  dlg_name: str = "") -> int:
        """Return the total number of dialogue snapshots (for pagination UI)."""
        if dlg_name:
            return self._conn.execute("""
                SELECT COUNT(*) FROM dialogue_snapshots
                WHERE project_id = ? AND dlg_name = ?
            """, (project_id, dlg_name)).fetchone()[0]
        return self._conn.execute("""
            SELECT COUNT(*) FROM dialogue_snapshots WHERE project_id = ?
        """, (project_id,)).fetchone()[0]


# ── Module-level singleton (lazy) ─────────────────────────────
_db_instance: DatabaseManager | None = None


def get_db() -> DatabaseManager:
    """Get or create the global DB manager instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance


def close_db():
    """Close the global DB connection."""
    global _db_instance
    if _db_instance:
        _db_instance.close()
        _db_instance = None
