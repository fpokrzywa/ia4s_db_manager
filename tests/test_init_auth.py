import psycopg
from click.testing import CliRunner
from dbmanager.cli import cli


def test_init_auth_creates_user(common_data_url, monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    result = CliRunner().invoke(cli, ["init-auth", "--email",
                                      "new@example.com", "--password",
                                      "TempPass123"])
    assert result.exit_code == 0, result.output
    with psycopg.connect(common_data_url) as conn:
        row = conn.execute(
            "SELECT must_change_password FROM users WHERE email = %s",
            ("new@example.com",)).fetchone()
    assert row is not None
    assert row[0] is True


def test_init_auth_is_idempotent(common_data_url, monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    runner = CliRunner()
    runner.invoke(cli, ["init-auth", "--email", "dup@example.com",
                        "--password", "TempPass123"])
    result = runner.invoke(cli, ["init-auth", "--email", "dup@example.com",
                                 "--password", "TempPass123"])
    assert result.exit_code == 0
    assert "already exists" in result.output
