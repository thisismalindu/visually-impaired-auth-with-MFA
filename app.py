"""Flask application factory and foundation health endpoint."""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify

from config import load_config, validate_required_config


def _register_integrated_blueprints(app: Flask) -> None:
    """Register member blueprints when their modules are merged.

    The imports stay optional while the parallel feature branches are under
    development. Integration should replace this hook's comments with imports
    of the completed blueprints, keeping application construction centralized.
    """

    # Example integration points (not implemented on the foundation branch):
    # from auth.flow import auth_bp
    # from auth.otp import otp_bp
    # app.register_blueprint(auth_bp)
    # app.register_blueprint(otp_bp)


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
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=application.config.get("DEBUG", False))
