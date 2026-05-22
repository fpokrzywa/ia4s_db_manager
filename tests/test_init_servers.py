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
