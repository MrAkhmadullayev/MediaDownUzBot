import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.admin.presentation import MODULES, module_by_key, present_table
from app.enums import JobStatus, MediaType, Platform
from app.models import (
    AdminLoginToken,
    AdminSession,
    DownloadJob,
    MediaSourceCache,
    TelegramFileCache,
    User,
)


@pytest.fixture
def table_records() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "users": User(
            telegram_id=1001,
            username="admin",
            first_name="Admin",
            phone_encrypted="encrypted-phone",
            phone_last4="1234",
            is_registered=True,
            is_active=True,
            created_at=now,
            registered_at=now,
            last_seen_at=now,
        ),
        "download_jobs": DownloadJob(
            id=uuid.uuid4(),
            user_id=1001,
            source_url_encrypted="encrypted-url",
            platform=Platform.YOUTUBE,
            status=JobStatus.SUCCESS,
            media_type=MediaType.VIDEO,
            quality="1080p",
            title="Test video",
            duration_seconds=125,
            available_qualities=[720, 1080],
            available_quality_sizes={"1080": {"video": 1024}},
            file_size_bytes=1024,
            created_at=now,
            started_at=now,
            completed_at=now,
        ),
        "media_source_cache": MediaSourceCache(
            source_key="source-key",
            platform=Platform.INSTAGRAM,
            title="Test reel",
            duration_seconds=30,
            available_qualities=[1080],
            available_quality_sizes={"1080": {"video": 2048}},
            updated_at=now,
        ),
        "telegram_file_cache": TelegramFileCache(
            source_key="source-key",
            media_type=MediaType.VIDEO,
            quality="1080p",
            telegram_file_id="secret-file-id",
            telegram_file_unique_id="safe-unique-id",
            title="Cached video",
            duration_seconds=30,
            file_size_bytes=2048,
            created_at=now,
            last_used_at=now,
        ),
        "admin_login_tokens": AdminLoginToken(
            id=uuid.uuid4(),
            telegram_id=1001,
            token_hash="secret-login-hash",
            expires_at=now + timedelta(minutes=5),
            created_at=now,
        ),
        "admin_sessions": AdminSession(
            id=uuid.uuid4(),
            telegram_id=1001,
            token_hash="secret-session-hash",
            csrf_hash="secret-csrf-hash",
            expires_at=now + timedelta(hours=1),
            last_seen_at=now,
            created_at=now,
        ),
    }


def test_all_database_modules_have_safe_table_presentations(
    table_records: dict[str, object],
) -> None:
    assert {module["key"] for module in MODULES} == set(table_records)

    rendered = []
    for view, record in table_records.items():
        columns, rows = present_table(view, [record])
        assert module_by_key(view)["label"]
        assert len(rows) == 1
        assert len(rows[0]) == len(columns)
        rendered.extend(cell["value"] for cell in rows[0])

    output = " ".join(rendered)
    assert "Himoyalangan" in output
    assert "secret-file-id" not in output
    assert "secret-login-hash" not in output
    assert "secret-session-hash" not in output
    assert "secret-csrf-hash" not in output
    assert "encrypted-phone" not in output
    assert "encrypted-url" not in output
