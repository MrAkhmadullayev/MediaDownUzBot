import pytest

from app.enums import Platform
from app.services.urls import (
    InvalidMediaUrlError,
    instagram_story_target_shortcode,
    media_source_key,
    parse_media_url,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("https://youtu.be/dQw4w9WgXcQ?t=2", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        (
            "https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ),
        (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=malicious",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ),
    ],
)
def test_youtube_urls_are_normalized(source: str, expected: str) -> None:
    result = parse_media_url(source)
    assert result.platform == Platform.YOUTUBE
    assert result.normalized == expected


@pytest.mark.parametrize("kind", ["p", "reel", "reels", "tv"])
def test_instagram_urls_are_normalized(kind: str) -> None:
    result = parse_media_url(f"https://instagram.com/{kind}/ABC_123/?utm_source=test")
    assert result.platform == Platform.INSTAGRAM
    assert result.normalized in {
        "https://www.instagram.com/reel/ABC_123/",
        f"https://www.instagram.com/{kind}/ABC_123/",
    }


def test_instagram_shared_highlight_story_is_normalized() -> None:
    source = (
        "https://www.instagram.com/s/aGlnaGxpZ2h0OjE4MDEzMjU0NjUwODg3Mjk2"
        "?story_media_id=3912338590873067115_10449377142&igsh=ignored"
    )

    result = parse_media_url(source)

    assert result.platform == Platform.INSTAGRAM
    assert result.normalized == (
        "https://www.instagram.com/s/aGlnaGxpZ2h0OjE4MDEzMjU0NjUwODg3Mjk2"
        "?story_media_id=3912338590873067115"
    )
    assert instagram_story_target_shortcode(result.normalized) == "DZLazhOCp5r"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "https://instagram.com/stories/test.user/3912338590873067115/?igsh=ignored",
            "https://www.instagram.com/stories/test.user/3912338590873067115/",
        ),
        (
            "https://instagram.com/stories/highlights/18013254650887296/"
            "?story_media_id=3912338590873067115_10449377142",
            "https://www.instagram.com/s/aGlnaGxpZ2h0OjE4MDEzMjU0NjUwODg3Mjk2"
            "?story_media_id=3912338590873067115",
        ),
    ],
)
def test_instagram_story_urls_are_normalized(source: str, expected: str) -> None:
    assert parse_media_url(source).normalized == expected


@pytest.mark.parametrize(
    "source",
    [
        "https://www.instagram.com/p/DOdWFmdCoKQ/?igsh=MXV6ODAzNzFtdGY2ZA==",
        "Mana post: https://www.instagram.com/p/DOdWFmdCoKQ/?igsh=ignored",
        "https://www.instagram.com\n/p/DOdWFmdCoKQ/?igsh=ignored",
        "https://www.insta\u200bgram.com/p/DOdWFmdCoKQ/?igsh=ignored",
    ],
)
def test_instagram_post_is_extracted_from_telegram_message(source: str) -> None:
    result = parse_media_url(source)

    assert result.platform == Platform.INSTAGRAM
    assert result.normalized == "https://www.instagram.com/p/DOdWFmdCoKQ/"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "https://www.instagram.com/share/BAAbCdEf12/",
            "https://www.instagram.com/share/BAAbCdEf12/",
        ),
        (
            "https://www.instagram.com/share/reel/BAAbCdEf12/?igsh=ignored",
            "https://www.instagram.com/share/reel/BAAbCdEf12/",
        ),
    ],
)
def test_instagram_share_urls_are_normalized(source: str, expected: str) -> None:
    assert parse_media_url(source).normalized == expected


@pytest.mark.parametrize(
    "source",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/video",
        "https://youtube.com.evil.test/watch?v=test",
        "https://user:pass@youtube.com/watch?v=test",
        "https://youtube.com:8080/watch?v=test",
        "https://instagram.com/accounts/login/",
        "https://instagram.com/example.profile/",
        "https://instagram.com/s/not_base64?story_media_id=3912338590873067115",
        "https://instagram.com/s/aGlnaGxpZ2h0OjE4MDEzMjU0NjUwODg3Mjk2",
        "https://instagram.com/stories/test.user/not-a-number/",
        "https://instagram.com/stories/highlights/not-a-number/",
        "javascript:alert(1)",
    ],
)
def test_unsafe_urls_are_rejected(source: str) -> None:
    with pytest.raises(InvalidMediaUrlError):
        parse_media_url(source)


def test_media_source_key_is_stable_and_contains_no_url() -> None:
    url = "https://www.youtube.com/watch?v=abc123"

    assert media_source_key(url) == media_source_key(url)
    assert len(media_source_key(url)) == 64
    assert "youtube" not in media_source_key(url)
