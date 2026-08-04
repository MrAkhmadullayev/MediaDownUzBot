import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.enums import (
    BroadcastStatus,
    DeliveryStatus,
    JobStatus,
    MediaType,
    Platform,
    SupportSender,
    SupportTicketStatus,
)
from app.models import Base
from app.repositories import (
    AdminRepository,
    BroadcastRepository,
    JobRepository,
    MediaCacheRepository,
    SupportRepository,
    UserRepository,
    selected_quality,
)


async def test_user_job_and_dashboard_stats() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = await UserRepository.touch(session, 42, "tester", "Test", None)
        await UserRepository.register(session, user, "encrypted", "4567")
        job = await JobRepository.create(
            session,
            uuid.uuid4(),
            user.telegram_id,
            "encrypted-url",
            Platform.YOUTUBE,
        )
        job.status = JobStatus.SUCCESS
        await AdminRepository.create_login_token(session, user.telegram_id, "a" * 64, 300)
        await AdminRepository.create_session(
            session,
            user.telegram_id,
            "b" * 64,
            "c" * 64,
            12,
        )
        await session.commit()
    async with factory() as session:
        stats = await AdminRepository.dashboard_stats(session)
        users = await AdminRepository.recent_users(session)
        counts = await AdminRepository.table_counts(session)
        user_page = await AdminRepository.table_page(session, "users", 1, 25, "tester")
    assert stats == {
        "users": 1,
        "jobs": 1,
        "success": 1,
        "errors": 0,
        "cancelled": 0,
        "active": 0,
    }
    assert users[0]["jobs"] == 1
    assert counts == {
        "users": 1,
        "download_jobs": 1,
        "media_source_cache": 0,
        "telegram_file_cache": 0,
        "admin_login_tokens": 1,
        "admin_sessions": 1,
        "support_tickets": 0,
        "support_messages": 0,
        "broadcasts": 0,
        "broadcast_deliveries": 0,
    }
    assert user_page.total == 1
    assert user_page.items[0].telegram_id == 42
    await engine.dispose()


def test_best_quality_label_is_human_readable() -> None:
    assert selected_quality(MediaType.VIDEO, "best") == "Eng yuqori mavjud sifat"


async def test_media_metadata_and_telegram_file_cache() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    source_key = "a" * 64
    async with factory() as session:
        await MediaCacheRepository.upsert_source(
            session,
            source_key,
            Platform.YOUTUBE,
            "Test video",
            120,
            [720, 1080],
            {"video": {"720": 10_000}, "audio": {"128": 2_000}},
        )
        await MediaCacheRepository.upsert_file(
            session,
            source_key,
            MediaType.VIDEO,
            "720",
            "telegram-file-id",
            "unique-id",
            "Test video",
            120,
            10_000,
        )
        await session.commit()
    async with factory() as session:
        source = await MediaCacheRepository.get_source(session, source_key, 3600)
        cached_file = await MediaCacheRepository.get_file(
            session,
            source_key,
            MediaType.VIDEO,
            "720",
        )
    assert source is not None
    assert source.available_qualities == [720, 1080]
    assert cached_file is not None
    assert cached_file.telegram_file_id == "telegram-file-id"
    await engine.dispose()


async def test_support_history_and_broadcast_recipient_snapshot() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        active_user = await UserRepository.touch(session, 101, "active", "Active", None)
        await UserRepository.register(session, active_user, "encrypted", "0101")
        inactive_user = await UserRepository.touch(session, 202, "inactive", "Inactive", None)
        await UserRepository.register(session, inactive_user, "encrypted", "0202")
        inactive_user.is_active = False

        ticket = await SupportRepository.get_or_create_open(session, active_user.telegram_id)
        user_message = await SupportRepository.add_message(
            session,
            ticket,
            SupportSender.USER,
            "Yordam kerak",
        )
        admin_message = await SupportRepository.add_message(
            session,
            ticket,
            SupportSender.ADMIN,
            "Albatta, yordam beramiz",
        )
        await SupportRepository.set_status(session, ticket, SupportTicketStatus.CLOSED)
        broadcast = await BroadcastRepository.create(session, "Yangilik", created_by=999)
        await session.commit()

        ticket_id = ticket.id
        broadcast_id = broadcast.id
        assert user_message.delivery_status == DeliveryStatus.SENT
        assert admin_message.delivery_status == DeliveryStatus.PENDING
        assert broadcast.total_count == 1

    async with factory() as session:
        history = await SupportRepository.list_owned(session, 101)
        details = await SupportRepository.get_details(session, ticket_id)
        broadcast = await BroadcastRepository.get_with_deliveries(session, broadcast_id)
        counts = await AdminRepository.table_counts(session)

    assert history.total == 1
    assert details is not None
    assert details.status == SupportTicketStatus.CLOSED
    assert [message.body for message in details.messages] == [
        "Yordam kerak",
        "Albatta, yordam beramiz",
    ]
    assert broadcast is not None
    assert broadcast.status == BroadcastStatus.PENDING
    assert [delivery.user_id for delivery in broadcast.deliveries] == [101]
    assert counts["support_tickets"] == 1
    assert counts["support_messages"] == 2
    assert counts["broadcasts"] == 1
    assert counts["broadcast_deliveries"] == 1
    await engine.dispose()
