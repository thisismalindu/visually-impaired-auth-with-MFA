from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from psycopg import errors

from database import repository


def fake_connection(result=None, rowcount=1):
    conn = MagicMock()
    cursor = conn.execute.return_value
    cursor.fetchone.return_value = result
    cursor.rowcount = rowcount
    return conn


def test_get_user_by_username_uses_parameterized_query():
    conn = fake_connection({"id": 1})
    with patch("database.repository.connection") as connection:
        connection.return_value.__enter__.return_value = conn
        assert repository.get_user_by_username("alice' OR '1'='1") == {"id": 1}

    params = conn.execute.call_args.args[1]
    assert params == ("alice' OR '1'='1",)
    assert "%s" in conn.execute.call_args.args[0]


def test_create_user_returns_inserted_user():
    user = {"id": 1, "username": "alice"}
    conn = fake_connection(user)
    with patch("database.repository.connection") as connection:
        connection.return_value.__enter__.return_value = conn
        assert repository.create_user("alice", "a@example.com", "hash") == user
    assert conn.execute.call_args.args[1] == ("alice", "a@example.com", "hash")


@pytest.mark.parametrize(
    ("constraint", "message"),
    [
        ("users_username_key", "username is already registered"),
        ("users_email_key", "email is already registered"),
        (None, "user already exists"),
    ],
)
def test_duplicate_constraint_is_translated(constraint, message):
    violation = SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint))
    translated = repository._duplicate_user_error(violation)
    assert str(translated) == message


def test_create_user_translates_unique_violation():
    conn = MagicMock()
    conn.execute.side_effect = errors.UniqueViolation()
    with patch("database.repository.connection") as connection:
        connection.return_value.__enter__.return_value = conn
        with pytest.raises(repository.DuplicateUserError):
            repository.create_user("alice", "a@example.com", "hash")


def test_otp_creation_and_active_lookup():
    challenge = {"id": 7, "user_id": 1, "used": False}
    conn = fake_connection(challenge)
    expiry = datetime.now(timezone.utc)
    with patch("database.repository.connection") as connection:
        connection.return_value.__enter__.return_value = conn
        assert repository.create_otp_challenge(1, "otp-hash", expiry) == challenge
        assert repository.get_active_otp_challenge(1) == challenge
    assert conn.execute.call_args.args[1] == (1,)


def test_mark_used_and_increment_attempts_return_update_status():
    conn = fake_connection(rowcount=1)
    with patch("database.repository.connection") as connection:
        connection.return_value.__enter__.return_value = conn
        assert repository.increment_otp_attempts(7) is True
        assert repository.mark_otp_used(7) is True
    assert all("%s" in call.args[0] for call in conn.execute.call_args_list)


def test_update_operations_report_no_change_for_used_or_expired_challenge():
    conn = fake_connection(rowcount=0)
    with patch("database.repository.connection") as connection:
        connection.return_value.__enter__.return_value = conn
        assert repository.increment_otp_attempts(7) is False
        assert repository.mark_otp_used(7) is False


def test_invalidate_active_challenges_is_scoped_to_user():
    conn = fake_connection(rowcount=2)
    with patch("database.repository.connection") as connection:
        connection.return_value.__enter__.return_value = conn
        assert repository.invalidate_active_otp_challenges(3) == 2
    assert conn.execute.call_args.args[1] == (3,)
