import pytest
from fastapi import HTTPException
from dbmanager.auth import require_session


class FakeRequest:
    def __init__(self, session):
        self.session = session


def test_require_session_allows_logged_in():
    require_session(FakeRequest({"user_id": 1}))  # no raise


def test_require_session_rejects_anonymous():
    with pytest.raises(HTTPException) as exc:
        require_session(FakeRequest({}))
    assert exc.value.status_code == 401
