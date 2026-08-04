import uuid

from app.bot.keyboards import (
    audio_quality_keyboard,
    main_keyboard,
    support_menu_keyboard,
    video_quality_keyboard,
)


def test_main_keyboard_exposes_help_and_support() -> None:
    markup = main_keyboard(is_admin=False)

    assert [button.text for button in markup.keyboard[0]] == [
        "ℹ️ Yordam",
        "💬 Qo‘llab-quvvatlash",
    ]


def test_support_menu_contains_new_request_and_history() -> None:
    markup = support_menu_keyboard()

    assert markup.inline_keyboard[0][0].callback_data == "support:new"
    assert markup.inline_keyboard[1][0].callback_data == "support:history"


def test_video_quality_keyboard_includes_estimated_size() -> None:
    markup = video_quality_keyboard(uuid.uuid4(), [720], {"720": 37_859_797}, 2_000_000_000)

    assert markup.inline_keyboard[0][0].text == "720p · ≈ 36.1 MB"


def test_oversized_video_quality_is_blocked() -> None:
    markup = video_quality_keyboard(uuid.uuid4(), [2160], {"2160": 2_100_000_000}, 2_000_000_000)

    button = markup.inline_keyboard[0][0]

    assert button.text == "🚫 2160p · ≈ 1.96 GB · hajm katta"
    assert button.callback_data == "oversize"


def test_audio_quality_keyboard_includes_estimated_sizes() -> None:
    markup = audio_quality_keyboard(
        uuid.uuid4(),
        {"128": 16_000_000, "192": 24_000_000, "m4a": None},
        2_000_000_000,
    )

    assert markup.inline_keyboard[0][0].text == "MP3 · 128 kbps · ≈ 15.3 MB"
    assert markup.inline_keyboard[1][0].text == "MP3 · 192 kbps · ≈ 22.9 MB"
    assert markup.inline_keyboard[2][0].text == "M4A · yuqori sifat · hajm noma’lum"
