import pytest
from fastapi import HTTPException
from dbmanager.auth import password_matches, require_session


class FakeRequest:
    def __init__(self, session):
        self.session = session


def test_password_matches_true():
    assert password_matches("hunter2", "hunter2") is True


def test_password_matches_false():
    assert password_matches("wrong", "hunter2") is False


def test_require_session_allows_authenticated():
    require_session(FakeRequest({"authenticated": True}))  # no raise


def test_require_session_rejects_anonymous():
    with pytest.raises(HTTPException) as exc:
        require_session(FakeRequest({}))
    assert exc.value.status_code == 401
