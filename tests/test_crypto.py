from app.services.crypto import FieldCipher, create_token, csrf_token, token_hash, tokens_match

KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def test_field_cipher_round_trip() -> None:
    cipher = FieldCipher(KEY)
    encrypted = cipher.encrypt("+998901234567")
    assert encrypted != "+998901234567"
    assert cipher.decrypt(encrypted) == "+998901234567"


def test_tokens_are_random_and_hashable() -> None:
    first = create_token()
    second = create_token()
    assert first != second
    assert len(token_hash(first)) == 64


def test_csrf_is_bound_to_session() -> None:
    first = csrf_token("session-a", KEY)
    second = csrf_token("session-b", KEY)
    assert first != second
    assert tokens_match(first, first)
    assert not tokens_match(first, second)
