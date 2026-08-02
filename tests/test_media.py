import uuid

import pytest

from app.config import Settings
from app.services.media import MediaProcessingError, MediaService


def test_base_options_keep_certificate_verification_enabled(tmp_path) -> None:
    service = MediaService(Settings(VIDEOS_DIR=tmp_path))

    options = service._base_options()

    assert "nocheckcertificate" not in options
    assert "legacyserverconnect" not in options


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

    with pytest.raises(MediaProcessingError) as caught:
        service._base_options()

    assert caught.value.code == "cookies_required"


def test_configured_cookie_file_is_passed_to_ytdlp(tmp_path) -> None:
    cookie_file = tmp_path / "youtube-cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    service = MediaService(Settings(VIDEOS_DIR=tmp_path, YTDLP_COOKIES_FILE=cookie_file))

    options = service._base_options()

    assert options["cookiefile"] == str(cookie_file)


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
