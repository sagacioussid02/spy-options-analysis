"""
One-shot: copy the local cma_lab JSON/markdown state into the Postgres store
so cloud runs (fresh checkouts) start from the same journal/playbook/shadow/
tokens as the laptop.

    DATABASE_URL=postgresql://... .venv/bin/python scripts/migrate_state_to_neon.py [--force]

Backs up the local files to cma_lab/state_backup/ first. Refuses to overwrite
a non-empty target collection unless --force. Also seeds the Robinhood token
fields from cma_lab/.env into the "secrets" collection.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cma_lab"))

import store as store_mod  # noqa: E402


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL must be set in the environment for this script.")
        return 2
    force = "--force" in sys.argv
    backup = store_mod.backup_local()
    print(f"[migrate] local state backed up to {backup}")
    target = store_mod.PostgresStore(dsn)
    copied = store_mod.copy_local_to(target, force=force)
    print(f"[migrate] copied collections: {copied or 'none'}")

    store_mod.reset_store()
    import lab  # noqa: E402  (picks up DATABASE_URL -> PostgresStore)
    keys = lab.seed_secrets_from_env()
    print(f"[migrate] seeded secrets: {keys or 'none'}")
    print(f"[migrate] target: {target.describe()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
