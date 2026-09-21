from auth.password_utils import hash_password, verify_password_hash


def test_password_hash_is_argon2_and_does_not_contain_plaintext():
    password = "correct horse battery staple"

    password_hash = hash_password(password)

    assert password_hash.startswith("$argon2")
    assert password not in password_hash


def test_password_verification_accepts_only_the_original_password():
    password_hash = hash_password("university-demo-password")

    assert verify_password_hash(password_hash, "university-demo-password") is True
    assert verify_password_hash(password_hash, "wrong-password") is False
    assert verify_password_hash("not-a-valid-hash", "wrong-password") is False
