import base64
import binascii
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import SplitResult, parse_qs, urlencode, urlsplit, urlunsplit

from app.enums import Platform


class InvalidMediaUrlError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MediaUrl:
    normalized: str
    platform: Platform


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}
INSTAGRAM_ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def parse_media_url(raw_url: str) -> MediaUrl:
    value = raw_url.strip()
    if len(value) > 2048:
        raise InvalidMediaUrlError("Havola juda uzun")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"}:
        raise InvalidMediaUrlError("Faqat HTTP yoki HTTPS havola qabul qilinadi")
    if parts.username or parts.password:
        raise InvalidMediaUrlError("Noto'g'ri havola")
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.port not in {None, 80, 443}:
        raise InvalidMediaUrlError("Noto'g'ri port")
    if host in YOUTUBE_HOSTS:
        return MediaUrl(_normalize_youtube(parts), Platform.YOUTUBE)
    if host in INSTAGRAM_HOSTS:
        return MediaUrl(_normalize_instagram(parts), Platform.INSTAGRAM)
    raise InvalidMediaUrlError("Faqat YouTube va Instagram havolalari qabul qilinadi")


def media_source_key(normalized_url: str) -> str:
    return sha256(normalized_url.encode("utf-8")).hexdigest()


def instagram_story_target_shortcode(url: str) -> str | None:
    parts = urlsplit(url)
    path_parts = [part for part in parts.path.split("/") if part]
    if len(path_parts) != 3 or path_parts[:2] != ["stories", "highlights"]:
        return None
    media_id = _instagram_story_media_id(parse_qs(parts.query, keep_blank_values=False))
    if media_id is None:
        return None
    number = int(media_id)
    encoded = ""
    while number:
        number, remainder = divmod(number, len(INSTAGRAM_ID_ALPHABET))
        encoded = INSTAGRAM_ID_ALPHABET[remainder] + encoded
    return encoded or INSTAGRAM_ID_ALPHABET[0]


def _normalize_youtube(parts: SplitResult) -> str:
    host = (parts.hostname or "").lower().rstrip(".")
    path = parts.path.rstrip("/") or "/"
    query = parse_qs(parts.query, keep_blank_values=False)
    if host == "youtu.be":
        video_id = path.removeprefix("/").split("/")[0]
    elif path == "/watch":
        video_id = query.get("v", [""])[0]
    elif path.startswith(("/shorts/", "/embed/", "/live/")):
        video_id = path.split("/")[2] if len(path.split("/")) > 2 else ""
    else:
        raise InvalidMediaUrlError("YouTube video havolasi noto'g'ri")
    if not video_id or len(video_id) > 64 or not all(c.isalnum() or c in "_-" for c in video_id):
        raise InvalidMediaUrlError("YouTube video identifikatori noto'g'ri")
    return urlunsplit(("https", "www.youtube.com", "/watch", urlencode({"v": video_id}), ""))


def _normalize_instagram(parts: SplitResult) -> str:
    path_parts = [part for part in parts.path.split("/") if part]
    if len(path_parts) == 2 and path_parts[0] == "s":
        return _normalize_instagram_shared_story(path_parts[1], parts)
    if len(path_parts) in {2, 3} and path_parts[0] == "stories":
        return _normalize_instagram_story(path_parts, parts)
    if len(path_parts) < 2 or path_parts[0] not in {"p", "reel", "reels", "tv"}:
        raise InvalidMediaUrlError("Instagram media havolasi noto'g'ri")
    shortcode = path_parts[1]
    if len(shortcode) > 128 or not all(c.isalnum() or c in "_-" for c in shortcode):
        raise InvalidMediaUrlError("Instagram media identifikatori noto'g'ri")
    media_type = "reel" if path_parts[0] == "reels" else path_parts[0]
    return urlunsplit(("https", "www.instagram.com", f"/{media_type}/{shortcode}/", "", ""))


def _normalize_instagram_shared_story(token: str, parts: SplitResult) -> str:
    if not token or len(token) > 256 or not all(c.isalnum() or c in "-_" for c in token):
        raise InvalidMediaUrlError("Instagram story havolasi noto'g'ri")
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.b64decode(padded, altchars=b"-_", validate=True).decode("ascii")
        media_type, highlight_id = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        raise InvalidMediaUrlError("Instagram story havolasi noto'g'ri") from None
    if media_type != "highlight" or not _valid_numeric_id(highlight_id):
        raise InvalidMediaUrlError("Instagram highlight identifikatori noto'g'ri")
    media_id = _required_instagram_story_media_id(parts)
    query = urlencode({"story_media_id": media_id})
    path = f"/stories/highlights/{highlight_id}/"
    return urlunsplit(("https", "www.instagram.com", path, query, ""))


def _normalize_instagram_story(path_parts: list[str], parts: SplitResult) -> str:
    if len(path_parts) != 3:
        raise InvalidMediaUrlError("Instagram story havolasi to'liq emas")
    owner, story_id = path_parts[1:]
    if owner == "highlights":
        if not _valid_numeric_id(story_id):
            raise InvalidMediaUrlError("Instagram highlight identifikatori noto'g'ri")
        media_id = _instagram_story_media_id(parse_qs(parts.query, keep_blank_values=False))
        query = urlencode({"story_media_id": media_id}) if media_id else ""
    else:
        if not _valid_instagram_username(owner) or not _valid_numeric_id(story_id):
            raise InvalidMediaUrlError("Instagram story identifikatori noto'g'ri")
        query = ""
    path = f"/stories/{owner}/{story_id}/"
    return urlunsplit(("https", "www.instagram.com", path, query, ""))


def _required_instagram_story_media_id(parts: SplitResult) -> str:
    media_id = _instagram_story_media_id(parse_qs(parts.query, keep_blank_values=False))
    if media_id is None:
        raise InvalidMediaUrlError("Instagram story media identifikatori topilmadi")
    return media_id


def _instagram_story_media_id(query: dict[str, list[str]]) -> str | None:
    values = query.get("story_media_id")
    if not values:
        return None
    value = values[0]
    media_id, separator, owner_id = value.partition("_")
    if not _valid_numeric_id(media_id) or (separator and not _valid_numeric_id(owner_id)):
        raise InvalidMediaUrlError("Instagram story media identifikatori noto'g'ri")
    return media_id


def _valid_numeric_id(value: str) -> bool:
    return 1 <= len(value) <= 32 and value.isascii() and value.isdigit()


def _valid_instagram_username(value: str) -> bool:
    return (
        1 <= len(value) <= 30
        and value.isascii()
        and all(character.isalnum() or character in "_." for character in value)
    )
