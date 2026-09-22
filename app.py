"""Flask application factory and foundation health endpoint."""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, redirect, url_for

from auth.flow import auth_bp
from auth.otp import OTPService, OTPSettings, ResendEmailSender, create_otp_blueprint
from config import load_config, validate_required_config


def _register_integrated_blueprints(app: Flask) -> None:
    """Construct the OTP service and register the completed authentication modules."""
    from database import repository

    otp_service = app.config.get("OTP_SERVICE")
    if otp_service is None:
        otp_service = OTPService(
            repository=app.config.get("OTP_REPOSITORY", repository),
            email_sender=ResendEmailSender(
                app.config.get("RESEND_API_KEY"),
                app.config.get("RESEND_FROM_EMAIL"),
            ),
            settings=OTPSettings(
                secret_key=app.config["SECRET_KEY"],
                application_name=app.config["APP_NAME"],
                lifetime_seconds=app.config["OTP_EXPIRY_SECONDS"],
                max_attempts=app.config["OTP_MAX_ATTEMPTS"],
                resend_cooldown_seconds=app.config["OTP_RESEND_COOLDOWN_SECONDS"],
            ),
        )
    otp_repository = app.config.get("OTP_REPOSITORY", repository)
    app.extensions["otp_service"] = otp_service

    app.register_blueprint(auth_bp)
    app.register_blueprint(
        create_otp_blueprint(otp_service, otp_repository)
    )


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the Flask application.

    ``test_config`` is intentionally explicit so tests can use a test secret
    without weakening runtime validation or committing credentials.
    """

    app = Flask(__name__)
    app.config.from_mapping(load_config())
    if test_config:
        app.config.update(test_config)

    if not app.config.get("TESTING", False):
        validate_required_config(app.config)

    @app.get("/health")
    def health() -> tuple[Any, int]:
        return jsonify(status="ok"), 200

    _register_integrated_blueprints(app)

    @app.get("/")
    def index() -> Any:
        return redirect(url_for("auth.login_username"))

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=application.config.get("DEBUG", False))
