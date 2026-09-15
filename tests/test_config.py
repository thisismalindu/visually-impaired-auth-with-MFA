import pytest
from pathlib import Path

import config


def test_non_secret_defaults_load_correctly(monkeypatch):
    for name in (
        "APP_NAME",
        "OTP_EXPIRY_SECONDS",
        "OTP_MAX_ATTEMPTS",
        "OTP_RESEND_COOLDOWN_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = config.load_config()

    assert settings["APP_NAME"] == "Accessible MFA"
    assert settings["OTP_EXPIRY_SECONDS"] == 300
    assert settings["OTP_MAX_ATTEMPTS"] == 5
    assert settings["OTP_RESEND_COOLDOWN_SECONDS"] == 60


def test_environment_variables_override_defaults(monkeypatch):
    monkeypatch.setenv("APP_NAME", "University MFA")
    monkeypatch.setenv("OTP_EXPIRY_SECONDS", "120")
    monkeypatch.setenv("OTP_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "30")
    monkeypatch.setenv("SECRET_KEY", "test-secret-from-environment")

    settings = config.load_config()

    assert settings["APP_NAME"] == "University MFA"
    assert settings["OTP_EXPIRY_SECONDS"] == 120
    assert settings["OTP_MAX_ATTEMPTS"] == 3
    assert settings["OTP_RESEND_COOLDOWN_SECONDS"] == 30
    assert settings["SECRET_KEY"] == "test-secret-from-environment"


def test_invalid_numeric_configuration_is_rejected(monkeypatch):
    monkeypatch.setenv("OTP_MAX_ATTEMPTS", "zero")

    with pytest.raises(config.ConfigurationError, match="OTP_MAX_ATTEMPTS"):
        config.load_config()


def test_runtime_validation_reports_missing_names_without_values():
    with pytest.raises(config.ConfigurationError) as error:
        config.validate_required_config({})

    message = str(error.value)
    assert "SECRET_KEY" in message
    assert "DATABASE_URL" in message
    assert "RESEND_API_KEY" in message
    assert "RESEND_FROM_EMAIL" in message


def test_secret_names_have_no_committed_values():
    example_path = Path(__file__).parents[1] / ".env.example"
    example = example_path.read_text(encoding="utf-8")

    assert "SECRET_KEY=\n" in example
    assert "DATABASE_URL=\n" in example
    assert "RESEND_API_KEY=\n" in example
