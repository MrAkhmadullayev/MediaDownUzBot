from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.database import Database
from app.enums import BroadcastStatus, DeliveryStatus, SupportSender
from app.models import Base, Broadcast, BroadcastDelivery, SupportMessage, SupportTicket, User
from app.repositories import BroadcastRepository
from app.tasks import notification_tasks


@pytest.fixture
async def notification_database() -> Database:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield database
    await database.close()


def configure_task_runtime(
    monkeypatch: pytest.MonkeyPatch,
    database: Database,
    bot: SimpleNamespace,
) -> None:
    runtime_database = SimpleNamespace(
        session_factory=database.session_factory,
        close=AsyncMock(),
    )
    monkeypatch.setattr(notification_tasks, "Database", lambda _: runtime_database)
    monkeypatch.setattr(notification_tasks, "create_bot", lambda _: bot)


def task_bot(send_message: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(
        send_message=send_message,
        session=SimpleNamespace(close=AsyncMock()),
    )


async def create_user(database: Database, telegram_id: int, name: str) -> None:
    async with database.session_factory() as session:
        session.add(
            User(
                telegram_id=telegram_id,
                first_name=name,
                is_registered=True,
                is_active=True,
            )
        )
        await session.commit()


async def create_admin_support_message(database: Database, user_id: int) -> SupportMessage:
    async with database.session_factory() as session:
        ticket = SupportTicket(user_id=user_id)
        session.add(ticket)
        await session.flush()
        message = SupportMessage(
            ticket_id=ticket.id,
            sender=SupportSender.ADMIN,
            body="Sinov javobi",
        )
        session.add(message)
        await session.commit()
        return message


async def create_user_support_message(database: Database, user_id: int) -> SupportMessage:
    async with database.session_factory() as session:
        ticket = SupportTicket(user_id=user_id)
        session.add(ticket)
        await session.flush()
        message = SupportMessage(
            ticket_id=ticket.id,
            sender=SupportSender.USER,
            body="Yordam kerak <script>alert(1)</script>",
        )
        session.add(message)
        await session.commit()
        return message


async def test_user_support_message_notifies_admin(
    monkeypatch: pytest.MonkeyPatch,
    notification_database: Database,
) -> None:
    user_id = 701_000_000
    admin_id = 123_456_789
    await create_user(notification_database, user_id, "Ali")
    message = await create_user_support_message(notification_database, user_id)
    send_message = AsyncMock(return_value=SimpleNamespace(message_id=9122))
    bot = task_bot(send_message)
    configure_task_runtime(monkeypatch, notification_database, bot)
    monkeypatch.setattr(
        notification_tasks,
        "get_settings",
        lambda: SimpleNamespace(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            ADMIN_BASE_URL="https://admin.example.uz",
            ADMIN_TELEGRAM_IDS=[admin_id],
        ),
    )

    await notification_tasks.notify_admins(message.id)

    send_message.assert_awaited_once()
    assert send_message.await_args.args[0] == admin_id
    assert "Yangi murojaat" in send_message.await_args.args[1]
    assert "&lt;script&gt;" in send_message.await_args.args[1]
    assert "<script>" not in send_message.await_args.args[1]
    markup = send_message.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].url == (
        f"https://admin.example.uz/admin/support/{message.ticket_id}"
    )


async def test_support_reply_is_delivered_once(
    monkeypatch: pytest.MonkeyPatch,
    notification_database: Database,
) -> None:
    user_id = 701_000_001
    await create_user(notification_database, user_id, "Ali")
    message = await create_admin_support_message(notification_database, user_id)
    send_message = AsyncMock(return_value=SimpleNamespace(message_id=9123))
    bot = task_bot(send_message)
    configure_task_runtime(monkeypatch, notification_database, bot)

    await notification_tasks.deliver_support_message(message.id)
    await notification_tasks.deliver_support_message(message.id)

    send_message.assert_awaited_once()
    assert send_message.await_args.args[0] == user_id
    async with notification_database.session_factory() as session:
        delivered = await session.get(SupportMessage, message.id)
        assert delivered is not None
        assert delivered.delivery_status == DeliveryStatus.SENT
        assert delivered.telegram_message_id == 9123
        assert delivered.sent_at is not None
        assert delivered.error_detail is None


async def test_failed_support_reply_can_be_retried(
    monkeypatch: pytest.MonkeyPatch,
    notification_database: Database,
) -> None:
    user_id = 701_000_002
    await create_user(notification_database, user_id, "Vali")
    message = await create_admin_support_message(notification_database, user_id)
    send_message = AsyncMock(side_effect=RuntimeError("Telegram vaqtincha ishlamadi"))
    bot = task_bot(send_message)
    configure_task_runtime(monkeypatch, notification_database, bot)

    with pytest.raises(RuntimeError, match="Telegram vaqtincha ishlamadi"):
        await notification_tasks.deliver_support_message(message.id)

    async with notification_database.session_factory() as session:
        failed = await session.get(SupportMessage, message.id)
        assert failed is not None
        assert failed.delivery_status == DeliveryStatus.FAILED
        assert failed.error_detail == "RuntimeError"

    send_message.side_effect = None
    send_message.return_value = SimpleNamespace(message_id=9124)
    await notification_tasks.deliver_support_message(message.id)

    async with notification_database.session_factory() as session:
        delivered = await session.get(SupportMessage, message.id)
        assert delivered is not None
        assert delivered.delivery_status == DeliveryStatus.SENT
        assert delivered.telegram_message_id == 9124
        assert delivered.error_detail is None


async def test_broadcast_retries_only_failed_recipients(
    monkeypatch: pytest.MonkeyPatch,
    notification_database: Database,
) -> None:
    first_user_id = 701_000_003
    second_user_id = 701_000_004
    await create_user(notification_database, first_user_id, "Salim")
    await create_user(notification_database, second_user_id, "Karim")
    async with notification_database.session_factory() as session:
        broadcast = await BroadcastRepository.create(session, "Yangi xabar", created_by=123456789)
        await session.commit()
        broadcast_id = broadcast.id

    async def partially_failing_send(chat_id: int, *_: object, **__: object) -> SimpleNamespace:
        if chat_id == second_user_id:
            raise RuntimeError("Telegram vaqtincha ishlamadi")
        return SimpleNamespace(message_id=9201)

    send_message = AsyncMock(side_effect=partially_failing_send)
    bot = task_bot(send_message)
    configure_task_runtime(monkeypatch, notification_database, bot)
    monkeypatch.setattr(notification_tasks.asyncio, "sleep", AsyncMock())

    await notification_tasks.deliver_broadcast(broadcast_id)

    async with notification_database.session_factory() as session:
        partial = await session.get(Broadcast, broadcast_id)
        deliveries = {
            delivery.user_id: delivery
            for delivery in await session.scalars(
                select(BroadcastDelivery).where(BroadcastDelivery.broadcast_id == broadcast_id)
            )
        }
        assert partial is not None
        assert partial.status == BroadcastStatus.PARTIAL
        assert partial.sent_count == 1
        assert partial.failed_count == 1
        assert deliveries[first_user_id].status == DeliveryStatus.SENT
        assert deliveries[second_user_id].status == DeliveryStatus.FAILED

    send_message.reset_mock()
    send_message.side_effect = None
    send_message.return_value = SimpleNamespace(message_id=9202)
    await notification_tasks.deliver_broadcast(broadcast_id)

    send_message.assert_awaited_once()
    assert send_message.await_args.args[0] == second_user_id
    async with notification_database.session_factory() as session:
        completed = await session.get(Broadcast, broadcast_id)
        deliveries = list(
            await session.scalars(
                select(BroadcastDelivery).where(BroadcastDelivery.broadcast_id == broadcast_id)
            )
        )
        assert completed is not None
        assert completed.status == BroadcastStatus.COMPLETED
        assert completed.sent_count == 2
        assert completed.failed_count == 0
        assert all(delivery.status == DeliveryStatus.SENT for delivery in deliveries)
