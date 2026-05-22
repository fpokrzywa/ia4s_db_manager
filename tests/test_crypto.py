from dbmanager.crypto import encrypt, decrypt


def test_encrypt_decrypt_round_trip():
    token = encrypt("s3cr3t-password")
    assert token != "s3cr3t-password"
    assert decrypt(token) == "s3cr3t-password"


def test_encrypt_is_non_deterministic():
    assert encrypt("same") != encrypt("same")


def test_encrypt_handles_empty_string():
    assert decrypt(encrypt("")) == ""
