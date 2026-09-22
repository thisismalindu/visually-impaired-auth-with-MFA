from __future__ import annotations

import sys
from types import ModuleType

import pytest
from psycopg import OperationalError, errors

import scripts.create_user as create_user_script


def _prepare_script(monkeypatch, tmp_path, repository_module):
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://demo:secret@localhost/test\n")
    monkeypatch.setattr(create_user_script, "ENV_FILE", env_file)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setitem(sys.modules, "database.repository", repository_module)
    monkeypatch.setattr(create_user_script.getpass, "getpass", lambda _: "my-secret-password")


def test_provisioning_loads_database_url_from_project_env(monkeypatch, tmp_path, capsys):
    calls = []
    repository_module = ModuleType("database.repository")
    repository_module.DuplicateUserError = type("DuplicateUserError", (ValueError,), {})
    repository_module.create_user = lambda username, email, password_hash: calls.append(
        (username, email, password_hash)
    )
    _prepare_script(monkeypatch, tmp_path, repository_module)

    result = create_user_script.main(
        ["--username", "demo-user", "--email", "demo@example.test"]
    )

    assert result == 0
    assert calls[0][0:2] == ("demo-user", "demo@example.test")
    assert calls[0][2].startswith("$argon2")
    assert "my-secret-password" not in calls[0][2]
    assert "Demo user 'demo-user' created." in capsys.readouterr().out


def test_missing_database_url_has_clear_message(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(create_user_script, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = create_user_script.main(["--username", "demo", "--email", "demo@example.test"])

    assert result == 1
    assert "DATABASE_URL is missing" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("database_error", "expected_message"),
    [
        (errors.UndefinedTable("relation does not exist"), "tables are missing"),
        (OperationalError("secret-bearing connection detail"), "Could not connect"),
    ],
)
def test_database_failures_are_explained_without_raw_details(
    monkeypatch, tmp_path, capsys, database_error, expected_message
):
    repository_module = ModuleType("database.repository")
    repository_module.DuplicateUserError = type("DuplicateUserError", (ValueError,), {})

    def fail_to_create(*args):
        raise database_error

    repository_module.create_user = fail_to_create
    _prepare_script(monkeypatch, tmp_path, repository_module)

    result = create_user_script.main(
        ["--username", "demo-user", "--email", "demo@example.test"]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert expected_message in captured.err
    assert "secret-bearing connection detail" not in captured.err


def test_duplicate_account_has_clear_message(monkeypatch, tmp_path, capsys):
    duplicate_error = type("DuplicateUserError", (ValueError,), {})
    repository_module = ModuleType("database.repository")
    repository_module.DuplicateUserError = duplicate_error
    repository_module.create_user = lambda *args: (_ for _ in ()).throw(
        duplicate_error("username is already registered")
    )
    _prepare_script(monkeypatch, tmp_path, repository_module)

    result = create_user_script.main(
        ["--username", "demo-user", "--email", "demo@example.test"]
    )

    assert result == 1
    assert "already registered" in capsys.readouterr().err
