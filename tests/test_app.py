from app import create_app


def test_create_app_succeeds_with_test_configuration():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-only-secret"})

    assert app is not None


def test_health_returns_success():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-only-secret"})
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_testing_mode_is_enabled_when_configured():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-only-secret"})

    assert app.testing is True
