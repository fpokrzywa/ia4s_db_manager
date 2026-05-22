from dbmanager.passwords import hash_password, verify_password


def test_hash_then_verify_succeeds():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("hunter2")
    assert verify_password("wrong", h) is False


def test_hash_is_not_plaintext():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert len(h) > 20


def test_verify_handles_garbage_hash():
    assert verify_password("anything", "not-a-real-hash") is False
