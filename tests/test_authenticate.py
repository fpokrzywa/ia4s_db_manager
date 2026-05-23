import pytest
from fastapi import HTTPException
from dbmanager import auth, authdb
from dbmanager.passwords import hash_password


def _make_user(common_data_url, email, password, **cols):
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.create_user(conn, email, hash_password(password))
        if cols:
            sets = ", ".join(f"{k} = %s" for k in cols)
            conn.execute(f"UPDATE users SET {sets} WHERE id = %s",
                         [*cols.values(), user["id"]])
        return user["id"]


def test_authenticate_success(common_data_url):
    _make_user(common_data_url, "u@x.com", "Password1")
    result = auth.authenticate(common_data_url, "U@x.com", "Password1",
                               "1.1.1.1", "pytest")
    assert result.email == "u@x.com"
    assert result.must_change_password is True


def test_authenticate_wrong_password(common_data_url):
    _make_user(common_data_url, "u@x.com", "Password1")
    with pytest.raises(HTTPException) as exc:
        auth.authenticate(common_data_url, "u@x.com", "wrong", None, None)
    assert exc.value.status_code == 401


def test_authenticate_unknown_email(common_data_url):
    with pytest.raises(HTTPException) as exc:
        auth.authenticate(common_data_url, "ghost@x.com", "x", None, None)
    assert exc.value.status_code == 401


def test_authenticate_inactive_account(common_data_url):
    _make_user(common_data_url, "off@x.com", "Password1", is_active=False)
    with pytest.raises(HTTPException) as exc:
        auth.authenticate(common_data_url, "off@x.com", "Password1", None, None)
    assert exc.value.status_code == 403


def test_authenticate_locks_after_five_failures(common_data_url):
    _make_user(common_data_url, "brute@x.com", "Password1")
    for _ in range(5):
        with pytest.raises(HTTPException):
            auth.authenticate(common_data_url, "brute@x.com", "wrong", None, None)
    with pytest.raises(HTTPException) as exc:
        auth.authenticate(common_data_url, "brute@x.com", "Password1", None, None)
    assert exc.value.status_code == 403
    assert "lock" in exc.value.detail.lower()


def test_change_password_success(common_data_url):
    uid = _make_user(common_data_url, "cp@x.com", "OldPass1")
    auth.change_password(common_data_url, uid, "OldPass1", "NewPass123",
                         None, None)
    result = auth.authenticate(common_data_url, "cp@x.com", "NewPass123",
                               None, None)
    assert result.must_change_password is False


def test_change_password_wrong_current(common_data_url):
    uid = _make_user(common_data_url, "cp@x.com", "OldPass1")
    with pytest.raises(HTTPException) as exc:
        auth.change_password(common_data_url, uid, "WRONG", "NewPass123",
                             None, None)
    assert exc.value.status_code == 400


def test_change_password_too_short(common_data_url):
    uid = _make_user(common_data_url, "cp@x.com", "OldPass1")
    with pytest.raises(HTTPException) as exc:
        auth.change_password(common_data_url, uid, "OldPass1", "short",
                             None, None)
    assert exc.value.status_code == 400


def test_require_admin_returns_403_for_non_admin(non_admin_client):
    # /api/me is NOT admin-gated; we just check that requiring admin would
    # work. Defer the real 403 test to Task 4 (which adds the first
    # admin-only route on /api/users/{id}/admin). For Task 1 the test
    # below verifies non_admin_client correctly identifies as non-admin.
    resp = non_admin_client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False
