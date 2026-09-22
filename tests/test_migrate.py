import scripts.migrate as migrate


def test_migration_requires_direct_database_url(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(migrate, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)

    result = migrate.main([])

    assert result == 1
    assert "DATABASE_URL_UNPOOLED is missing" in capsys.readouterr().err


def test_migration_applies_schema_with_direct_url(monkeypatch, tmp_path, capsys):
    schema = tmp_path / "schema.sql"
    schema.write_text("CREATE TABLE test_table (id INTEGER);", encoding="utf-8")
    calls = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql):
            calls.append(("execute", sql))

        def commit(self):
            calls.append(("commit",))

    def connect(url, connect_timeout):
        calls.append(("connect", url, connect_timeout))
        return Connection()

    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgresql://secret")
    monkeypatch.setattr(migrate.psycopg, "connect", connect)

    result = migrate.main(["--schema", str(schema)])

    assert result == 0
    assert calls == [
        ("connect", "postgresql://secret", 10),
        ("execute", "CREATE TABLE test_table (id INTEGER);"),
        ("commit",),
    ]
    assert "secret" not in capsys.readouterr().out


def test_migration_hides_connection_details(monkeypatch, tmp_path, capsys):
    schema = tmp_path / "schema.sql"
    schema.write_text("SELECT 1;", encoding="utf-8")
    secret_detail = "postgresql://secret@host/database"

    def connect(*args, **kwargs):
        raise migrate.OperationalError(secret_detail)

    monkeypatch.setenv("DATABASE_URL_UNPOOLED", secret_detail)
    monkeypatch.setattr(migrate.psycopg, "connect", connect)

    result = migrate.main(["--schema", str(schema)])

    assert result == 1
    captured = capsys.readouterr()
    assert "Could not connect to PostgreSQL" in captured.err
    assert secret_detail not in captured.err
