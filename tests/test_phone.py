import pytest

from app.bot.router import is_local_admin_url, local_admin_link_message, normalize_phone


def test_phone_is_normalized() -> None:
    assert normalize_phone("998 90 123-45-67") == "+998901234567"


def test_invalid_phone_is_rejected() -> None:
    assert normalize_phone("123") is None


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8080/admin/login/token",
        "http://service.localhost/admin/login/token",
        "http://127.0.0.1:8080/admin/login/token",
        "http://[::1]:8080/admin/login/token",
        "http://0.0.0.0:8080/admin/login/token",
    ],
)
def test_local_admin_url_is_detected(url: str) -> None:
    assert is_local_admin_url(url)


def test_public_admin_url_is_not_local() -> None:
    assert not is_local_admin_url("https://admin.example.com/admin/login/token")


def test_local_admin_message_escapes_url() -> None:
    message = local_admin_link_message("http://localhost:8080/?value=<unsafe>")
    assert "<unsafe>" not in message
    assert "&lt;unsafe&gt;" in message
