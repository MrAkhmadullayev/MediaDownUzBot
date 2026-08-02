from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMediaGroup
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo

from app.config import Settings
from app.enums import MediaType, Platform
from app.services.media import (
    DownloadedItem,
    DownloadedMedia,
    MediaInfo,
    MediaKind,
    MediaProcessingError,
)
from app.tasks.media_tasks import (
    DownloadContext,
    automatic_download_selection,
    send_downloaded_media,
    upload_input,
)


def test_instagram_uses_automatic_best_video() -> None:
    info = media_info({"1080": 500_000_000, "2160": 1_500_000_000})

    assert automatic_download_selection(Platform.INSTAGRAM, info, 2_000_000_000) == (
        MediaType.VIDEO,
        "best",
    )


def test_instagram_without_quality_metadata_starts_original_download() -> None:
    info = MediaInfo(
        title="Instagram media",
        duration_seconds=None,
        qualities=[],
        quality_sizes={"video": {}, "audio": {}},
    )

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


async def test_instagram_carousel_is_sent_as_typed_album(tmp_path) -> None:
    photo = tmp_path / "001_1.jpg"
    video = tmp_path / "002_2.mp4"
    photo.write_bytes(b"photo")
    video.write_bytes(b"video")
    downloaded = DownloadedMedia(
        path=photo,
        title="Instagram media",
        duration_seconds=None,
        size_bytes=10,
        items=(
            DownloadedItem(photo, 5, MediaKind.PHOTO),
            DownloadedItem(video, 5, MediaKind.VIDEO),
        ),
    )
    bot = AsyncMock()
    bot.send_media_group.return_value = [object(), object()]

    messages = await send_downloaded_media(
        bot,
        Settings(TELEGRAM_LOCAL_MODE=True),
        instagram_context(),
        downloaded,
    )

    assert len(messages) == 2
    album = bot.send_media_group.await_args.kwargs["media"]
    assert isinstance(album[0], InputMediaPhoto)
    assert isinstance(album[1], InputMediaVideo)
    assert album[0].caption is not None
    assert album[1].caption is None


async def test_single_instagram_photo_is_sent_as_photo(tmp_path) -> None:
    photo = tmp_path / "001_1.jpg"
    photo.write_bytes(b"photo")
    downloaded = DownloadedMedia(
        path=photo,
        title="Instagram media",
        duration_seconds=None,
        size_bytes=5,
        items=(DownloadedItem(photo, 5, MediaKind.PHOTO),),
    )
    bot = AsyncMock()
    bot.send_photo.return_value = object()

    await send_downloaded_media(
        bot,
        Settings(TELEGRAM_LOCAL_MODE=True),
        instagram_context(),
        downloaded,
    )

    bot.send_photo.assert_awaited_once()
    bot.send_video.assert_not_awaited()


async def test_rejected_instagram_album_falls_back_to_individual_media(tmp_path) -> None:
    photo = tmp_path / "001_1.jpg"
    video = tmp_path / "002_2.mp4"
    photo.write_bytes(b"photo")
    video.write_bytes(b"video")
    downloaded = DownloadedMedia(
        path=photo,
        title="Instagram media",
        duration_seconds=None,
        size_bytes=10,
        items=(
            DownloadedItem(photo, 5, MediaKind.PHOTO),
            DownloadedItem(video, 5, MediaKind.VIDEO),
        ),
    )
    bot = AsyncMock()
    bot.send_media_group.side_effect = TelegramBadRequest(
        SendMediaGroup(chat_id=1, media=[]),
        "media group rejected",
    )
    bot.send_photo.return_value = object()
    bot.send_video.return_value = object()

    messages = await send_downloaded_media(
        bot,
        Settings(TELEGRAM_LOCAL_MODE=True),
        instagram_context(),
        downloaded,
    )

    assert len(messages) == 2
    bot.send_photo.assert_awaited_once()
    bot.send_video.assert_awaited_once()


def instagram_context() -> DownloadContext:
    return DownloadContext(
        user_id=1,
        status_message_id=2,
        media_type=MediaType.VIDEO,
        quality="best",
        platform=Platform.INSTAGRAM,
        url="https://www.instagram.com/p/DOdWFmdCoKQ/",
        source_key="source-key",
    )


def media_info(sizes: dict[str, int | None]) -> MediaInfo:
    return MediaInfo(
        title="Test",
        duration_seconds=100_000,
        qualities=[1080, 2160],
        quality_sizes={"video": sizes, "audio": {}},
    )
