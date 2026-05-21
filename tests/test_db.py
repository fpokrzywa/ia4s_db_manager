from dbmanager.db import server_conn, db_conn


def test_server_conn_is_autocommit(server_url):
    with server_conn(server_url) as conn:
        assert conn.autocommit is True
        row = conn.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1


def test_db_conn_targets_named_database(server_url):
    with db_conn(server_url, "postgres") as conn:
        row = conn.execute("SELECT current_database() AS db").fetchone()
        assert row["db"] == "postgres"
