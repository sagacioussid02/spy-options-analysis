"""
store.py — the one door all persistent cma_lab state goes through.

Every state module (journal, shadow, playbook, predictions, radar, lessons,
risk overrides, CMA resource ids, committee debates/beliefs, futurist theses,
Robinhood tokens) used to read/write its own JSON/markdown file next to this
module. That works on a laptop and breaks in a scheduled cloud run, which
starts from a fresh git checkout where every one of those (gitignored) files
is missing and any write is thrown away when the run ends.

So: one `store()` with two backends, chosen by the presence of DATABASE_URL.

- JsonFileStore  (default) — exactly the same files/dirs as before, so local
  behaviour is unchanged: cma_lab/<name>.json, lessons.md, debates/<id>.json,
  beliefs/<persona>.md, theses/<slug>.md.
- PostgresStore  (DATABASE_URL set) — one table, `collections(name, data
  jsonb)`. A "collection" is whatever the module used to keep in one file
  (a list, a dict, or a string), or for directory-backed collections a dict
  of {doc_name: content}.

Module API is intentionally tiny: load(name, default) / save(name, obj) /
lock(name). Modules keep their public APIs; only their _load/_save bodies
changed.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional

BASE = Path(__file__).parent

# Collections stored as a single text file (a str), not JSON.
_TEXT_FILES = {"lessons": "lessons.md"}
# Collections stored as a directory of documents: name -> (subdir, extension).
# Loaded/saved as {doc_name: content}; ".json" docs are parsed, ".md" are str.
_DIR_COLLECTIONS = {
    "debates": ("debates", ".json"),
    "beliefs": ("beliefs", ".md"),
    "theses": ("theses", ".md"),
    "theses_archive": ("theses/archive", ".md"),
}


def _env(key: str) -> Optional[str]:
    """OS env first, then cma_lab/.env — without importing lab (lab imports us)."""
    v = os.environ.get(key)
    if v:
        return v
    env_file = BASE / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                return line.partition("=")[2].strip().strip('"').strip("'") or None
    return None


class JsonFileStore:
    """The original behaviour: files next to the modules."""

    def __init__(self, base: Path = BASE):
        self.base = base

    def _path(self, name: str) -> Path:
        if name in _TEXT_FILES:
            return self.base / _TEXT_FILES[name]
        return self.base / f"{name}.json"

    def load(self, name: str, default: Any = None) -> Any:
        if name in _DIR_COLLECTIONS:
            subdir, ext = _DIR_COLLECTIONS[name]
            d = self.base / subdir
            out: dict = {}
            if d.exists():
                for f in sorted(d.glob(f"*{ext}")):
                    text = f.read_text()
                    if ext == ".json":
                        try:
                            out[f.stem] = json.loads(text)
                        except json.JSONDecodeError:
                            continue
                    else:
                        out[f.stem] = text
            return out if out or default is None else default
        p = self._path(name)
        if not p.exists():
            return default
        text = p.read_text()
        if name in _TEXT_FILES:
            return text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return default

    def save(self, name: str, obj: Any) -> None:
        if name in _DIR_COLLECTIONS:
            subdir, ext = _DIR_COLLECTIONS[name]
            d = self.base / subdir
            d.mkdir(parents=True, exist_ok=True)
            keep = set()
            for doc, content in (obj or {}).items():
                keep.add(f"{doc}{ext}")
                text = json.dumps(content, indent=2) if ext == ".json" else str(content)
                (d / f"{doc}{ext}").write_text(text)
            for f in d.glob(f"*{ext}"):
                if f.name not in keep:
                    f.unlink()
            return
        p = self._path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        if name in _TEXT_FILES:
            p.write_text(str(obj))
        else:
            p.write_text(json.dumps(obj, indent=2))

    @contextlib.contextmanager
    def lock(self, name: str):
        yield  # single-user laptop: nothing to lock against

    def describe(self) -> str:
        return f"json files in {self.base}"


class PostgresStore:
    """One table; each collection is one jsonb row. Cheap, transactional,
    shared by local and cloud runs alike."""

    def __init__(self, dsn: str):
        import psycopg  # imported lazily so JSON-only installs don't need it
        self._psycopg = psycopg
        self.dsn = dsn
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS collections ("
                " name text PRIMARY KEY,"
                " data jsonb NOT NULL,"
                " updated_at timestamptz NOT NULL DEFAULT now())"
            )
            conn.commit()

    def _conn(self):
        return self._psycopg.connect(self.dsn)

    def load(self, name: str, default: Any = None) -> Any:
        with self._conn() as conn:
            row = conn.execute("SELECT data FROM collections WHERE name = %s", (name,)).fetchone()
        return row[0] if row else default

    def save(self, name: str, obj: Any) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO collections (name, data, updated_at) VALUES (%s, %s::jsonb, now())"
                " ON CONFLICT (name) DO UPDATE SET data = EXCLUDED.data, updated_at = now()",
                (name, json.dumps(obj)),
            )
            conn.commit()

    @contextlib.contextmanager
    def lock(self, name: str):
        """Session-level advisory lock so an overlapping run (cron + a manual
        run, say) serialises instead of racing on the same collections."""
        import zlib
        key = zlib.crc32(name.encode()) % (2 ** 31)  # stable across processes (hash() isn't)
        conn = self._conn()
        try:
            conn.execute("SELECT pg_advisory_lock(%s)", (key,))
            yield
        finally:
            try:
                conn.execute("SELECT pg_advisory_unlock(%s)", (key,))
            finally:
                conn.close()

    def describe(self) -> str:
        host = self.dsn.split("@")[-1].split("/")[0]
        return f"postgres ({host})"


_store = None


def store():
    """The process-wide store. DATABASE_URL (env or cma_lab/.env) selects
    Postgres; otherwise the original JSON files."""
    global _store
    if _store is None:
        dsn = _env("DATABASE_URL")
        _store = PostgresStore(dsn) if dsn else JsonFileStore()
    return _store


def reset_store() -> None:
    """Tests / migration: forget the cached backend so the next store() call
    re-reads DATABASE_URL."""
    global _store
    _store = None


def copy_local_to(target, *, force: bool = False, base: Path = BASE) -> list[str]:
    """Migration helper: push every local JSON/markdown collection into
    `target` (a PostgresStore). Refuses to overwrite a non-empty target
    collection unless force=True. Returns the names copied."""
    src = JsonFileStore(base)
    names = [p.stem for p in base.glob("*.json") if p.stem != "cma_state" or True]
    names += list(_TEXT_FILES) + list(_DIR_COLLECTIONS)
    copied = []
    for name in sorted(set(names)):
        obj = src.load(name)
        if obj in (None, [], {}, ""):
            continue
        existing = target.load(name)
        if existing not in (None, [], {}, "") and not force:
            print(f"  [migrate] skip {name}: target already has data (use --force)")
            continue
        target.save(name, obj)
        copied.append(name)
    return copied


def backup_local(base: Path = BASE) -> Path:
    """Snapshot the local state files before a migration."""
    dest = base / "state_backup"
    dest.mkdir(exist_ok=True)
    for p in list(base.glob("*.json")) + [base / f for f in _TEXT_FILES.values()]:
        if p.exists():
            shutil.copy2(p, dest / p.name)
    for subdir, _ in _DIR_COLLECTIONS.values():
        d = base / subdir
        if d.exists():
            shutil.copytree(d, dest / subdir, dirs_exist_ok=True)
    return dest
