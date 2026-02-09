#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import sys
from getpass import getpass
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.models import AuthDB  # noqa: E402
from app.security import hash_password  # noqa: E402


def _prompt_username() -> str:
    while True:
        username = input("Admin username: ").strip()
        if username:
            return username
        print("Username cannot be empty.", file=sys.stderr)


def _prompt_password() -> str:
    while True:
        password = getpass("Admin password: ")
        if not password:
            print("Password cannot be empty.", file=sys.stderr)
            continue
        confirm = getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.", file=sys.stderr)
            continue
        return password


def main() -> None:
    settings = get_settings()
    db = AuthDB(settings.auth_db_path)
    db.init()

    username = os.environ.get("ADMIN_USER") or _prompt_username()
    password = os.environ.get("ADMIN_PASS") or _prompt_password()

    try:
        db.create_user(username=username, password_hash=hash_password(password))
    except sqlite3.IntegrityError:
        print(f"User '{username}' already exists in {settings.auth_db_path}.", file=sys.stderr)
        raise SystemExit(1) from None

    print(f"OK: created user '{username}' in {settings.auth_db_path}")


if __name__ == "__main__":
    main()

