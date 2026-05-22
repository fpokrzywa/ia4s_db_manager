import psycopg
from dbmanager import authdb
from dbmanager.passwords import hash_password


def test_create_and_get_user(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        created = authdb.create_user(conn, "ALICE@x.com", hash_password("pw"))
        assert created["email"] == "alice@x.com"
        assert created["must_change_password"] is True
        fetched = authdb.get_user_by_email(conn, "alice@x.com")
        assert fetched["id"] == created["id"]
        assert authdb.get_user_by_id(conn, created["id"])["email"] == "alice@x.com"


def test_get_missing_user_returns_none(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        assert authdb.get_user_by_email(conn, "nobody@x.com") is None


def test_record_event_appends_row(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        authdb.record_event(conn, email="a@x.com", user_id=None,
                            event="login_failed", ip_address="1.2.3.4",
                            user_agent="pytest")
    with psycopg.connect(common_data_url) as conn:
        row = conn.execute(
            "SELECT event, ip_address FROM user_sessions WHERE email=%s",
            ("a@x.com",)).fetchone()
    assert row == ("login_failed", "1.2.3.4")


def test_note_failed_attempt_locks_at_threshold(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.create_user(conn, "lock@x.com", hash_password("pw"))
        locked = False
        for _ in range(5):
            locked = authdb.note_failed_attempt(conn, user["id"], 5, 15)
        assert locked is True
        refetched = authdb.get_user_by_id(conn, user["id"])
        assert refetched["locked_until"] is not None


def test_note_successful_login_resets_attempts(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.create_user(conn, "ok@x.com", hash_password("pw"))
        authdb.note_failed_attempt(conn, user["id"], 5, 15)
        authdb.note_successful_login(conn, user["id"])
        refetched = authdb.get_user_by_id(conn, user["id"])
        assert refetched["failed_attempts"] == 0
        assert refetched["last_login_at"] is not None


def test_set_password_clears_must_change_and_lock(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.create_user(conn, "sp@x.com", hash_password("old"))
        authdb.set_password(conn, user["id"], hash_password("new"),
                            must_change=False)
        refetched = authdb.get_user_by_id(conn, user["id"])
        assert refetched["must_change_password"] is False


def test_list_users_excludes_password_hash(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        authdb.create_user(conn, "lu@x.com", hash_password("pw"))
        rows = authdb.list_users(conn)
    assert all("password_hash" not in r for r in rows)
    assert any(r["email"] == "lu@x.com" for r in rows)


def test_update_user_deactivates_and_unlocks(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.create_user(conn, "uu@x.com", hash_password("pw"))
        authdb.note_failed_attempt(conn, user["id"], 5, 15)
        updated = authdb.update_user(conn, user["id"], is_active=False,
                                     unlock=True)
        assert updated["is_active"] is False
        assert updated["failed_attempts"] == 0
        assert updated["locked_until"] is None
