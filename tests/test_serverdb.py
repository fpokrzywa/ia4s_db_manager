from dbmanager import serverdb
from dbmanager.authdb import auth_conn


def test_create_and_get_server(common_data_url):
    with auth_conn(common_data_url) as conn:
        created = serverdb.create_server(
            conn, label="prod", host="db.example.com", port=5432,
            username="admin", password="pw", is_default=True)
        assert created["label"] == "prod"
        fetched = serverdb.get_server(conn, created["id"])
        assert fetched["host"] == "db.example.com"
        assert fetched["password_enc"] != "pw"          # stored encrypted


def test_list_servers_excludes_password(common_data_url):
    with auth_conn(common_data_url) as conn:
        serverdb.create_server(conn, label="s1", host="h", port=5432,
                               username="u", password="pw")
        rows = serverdb.list_servers(conn)
    assert rows and all("password_enc" not in r for r in rows)


def test_default_server_prefers_is_default(common_data_url):
    with auth_conn(common_data_url) as conn:
        serverdb.create_server(conn, label="a", host="h", port=5432,
                               username="u", password="pw")
        b = serverdb.create_server(conn, label="b", host="h", port=5432,
                                   username="u", password="pw", is_default=True)
        assert serverdb.default_server(conn)["id"] == b["id"]


def test_setting_default_clears_other_defaults(common_data_url):
    with auth_conn(common_data_url) as conn:
        a = serverdb.create_server(conn, label="a", host="h", port=5432,
                                   username="u", password="pw", is_default=True)
        serverdb.create_server(conn, label="b", host="h", port=5432,
                               username="u", password="pw", is_default=True)
        assert serverdb.get_server(conn, a["id"])["is_default"] is False


def test_update_server_keeps_password_when_none(common_data_url):
    with auth_conn(common_data_url) as conn:
        s = serverdb.create_server(conn, label="s", host="h", port=5432,
                                   username="u", password="orig")
        before = serverdb.get_server(conn, s["id"])["password_enc"]
        serverdb.update_server(conn, s["id"], label="s2", host="h2", port=5433,
                               username="u2", password=None,
                               maintenance_db="postgres", sslmode="require",
                               is_default=False, notes="x")
        after = serverdb.get_server(conn, s["id"])
        assert after["password_enc"] == before          # unchanged
        assert after["host"] == "h2" and after["port"] == 5433


def test_delete_server(common_data_url):
    with auth_conn(common_data_url) as conn:
        s = serverdb.create_server(conn, label="gone", host="h", port=5432,
                                   username="u", password="pw")
        assert serverdb.delete_server(conn, s["id"]) is True
        assert serverdb.get_server(conn, s["id"]) is None


def test_conninfo_for_decrypts_password(common_data_url):
    with auth_conn(common_data_url) as conn:
        s = serverdb.create_server(conn, label="c", host="h.example", port=6000,
                                   username="bob", password="topsecret",
                                   sslmode="require")
        full = serverdb.get_server(conn, s["id"])
    info = serverdb.conninfo_for(full, dbname="mydb")
    assert "password=topsecret" in info
    assert "host=h.example" in info and "dbname=mydb" in info
