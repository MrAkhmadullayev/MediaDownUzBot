import pytest
from aiogram.types import FSInputFile

from app.config import Settings
from app.enums import MediaType, Platform
from app.services.media import DownloadedMedia, MediaInfo, MediaProcessingError
from app.tasks.media_tasks import automatic_download_selection, upload_input


def test_instagram_uses_automatic_best_video() -> None:
    info = media_info({"1080": 500_000_000, "2160": 1_500_000_000})

    assert automatic_download_selection(Platform.INSTAGRAM, info, 2_000_000_000) == (
        MediaType.VIDEO,
        "best",
    )


def test_instagram_uses_highest_quality_within_upload_limit() -> None:
    info = media_info({"1080": 500_000_000, "2160": 2_500_000_000})

    assert automatic_download_selection(Platform.INSTAGRAM, info, 2_000_000_000) == (
        MediaType.VIDEO,
        "1080",
    )


def test_instagram_rejects_media_when_every_quality_is_oversized() -> None:
    info = media_info({"1080": 2_100_000_000, "2160": 2_500_000_000})

    with pytest.raises(MediaProcessingError, match="too_large"):
        automatic_download_selection(Platform.INSTAGRAM, info, 2_000_000_000)


def test_youtube_still_requires_user_selection() -> None:
    assert automatic_download_selection(Platform.YOUTUBE, media_info({}), 2_000_000_000) is None


def test_local_api_upload_uses_shared_file_uri(tmp_path) -> None:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"video")
    downloaded = DownloadedMedia(path, "Test", 1, 5)

    assert upload_input(downloaded, Settings(TELEGRAM_LOCAL_MODE=True)) == path.resolve().as_uri()
    assert isinstance(upload_input(downloaded, Settings(TELEGRAM_LOCAL_MODE=False)), FSInputFile)


def media_info(sizes: dict[str, int | None]) -> MediaInfo:
    return MediaInfo(
        title="Test",
        duration_seconds=100_000,
        qualities=[1080, 2160],
        quality_sizes={"video": sizes, "audio": {}},
    )
