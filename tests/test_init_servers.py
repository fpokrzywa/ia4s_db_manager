import psycopg
from click.testing import CliRunner
from dbmanager.cli import cli


def test_init_auth_creates_servers_table_and_seeds(common_data_url, server_url,
                                                   monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    monkeypatch.setenv("DATABASE_URL", server_url)
    result = CliRunner().invoke(cli, ["init-auth", "--email", "a@example.com",
                                      "--password", "TempPass123"])
    assert result.exit_code == 0, result.output
    with psycopg.connect(common_data_url) as conn:
        servers = conn.execute(
            "SELECT label, is_default FROM servers").fetchall()
    assert len(servers) == 1
    assert servers[0][1] is True          # seeded server is the default


def test_init_auth_does_not_duplicate_seed(common_data_url, server_url,
                                           monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    monkeypatch.setenv("DATABASE_URL", server_url)
    runner = CliRunner()
    runner.invoke(cli, ["init-auth", "--email", "a@example.com",
                        "--password", "TempPass123"])
    runner.invoke(cli, ["init-auth", "--email", "a@example.com",
                        "--password", "TempPass123"])
    with psycopg.connect(common_data_url) as conn:
        count = conn.execute("SELECT count(*) FROM servers").fetchone()[0]
    assert count == 1                     # second run does not re-seed


def test_init_auth_flags_first_user_as_admin(common_data_url, server_url,
                                              monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    monkeypatch.setenv("DATABASE_URL", server_url)
    # Remove all pre-seeded users so init-auth creates and flags the first user.
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        conn.execute("DELETE FROM users")
    result = CliRunner().invoke(cli, ["init-auth", "--email", "first@example.com",
                                      "--password", "TempPass123"])
    assert result.exit_code == 0, result.output
    with psycopg.connect(common_data_url) as conn:
        row = conn.execute(
            "SELECT is_admin FROM users WHERE email = %s",
            ("first@example.com",)).fetchone()
    assert row[0] is True


def test_init_auth_does_not_flip_existing_admin(common_data_url, server_url,
                                                 monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    monkeypatch.setenv("DATABASE_URL", server_url)
    # Remove all pre-seeded users so only our explicitly created users are present.
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        conn.execute("DELETE FROM users")
    runner = CliRunner()
    runner.invoke(cli, ["init-auth", "--email", "a@example.com",
                        "--password", "TempPass123"])
    # second run with a different email; a@example.com is still admin
    runner.invoke(cli, ["init-auth", "--email", "b@example.com",
                        "--password", "TempPass123"])
    with psycopg.connect(common_data_url) as conn:
        rows = dict(conn.execute(
            "SELECT email, is_admin FROM users ORDER BY id").fetchall())
    assert rows.get("a@example.com") is True
    assert rows.get("b@example.com") in (False, None)


def test_init_auth_reflags_when_no_admins(common_data_url, server_url,
                                          monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    monkeypatch.setenv("DATABASE_URL", server_url)
    runner = CliRunner()
    # Remove all pre-seeded users so init-auth controls which user is admin.
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        conn.execute("DELETE FROM users")
    runner.invoke(cli, ["init-auth", "--email", "a@example.com",
                        "--password", "TempPass123"])
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        conn.execute("UPDATE users SET is_admin = false")
    runner.invoke(cli, ["init-auth", "--email", "a@example.com",
                        "--password", "TempPass123"])
    with psycopg.connect(common_data_url) as conn:
        is_admin = conn.execute(
            "SELECT is_admin FROM users WHERE email = %s",
            ("a@example.com",)).fetchone()[0]
    assert is_admin is True
