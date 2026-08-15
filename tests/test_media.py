import subprocess
import uuid
from pathlib import Path

import pytest
import yt_dlp

from app.config import Settings
from app.enums import MediaType
from app.services.media import MediaKind, MediaProcessingError, MediaService


def test_base_options_keep_certificate_verification_enabled(tmp_path) -> None:
    service = MediaService(Settings(VIDEOS_DIR=tmp_path))

    options = service._base_options()

    assert "nocheckcertificate" not in options
    assert "legacyserverconnect" not in options


def test_base_options_enable_pot_provider_and_optional_proxy(tmp_path) -> None:
    service = MediaService(
        Settings(
            VIDEOS_DIR=tmp_path,
            YTDLP_POT_PROVIDER_URL="http://pot-provider:4416/",
            YTDLP_PROXY_URL="socks5h://proxy.example:1080",
        )
    )

    options = service._base_options(proxy_url="socks5h://proxy.example:1080")

    assert options["extractor_args"] == {
        "youtubepot-bgutilhttp": {"base_url": ["http://pot-provider:4416"]}
    }
    assert options["proxy"] == "socks5h://proxy.example:1080"


def test_shared_highlight_selects_only_requested_story(tmp_path) -> None:
    service = MediaService(Settings(VIDEOS_DIR=tmp_path))
    url = (
        "https://www.instagram.com/stories/highlights/18013254650887296/"
        "?story_media_id=3912338590873067115"
    )

    options = service._base_options(url)
    match_filter = options["match_filter"]

    assert "playlist_items" not in options
    assert match_filter({"id": "DZLazhOCp5r"}, incomplete=True) is None
    assert match_filter({"id": "DZNvrjMiiPY"}, incomplete=True) is not None
    assert match_filter({"playlist_id": "18013254650887296"}, incomplete=True) is None


def test_ssl_errors_are_mapped_to_network() -> None:
    error = MediaService._mapped_error("SSL handshake failure")

    assert error.code == "network"


def test_youtube_bot_verification_is_mapped_to_cookie_requirement() -> None:
    error = MediaService._mapped_error(
        "Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies"
    )

    assert error.code == "cookies_required"


def test_actual_login_requirement_stays_separate() -> None:
    error = MediaService._mapped_error("This video is only available to registered users")

    assert error.code == "login_required"


def test_configured_cookie_file_must_exist(tmp_path) -> None:
    service = MediaService(
        Settings(VIDEOS_DIR=tmp_path, YTDLP_COOKIES_FILE=tmp_path / "missing-cookies.txt")
    )

    with pytest.raises(MediaProcessingError) as caught, service._prepared_options():
        pass

    assert caught.value.code == "cookies_required"


def test_configured_cookie_file_uses_a_private_writable_copy(tmp_path) -> None:
    cookie_file = tmp_path / "youtube-cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    cookie_file.chmod(0o400)
    service = MediaService(Settings(VIDEOS_DIR=tmp_path, YTDLP_COOKIES_FILE=cookie_file))

    with service._prepared_options() as options:
        prepared_cookie = options["cookiefile"]
        assert prepared_cookie != str(cookie_file)
        assert Path(prepared_cookie).read_text() == "# Netscape HTTP Cookie File\n"
        assert Path(prepared_cookie).stat().st_mode & 0o777 == 0o600
        with yt_dlp.YoutubeDL(options):
            pass

    assert not Path(prepared_cookie).exists()
    assert cookie_file.read_text() == "# Netscape HTTP Cookie File\n"


def test_youtube_probe_tries_public_access_before_cookie_fallback(tmp_path, monkeypatch) -> None:
    cookie_file = tmp_path / "youtube-cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    attempts: list[bool] = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def extract_info(self, url, *, download):
            attempts.append("cookiefile" in self.options)
            if len(attempts) == 1:
                raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")
            assert Path(self.options["cookiefile"]).is_file()
            return {"title": "Sinov", "formats": [{"height": 720, "vcodec": "avc1"}]}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    service = MediaService(Settings(VIDEOS_DIR=tmp_path, YTDLP_COOKIES_FILE=cookie_file))

    info = service.probe("https://youtu.be/4uDX2GD8ckg")

    assert info.title == "Sinov"
    assert attempts == [False, True]


def test_youtube_probe_uses_proxy_after_direct_access_fails(tmp_path, monkeypatch) -> None:
    attempts: list[str | None] = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def extract_info(self, url, *, download):
            attempts.append(self.options.get("proxy"))
            if "proxy" not in self.options:
                raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")
            return {"title": "Proxy orqali", "formats": []}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    service = MediaService(
        Settings(
            VIDEOS_DIR=tmp_path,
            YTDLP_PROXY_URL="https://user:password@proxy.example:443",
        )
    )

    info = service.probe("https://youtu.be/4uDX2GD8ckg")

    assert info.title == "Proxy orqali"
    assert attempts == [None, "https://user:password@proxy.example:443"]


def test_public_youtube_probe_ignores_unneeded_stale_cookie(tmp_path, monkeypatch) -> None:
    class FakeYoutubeDL:
        def __init__(self, options):
            assert "cookiefile" not in options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def extract_info(self, url, *, download):
            return {"title": "Ochiq video", "formats": []}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    service = MediaService(
        Settings(
            VIDEOS_DIR=tmp_path,
            YTDLP_COOKIES_FILE=tmp_path / "expired-or-missing.txt",
        )
    )

    info = service.probe("https://youtu.be/4uDX2GD8ckg")

    assert info.title == "Ochiq video"


def test_instagram_cookie_file_uses_a_private_copy(tmp_path) -> None:
    cookie_file = tmp_path / "instagram-cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    cookie_file.chmod(0o400)
    service = MediaService(Settings(VIDEOS_DIR=tmp_path, INSTAGRAM_COOKIES_FILE=cookie_file))

    with service._prepared_instagram_cookie() as prepared_cookie:
        assert prepared_cookie is not None
        assert prepared_cookie != cookie_file
        assert prepared_cookie.read_text() == "# Netscape HTTP Cookie File\n"
        assert prepared_cookie.stat().st_mode & 0o777 == 0o600

    assert not prepared_cookie.exists()
    assert cookie_file.read_text() == "# Netscape HTTP Cookie File\n"


def test_missing_instagram_cookie_is_reported_as_login_required(tmp_path) -> None:
    service = MediaService(
        Settings(VIDEOS_DIR=tmp_path, INSTAGRAM_COOKIES_FILE=tmp_path / "missing.txt")
    )

    with pytest.raises(MediaProcessingError) as caught, service._prepared_instagram_cookie():
        pass

    assert caught.value.code == "login_required"


def test_instagram_probe_does_not_require_video_metadata(tmp_path, monkeypatch) -> None:
    def fail_youtube_dl(*args, **kwargs):
        raise AssertionError("Instagram probe yt-dlp ishlatmasligi kerak")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", fail_youtube_dl)
    service = MediaService(Settings(VIDEOS_DIR=tmp_path))

    info = service.probe("https://www.instagram.com/p/DOdWFmdCoKQ/")

    assert info.title == "Instagram media"
    assert info.qualities == []
    assert info.duration_seconds is None


def test_instagram_download_returns_all_carousel_items(tmp_path, monkeypatch) -> None:
    service = MediaService(Settings(VIDEOS_DIR=tmp_path))

    def fake_run(command, **kwargs):
        destination = Path(command[command.index("-D") + 1])
        (destination / "001_1.jpg").write_bytes(b"photo")
        (destination / "002_2.mp4").write_bytes(b"video")
        (destination / "003_3.gif").write_bytes(b"animation")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = service.download(
        "https://www.instagram.com/p/DOdWFmdCoKQ/",
        uuid.uuid4(),
        MediaType.VIDEO,
        "best",
    )

    assert [item.path.name for item in result.items] == [
        "001_1.jpg",
        "002_2.mp4",
        "003_3.gif",
    ]
    assert [item.kind for item in result.items] == [
        MediaKind.PHOTO,
        MediaKind.VIDEO,
        MediaKind.ANIMATION,
    ]
    assert result.size_bytes == len(b"photo") + len(b"video") + len(b"animation")


def test_instagram_download_uses_cookie_and_safe_argument_list(tmp_path, monkeypatch) -> None:
    cookie_file = tmp_path / "instagram-cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    service = MediaService(Settings(VIDEOS_DIR=tmp_path, INSTAGRAM_COOKIES_FILE=cookie_file))
    captured: list[list[str]] = []

    def fake_run(command, **kwargs):
        captured.append(command)
        if len(captured) == 1:
            return subprocess.CompletedProcess(
                command,
                1,
                "",
                "AuthenticationError: login required",
            )
        destination = Path(command[command.index("-D") + 1])
        (destination / "001_1.jpg").write_bytes(b"photo")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    service.download(
        "https://www.instagram.com/p/DOdWFmdCoKQ/",
        uuid.uuid4(),
        MediaType.VIDEO,
        "best",
    )

    assert captured[0][1:3] == ["-m", "gallery_dl"]
    assert "-C" not in captured[0]
    assert "-C" in captured[1]
    assert captured[1][-1] == "https://www.instagram.com/p/DOdWFmdCoKQ/"
    assert not Path(captured[1][captured[1].index("-C") + 1]).exists()


def test_instagram_download_uses_proxy_after_rate_limit(tmp_path, monkeypatch) -> None:
    service = MediaService(
        Settings(
            VIDEOS_DIR=tmp_path,
            INSTAGRAM_PROXY_URL="socks5h://user:password@proxy.example:1080",
        )
    )
    captured: list[list[str]] = []

    def fake_run(command, **kwargs):
        captured.append(command)
        if "--proxy" not in command:
            return subprocess.CompletedProcess(command, 1, "", "HttpError: '403 Forbidden'")
        destination = Path(command[command.index("-D") + 1])
        (destination / "001_1.jpg").write_bytes(b"photo")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = service.download(
        "https://www.instagram.com/p/DOdWFmdCoKQ/",
        uuid.uuid4(),
        MediaType.VIDEO,
        "best",
    )

    assert result.items[0].kind == MediaKind.PHOTO
    assert "--proxy" not in captured[0]
    assert captured[1][captured[1].index("--proxy") + 1] == (
        "socks5h://user:password@proxy.example:1080"
    )


def test_instagram_reel_falls_back_to_ytdlp_after_login_redirect(tmp_path, monkeypatch) -> None:
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def extract_info(self, url, *, download):
            destination = Path(self.options["paths"]["home"])
            (destination / "instagram.mp4").write_bytes(b"video")
            return {"title": "Instagram video", "duration": 12}

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            4,
            "",
            "AbortExtraction: HTTP redirect to login page "
            "(https://www.instagram.com/accounts/login/)",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    service = MediaService(Settings(VIDEOS_DIR=tmp_path))

    result = service.download(
        "https://www.instagram.com/reel/DcB15I6Mz2R/",
        uuid.uuid4(),
        MediaType.VIDEO,
        "best",
    )

    assert result.path.name == "instagram.mp4"
    assert result.title == "Instagram video"
    assert result.duration_seconds == 12
    assert result.media_items[0].kind == MediaKind.VIDEO


def test_instagram_cookie_error_is_not_reported_as_youtube_verification() -> None:
    error = MediaService._mapped_instagram_error("Cookies are required to log in")

    assert error.code == "login_required"


def test_instagram_login_redirect_is_mapped_to_login_requirement() -> None:
    error = MediaService._mapped_instagram_error(
        "HTTP redirect to login page (https://www.instagram.com/accounts/login/)"
    )

    assert error.code == "login_required"


def test_unknown_instagram_error_is_safe_and_actionable() -> None:
    error = MediaService._mapped_instagram_error(
        "ExtractorError: failed for https://instagram.com/p/secret/?token=sensitive"
    )

    assert error.code == "source_error"
    assert error.detail == "gallery-dl:ExtractorError"
    assert "instagram.com" not in error.detail


def test_instagram_oversized_download_is_reported_from_extractor_output(
    tmp_path, monkeypatch
) -> None:
    service = MediaService(Settings(VIDEOS_DIR=tmp_path))

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            "",
            "Skipping 001_1.mp4 (File size exceeds --filesize-max)",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(MediaProcessingError) as caught:
        service.download(
            "https://www.instagram.com/p/DOdWFmdCoKQ/",
            uuid.uuid4(),
            MediaType.VIDEO,
            "best",
        )

    assert caught.value.code == "too_large"


def test_quality_extraction_and_limit(tmp_path) -> None:
    settings = Settings(VIDEOS_DIR=tmp_path, MAX_VIDEO_HEIGHT=1080)
    service = MediaService(settings)
    info = {
        "formats": [
            {"height": 360, "vcodec": "avc1"},
            {"height": 720, "vcodec": "avc1"},
            {"height": 1080, "vcodec": "av01"},
            {"height": 2160, "vcodec": "av01"},
            {"height": None, "vcodec": "none"},
        ]
    }
    assert service._qualities(info) == [360, 720, 1080]


def test_best_quality_uses_configured_height_limit(tmp_path) -> None:
    service = MediaService(Settings(VIDEOS_DIR=tmp_path, MAX_VIDEO_HEIGHT=2160))

    options = service._video_options("best")

    assert "height<=2160" in options["format"]


def test_quality_size_estimates_match_selected_streams(tmp_path) -> None:
    service = MediaService(Settings(VIDEOS_DIR=tmp_path))
    info = {
        "formats": [
            {
                "height": 720,
                "vcodec": "avc1.64001f",
                "acodec": "none",
                "ext": "mp4",
                "filesize": 20_000_000,
                "fps": 30,
            },
            {
                "height": 1080,
                "vcodec": "avc1.640028",
                "acodec": "none",
                "ext": "mp4",
                "filesize_approx": 40_000_000,
                "fps": 30,
            },
            {
                "height": None,
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "ext": "m4a",
                "filesize": 10_000_000,
                "abr": 128,
            },
        ]
    }

    sizes = service._quality_sizes(info, [720, 1080], duration=100)

    assert sizes["video"]["720"] == 30_300_000
    assert sizes["video"]["1080"] == 50_500_000
    assert sizes["audio"]["128"] == 1_616_000
    assert sizes["audio"]["192"] == 2_424_000
    assert sizes["audio"]["m4a"] == 10_100_000


def test_quality_size_estimate_uses_bitrate_when_size_is_missing(tmp_path) -> None:
    service = MediaService(Settings(VIDEOS_DIR=tmp_path))
    item = {"tbr": 800}

    assert service._format_size(item, duration=60) == 6_000_000
    assert service._format_size(item, duration=None) is None


def test_cleanup_only_removes_job_directory(tmp_path) -> None:
    settings = Settings(VIDEOS_DIR=tmp_path)
    service = MediaService(settings)
    job_id = uuid.uuid4()
    job_dir = tmp_path / str(job_id)
    job_dir.mkdir()
    (job_dir / "media.mp4").write_bytes(b"video")
    preserved = tmp_path / "preserved"
    preserved.mkdir()
    service.cleanup(job_id)
    assert not job_dir.exists()
    assert preserved.exists()
