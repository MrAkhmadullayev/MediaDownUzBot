import math
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yt_dlp
from yt_dlp.networking.exceptions import RequestError
from yt_dlp.utils import DownloadError

from app.config import Settings
from app.enums import MediaType, Platform
from app.services.urls import instagram_story_target_shortcode


class MediaProcessingError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class MediaInfo:
    title: str
    duration_seconds: int | None
    qualities: list[int]
    quality_sizes: dict[str, dict[str, int | None]]


class MediaKind(StrEnum):
    VIDEO = "video"
    PHOTO = "photo"
    ANIMATION = "animation"
    DOCUMENT = "document"


@dataclass(frozen=True, slots=True)
class DownloadedItem:
    path: Path
    size_bytes: int
    kind: MediaKind


@dataclass(frozen=True, slots=True)
class DownloadedMedia:
    path: Path
    title: str
    duration_seconds: int | None
    size_bytes: int
    items: tuple[DownloadedItem, ...] = ()

    @property
    def media_items(self) -> tuple[DownloadedItem, ...]:
        if self.items:
            return self.items
        return (
            DownloadedItem(
                path=self.path,
                size_bytes=self.size_bytes,
                kind=media_kind_for_path(self.path),
            ),
        )


class MediaService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def probe(self, url: str) -> MediaInfo:
        if self._is_instagram_url(url):
            return MediaInfo(
                title="Instagram media",
                duration_seconds=None,
                qualities=[],
                quality_sizes={"video": {}, "audio": {}},
            )
        for use_cookies in self._youtube_cookie_attempts():
            try:
                return self._probe_youtube(url, use_cookies=use_cookies)
            except MediaProcessingError:
                raise
            except (DownloadError, RequestError) as exc:
                error = self._mapped_error(str(exc))
                if self._should_retry_with_cookies(error, use_cookies):
                    continue
                raise error from None
            except Exception as exc:
                raise MediaProcessingError("internal", type(exc).__name__) from None
        raise MediaProcessingError("cookies_required")

    def download(
        self,
        url: str,
        job_id: uuid.UUID,
        media_type: MediaType,
        quality: str,
    ) -> DownloadedMedia:
        work_dir = self._prepare_work_dir(job_id)
        if self._is_instagram_url(url):
            return self._download_instagram(url, work_dir)
        for use_cookies in self._youtube_cookie_attempts():
            if use_cookies:
                self._clear_work_dir(work_dir)
            try:
                return self._download_youtube(
                    url,
                    work_dir,
                    media_type,
                    quality,
                    use_cookies=use_cookies,
                )
            except MediaProcessingError:
                raise
            except (DownloadError, RequestError) as exc:
                error = self._mapped_error(str(exc))
                if self._should_retry_with_cookies(error, use_cookies):
                    continue
                raise error from None
            except Exception as exc:
                raise MediaProcessingError("internal", type(exc).__name__) from None
        raise MediaProcessingError("cookies_required")

    def _probe_youtube(self, url: str, *, use_cookies: bool) -> MediaInfo:
        with self._prepared_options(url, use_cookies=use_cookies) as options:
            options.update({"skip_download": True})
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=False)
        media = self._single_media(info)
        duration = self._duration(media)
        qualities = self._qualities(media)
        return MediaInfo(
            title=self._title(media),
            duration_seconds=duration,
            qualities=qualities,
            quality_sizes=self._quality_sizes(media, qualities, duration),
        )

    def _download_youtube(
        self,
        url: str,
        work_dir: Path,
        media_type: MediaType,
        quality: str,
        *,
        use_cookies: bool,
    ) -> DownloadedMedia:
        with self._prepared_options(url, use_cookies=use_cookies) as options:
            options.update(
                {
                    "paths": {"home": str(work_dir), "temp": str(work_dir)},
                    "outtmpl": {"default": "media.%(ext)s"},
                    "overwrites": True,
                    "continuedl": False,
                    "max_filesize": self.settings.upload_limit_bytes,
                }
            )
            if media_type == MediaType.VIDEO:
                options.update(self._video_options(quality))
            else:
                options.update(self._audio_options(quality))
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=True)
        media = self._single_media(info)
        duration = self._duration(media)
        path = self._find_output_file(work_dir)
        path.chmod(0o644)
        size = path.stat().st_size
        if size > self.settings.upload_limit_bytes:
            raise MediaProcessingError("too_large")
        return DownloadedMedia(
            path=path,
            title=self._title(media),
            duration_seconds=duration,
            size_bytes=size,
        )

    def _download_instagram(self, url: str, work_dir: Path) -> DownloadedMedia:
        try:
            with self._prepared_instagram_cookie() as cookie_file:
                command = [
                    sys.executable,
                    "-m",
                    "gallery_dl",
                    "--config-ignore",
                    "--no-input",
                    "--no-part",
                    "--no-mtime",
                    "--no-skip",
                    "--restrict-filenames",
                    "ascii",
                    "--retries",
                    "5",
                    "--http-timeout",
                    "30",
                    "--sleep-request",
                    "0.5",
                    "--filesize-max",
                    str(self.settings.upload_limit_bytes),
                    "--range",
                    "1-100",
                    "-o",
                    "extractor.instagram.videos=true",
                    "-o",
                    "extractor.instagram.audio=false",
                    "-o",
                    "extractor.instagram.previews=false",
                    "-f",
                    "{num:>03}_{media_id}.{extension}",
                    "-D",
                    str(work_dir),
                ]
                if cookie_file is not None:
                    command.extend(("-C", str(cookie_file)))
                command.append(url)
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.settings.MAX_DOWNLOAD_SECONDS,
                )
            output = "\n".join((result.stdout, result.stderr)).strip()
            if result.returncode != 0:
                raise self._mapped_instagram_error(output)
            items = self._instagram_output_files(work_dir)
            if not items:
                if self._is_oversized_output(output):
                    raise MediaProcessingError("too_large")
                raise self._mapped_instagram_error(output or "No downloadable media found")
            if any(item.size_bytes > self.settings.upload_limit_bytes for item in items):
                raise MediaProcessingError("too_large")
            size = sum(item.size_bytes for item in items)
            return DownloadedMedia(
                path=items[0].path,
                title="Instagram media",
                duration_seconds=None,
                size_bytes=size,
                items=items,
            )
        except MediaProcessingError:
            raise
        except subprocess.TimeoutExpired:
            raise MediaProcessingError("timeout") from None
        except OSError as exc:
            raise MediaProcessingError("internal", type(exc).__name__) from None

    def cleanup(self, job_id: uuid.UUID) -> None:
        root = self.settings.VIDEOS_DIR.resolve()
        target = (root / str(job_id)).resolve()
        if target.parent != root or target.name != str(job_id):
            raise ValueError("Noto'g'ri vaqtinchalik papka")
        if target.exists():
            shutil.rmtree(target)

    def cleanup_stale(self, older_than_seconds: int) -> int:
        root = self.settings.VIDEOS_DIR.resolve()
        if not root.exists():
            return 0
        removed = 0
        cutoff = time.time() - older_than_seconds
        for child in root.iterdir():
            if not child.is_dir() or child.is_symlink():
                continue
            try:
                uuid.UUID(child.name)
            except ValueError:
                continue
            resolved = child.resolve()
            if resolved.parent == root and child.stat().st_mtime < cutoff:
                shutil.rmtree(resolved)
                removed += 1
        return removed

    def _base_options(self, url: str | None = None) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "playlist_items": "1",
            "socket_timeout": 30,
            "retries": 5,
            "fragment_retries": 5,
            "extractor_retries": 3,
            "file_access_retries": 3,
            "concurrent_fragment_downloads": 4,
            "cachedir": False,
            "restrictfilenames": True,
            "windowsfilenames": True,
        }
        provider_url = self.settings.YTDLP_POT_PROVIDER_URL
        if provider_url:
            options["extractor_args"] = {
                "youtubepot-bgutilhttp": {"base_url": [provider_url]},
            }
        proxy_url = self.settings.YTDLP_PROXY_URL
        if proxy_url:
            options["proxy"] = proxy_url.get_secret_value()
        target_shortcode = instagram_story_target_shortcode(url) if url else None
        if target_shortcode:
            options.pop("playlist_items")
            options["match_filter"] = self._instagram_story_match_filter(target_shortcode)
        return options

    @contextmanager
    def _prepared_options(
        self,
        url: str | None = None,
        *,
        use_cookies: bool = True,
    ) -> Iterator[dict[str, Any]]:
        options = self._base_options(url)
        if not use_cookies:
            yield options
            return
        source = self.settings.YTDLP_COOKIES_FILE
        if source is None:
            yield options
            return
        if not source.is_file():
            raise MediaProcessingError("cookies_required", "CookieFileMissing")
        with tempfile.TemporaryDirectory(prefix="mediadown-ytdlp-") as temp_dir:
            cookie_file = Path(temp_dir) / "cookies.txt"
            shutil.copyfile(source, cookie_file)
            cookie_file.chmod(0o600)
            options["cookiefile"] = str(cookie_file)
            yield options

    def _youtube_cookie_attempts(self) -> tuple[bool, ...]:
        if self.settings.YTDLP_COOKIES_FILE is None:
            return (False,)
        return False, True

    def _should_retry_with_cookies(
        self,
        error: MediaProcessingError,
        use_cookies: bool,
    ) -> bool:
        return (
            not use_cookies
            and self.settings.YTDLP_COOKIES_FILE is not None
            and error.code in {"cookies_required", "login_required", "private"}
        )

    @staticmethod
    def _clear_work_dir(work_dir: Path) -> None:
        for child in work_dir.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)

    @contextmanager
    def _prepared_instagram_cookie(self) -> Iterator[Path | None]:
        source = self.settings.INSTAGRAM_COOKIES_FILE
        if source is None:
            yield None
            return
        if not source.is_file():
            raise MediaProcessingError("login_required", "CookieFileMissing")
        with tempfile.TemporaryDirectory(prefix="mediadown-instagram-") as temp_dir:
            cookie_file = Path(temp_dir) / "cookies.txt"
            shutil.copyfile(source, cookie_file)
            cookie_file.chmod(0o600)
            yield cookie_file

    @staticmethod
    def _instagram_story_match_filter(target_shortcode: str) -> Any:
        def match_story(info: dict[str, Any], *, incomplete: bool = False) -> str | None:
            candidate = info.get("id")
            if candidate is not None and candidate != target_shortcode:
                return "Boshqa Instagram story elementi o'tkazib yuborildi"
            return None

        return match_story

    def _video_options(self, quality: str) -> dict[str, Any]:
        if quality == "best":
            height = self.settings.MAX_VIDEO_HEIGHT
        else:
            try:
                height = int(quality)
            except ValueError as exc:
                raise MediaProcessingError("invalid_media") from exc
        if height < 144 or height > self.settings.MAX_VIDEO_HEIGHT:
            raise MediaProcessingError("invalid_media")
        selector = (
            f"bestvideo[height<={height}][vcodec^=avc1][ext=mp4]+"
            "bestaudio[acodec^=mp4a]/"
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={height}][ext=mp4]/best[height<={height}]"
        )
        return {
            "format": selector,
            "merge_output_format": "mp4",
            "postprocessors": [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
            ],
        }

    @staticmethod
    def _audio_options(quality: str) -> dict[str, Any]:
        if quality == "m4a":
            codec = "m4a"
            bitrate = "256"
        elif quality in {"128", "192"}:
            codec = "mp3"
            bitrate = quality
        else:
            raise MediaProcessingError("invalid_media")
        return {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": codec,
                    "preferredquality": bitrate,
                }
            ],
        }

    def _prepare_work_dir(self, job_id: uuid.UUID) -> Path:
        root = self.settings.VIDEOS_DIR.resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o755)
        root.chmod(0o755)
        work_dir = (root / str(job_id)).resolve()
        if work_dir.parent != root:
            raise ValueError("Noto'g'ri vaqtinchalik papka")
        work_dir.mkdir(mode=0o755)
        return work_dir

    @staticmethod
    def _single_media(info: dict[str, Any] | None) -> dict[str, Any]:
        if not info:
            raise MediaProcessingError("invalid_media")
        entries = info.get("entries")
        if entries:
            for entry in entries:
                if entry:
                    return entry
            raise MediaProcessingError("invalid_media")
        return info

    def _qualities(self, info: dict[str, Any]) -> list[int]:
        values = {
            int(item["height"])
            for item in info.get("formats", [])
            if item.get("height")
            and item.get("vcodec") not in {None, "none"}
            and 144 <= int(item["height"]) <= self.settings.MAX_VIDEO_HEIGHT
        }
        if info.get("height"):
            height = int(info["height"])
            if 144 <= height <= self.settings.MAX_VIDEO_HEIGHT:
                values.add(height)
        if not values:
            return [360]
        ordered = sorted(values)
        canonical = [value for value in (360, 480, 720, 1080, 1440, 2160, 4320) if value in values]
        result = canonical or ordered
        return result[-6:]

    def _quality_sizes(
        self,
        info: dict[str, Any],
        qualities: list[int],
        duration: int | None,
    ) -> dict[str, dict[str, int | None]]:
        formats = [item for item in info.get("formats", []) if isinstance(item, dict)]
        return {
            "video": {
                str(quality): self._estimated_video_size(formats, quality, duration)
                for quality in qualities
            },
            "audio": {
                "128": self._estimated_encoded_audio_size(duration, 128),
                "192": self._estimated_encoded_audio_size(duration, 192),
                "m4a": self._estimated_m4a_size(formats, duration),
            },
        }

    def _estimated_video_size(
        self,
        formats: list[dict[str, Any]],
        height: int,
        duration: int | None,
    ) -> int | None:
        video_only = [
            item
            for item in formats
            if self._has_video(item)
            and not self._has_audio(item)
            and self._format_height(item) <= height
        ]
        audio_only = [
            item for item in formats if self._has_audio(item) and not self._has_video(item)
        ]
        preferred_pairs = (
            (
                [
                    item
                    for item in video_only
                    if item.get("ext") == "mp4" and str(item.get("vcodec") or "").startswith("avc1")
                ],
                [item for item in audio_only if str(item.get("acodec") or "").startswith("mp4a")],
            ),
            (
                [item for item in video_only if item.get("ext") == "mp4"],
                [item for item in audio_only if item.get("ext") == "m4a"],
            ),
        )
        for videos, audios in preferred_pairs:
            if videos and audios:
                return self._combined_size(
                    self._best_video(videos),
                    self._best_audio(audios),
                    duration,
                )
        progressive = [
            item
            for item in formats
            if self._has_video(item)
            and self._has_audio(item)
            and self._format_height(item) <= height
        ]
        mp4_progressive = [item for item in progressive if item.get("ext") == "mp4"]
        selected = self._best_video(mp4_progressive or progressive)
        return self._with_container_overhead(self._format_size(selected, duration))

    def _estimated_m4a_size(
        self,
        formats: list[dict[str, Any]],
        duration: int | None,
    ) -> int | None:
        audio_only = [
            item for item in formats if self._has_audio(item) and not self._has_video(item)
        ]
        m4a = [item for item in audio_only if item.get("ext") == "m4a"]
        selected = self._best_audio(m4a or audio_only)
        return self._with_container_overhead(self._format_size(selected, duration))

    @staticmethod
    def _estimated_encoded_audio_size(duration: int | None, bitrate: int) -> int | None:
        if duration is None:
            return None
        return math.ceil(duration * bitrate * 1000 / 8 * 1.01)

    def _combined_size(
        self,
        video: dict[str, Any] | None,
        audio: dict[str, Any] | None,
        duration: int | None,
    ) -> int | None:
        video_size = self._format_size(video, duration)
        audio_size = self._format_size(audio, duration)
        if video_size is None or audio_size is None:
            return None
        return self._with_container_overhead(video_size + audio_size)

    @classmethod
    def _format_size(cls, item: dict[str, Any] | None, duration: int | None) -> int | None:
        if item is None:
            return None
        for field in ("filesize", "filesize_approx"):
            value = cls._positive_float(item.get(field))
            if value is not None:
                return math.ceil(value)
        bitrate = cls._positive_float(item.get("tbr"))
        if bitrate is None or duration is None:
            return None
        return math.ceil(duration * bitrate * 1000 / 8)

    @staticmethod
    def _with_container_overhead(size: int | None) -> int | None:
        return math.ceil(size * 1.01) if size is not None else None

    @classmethod
    def _best_video(cls, formats: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not formats:
            return None
        return max(
            formats,
            key=lambda item: (
                cls._format_height(item),
                cls._positive_float(item.get("fps")) or 0,
                cls._positive_float(item.get("tbr")) or 0,
                cls._positive_float(item.get("filesize")) or 0,
            ),
        )

    @classmethod
    def _best_audio(cls, formats: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not formats:
            return None
        return max(
            formats,
            key=lambda item: (
                cls._positive_float(item.get("abr")) or cls._positive_float(item.get("tbr")) or 0,
                cls._positive_float(item.get("filesize")) or 0,
            ),
        )

    @staticmethod
    def _has_video(item: dict[str, Any]) -> bool:
        return item.get("vcodec") not in {None, "none"}

    @staticmethod
    def _has_audio(item: dict[str, Any]) -> bool:
        return item.get("acodec") not in {None, "none"}

    @classmethod
    def _format_height(cls, item: dict[str, Any]) -> int:
        value = cls._positive_float(item.get("height"))
        return int(value or 0)

    @staticmethod
    def _positive_float(value: object) -> float | None:
        try:
            result = float(str(value))
        except (TypeError, ValueError):
            return None
        return result if result > 0 else None

    @staticmethod
    def _title(info: dict[str, Any]) -> str:
        title = str(info.get("title") or "Media").strip()
        return title[:500] or "Media"

    @staticmethod
    def _duration(info: dict[str, Any]) -> int | None:
        duration = info.get("duration")
        if duration is None:
            return None
        try:
            return max(0, int(float(duration)))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _find_output_file(work_dir: Path) -> Path:
        allowed = {".mp4", ".mp3", ".m4a", ".webm", ".mkv", ".mov"}
        files = [
            path
            for path in work_dir.iterdir()
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in allowed
        ]
        if not files:
            raise MediaProcessingError("invalid_media")
        path = max(files, key=lambda item: item.stat().st_size).resolve()
        if path.parent != work_dir.resolve():
            raise MediaProcessingError("internal")
        return path

    @staticmethod
    def _instagram_output_files(work_dir: Path) -> tuple[DownloadedItem, ...]:
        root = work_dir.resolve()
        allowed = {".gif", ".jpeg", ".jpg", ".m4v", ".mov", ".mp4", ".png", ".webm", ".webp"}
        items: list[DownloadedItem] = []
        for candidate in sorted(work_dir.rglob("*")):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            path = candidate.resolve()
            if root not in path.parents or path.suffix.lower() not in allowed:
                continue
            path.chmod(0o644)
            items.append(
                DownloadedItem(
                    path=path,
                    size_bytes=path.stat().st_size,
                    kind=media_kind_for_path(path),
                )
            )
        return tuple(items)

    @staticmethod
    def _is_instagram_url(url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
        return host in {"instagram.com", "www.instagram.com", "instagr.am", "www.instagr.am"}

    @staticmethod
    def _mapped_error(message: str) -> MediaProcessingError:
        lowered = message.lower()
        mappings = (
            (
                (
                    "confirm you're not a bot",
                    "confirm you’re not a bot",
                    "cookies-from-browser",
                    "provide account cookies",
                    "po token",
                ),
                "cookies_required",
            ),
            (("private", "not available on this app"), "private"),
            (
                ("sign in", "log in", "logged-in", "login required", "registered users"),
                "login_required",
            ),
            (("cookies",), "cookies_required"),
            (("geo", "country", "region"), "geo_restricted"),
            (("429", "too many requests", "rate-limit"), "rate_limited"),
            (("timed out", "timeout"), "timeout"),
            (
                (
                    "file is larger",
                    "file size exceeds",
                    "filesize-max",
                    "max-filesize",
                    "maximum filesize",
                ),
                "too_large",
            ),
            (
                (
                    "unsupported url",
                    "no video formats",
                    "no downloadable media",
                    "no results",
                ),
                "unsupported",
            ),
            (("unable to download", "network", "connection", "ssl", "handshake"), "network"),
            (("unavailable", "removed", "does not exist"), "unavailable"),
        )
        for needles, code in mappings:
            if any(needle in lowered for needle in needles):
                return MediaProcessingError(code)
        return MediaProcessingError("internal", "DownloadError")

    @classmethod
    def _mapped_instagram_error(cls, message: str) -> MediaProcessingError:
        error = cls._mapped_error(message)
        if error.code == "cookies_required":
            return MediaProcessingError("login_required")
        return error

    @staticmethod
    def _is_oversized_output(message: str) -> bool:
        lowered = message.lower()
        return any(
            needle in lowered
            for needle in (
                "file is larger",
                "file size exceeds",
                "filesize-max",
                "maximum filesize",
            )
        )


def media_kind_for_path(path: Path) -> MediaKind:
    suffix = path.suffix.lower()
    if suffix in {".mp4", ".mov", ".m4v", ".webm", ".mkv"}:
        return MediaKind.VIDEO
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return MediaKind.PHOTO
    if suffix == ".gif":
        return MediaKind.ANIMATION
    return MediaKind.DOCUMENT


def platform_label(platform: Platform) -> str:
    return "YouTube" if platform == Platform.YOUTUBE else "Instagram"
