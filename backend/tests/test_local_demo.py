"""Local-only demo access keeps genuine persistent user IDs and auditability."""
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import platform


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDB:
    def __init__(self, admin=None):
        self.admin = admin
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))
        if statement.startswith("SELECT id,name,email,role"):
            return FakeCursor(self.admin)
        if statement.startswith("SELECT id FROM platform_users"):
            return FakeCursor((self.admin[0],) if self.admin else None)
        return FakeCursor(None)


def test_local_demo_user_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(platform, "LOCAL_DEMO_MODE", False)
    with pytest.raises(HTTPException) as exc:
        platform.local_demo_user()
    assert exc.value.status_code == 403


def test_local_demo_user_uses_existing_admin_not_an_imaginary_id(monkeypatch):
    db = FakeDB((17, "Existing Admin", "private@example.invalid", "admin"))
    monkeypatch.setattr(platform, "LOCAL_DEMO_MODE", True)
    monkeypatch.setattr(platform, "conn", lambda: db)
    user = platform.local_demo_user()
    assert user["id"] == 17
    assert user["role"] == "admin"


def test_local_demo_creates_admin_only_if_none_exists(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(platform, "LOCAL_DEMO_MODE", True)
    monkeypatch.setattr(platform, "conn", lambda: db)
    platform.ensure_local_demo_admin()
    insert = [s for s, values in db.statements if s.startswith("INSERT INTO platform_users")]
    assert len(insert) == 1
    values = next(v for s, v in db.statements if s.startswith("INSERT INTO platform_users"))
    assert values[1] == "local-demo@bhoomiai.invalid"
    assert ":" in values[2]  # Salted PBKDF2 hash, never a plain-text password.


def test_existing_admin_is_not_replaced(monkeypatch):
    db = FakeDB((4, "Existing Admin", "private@example.invalid", "admin"))
    monkeypatch.setattr(platform, "LOCAL_DEMO_MODE", True)
    monkeypatch.setattr(platform, "conn", lambda: db)
    platform.ensure_local_demo_admin()
    assert not any(s.startswith("INSERT INTO platform_users") for s, _ in db.statements)
