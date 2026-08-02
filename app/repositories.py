import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import String, case, cast, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import TERMINAL_JOB_STATUSES, JobStatus, MediaType, Platform
from app.models import (
    AdminLoginToken,
    AdminSession,
    DownloadJob,
    MediaSourceCache,
    TelegramFileCache,
    User,
)


class UserRepository:
    @staticmethod
    async def get(session: AsyncSession, telegram_id: int) -> User | None:
        return await session.get(User, telegram_id)

    @staticmethod
    async def touch(
        session: AsyncSession,
        telegram_id: int,
        username: str | None,
        first_name: str,
        last_name: str | None,
    ) -> User:
        user = await session.get(User, telegram_id)
        now = datetime.now(UTC)
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name[:128],
                last_name=(last_name or "")[:128] or None,
                last_seen_at=now,
            )
            session.add(user)
        else:
            user.username = username
            user.first_name = first_name[:128]
            user.last_name = (last_name or "")[:128] or None
            user.last_seen_at = now
        await session.flush()
        return user

    @staticmethod
    async def register(
        session: AsyncSession,
        user: User,
        encrypted_phone: str,
        phone_last4: str,
    ) -> None:
        user.phone_encrypted = encrypted_phone
        user.phone_last4 = phone_last4
        user.is_registered = True
        user.registered_at = user.registered_at or datetime.now(UTC)
        await session.flush()


class JobRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        job_id: uuid.UUID,
        user_id: int,
        source_url_encrypted: str,
        platform: Platform,
    ) -> DownloadJob:
        job = DownloadJob(
            id=job_id,
            user_id=user_id,
            source_url_encrypted=source_url_encrypted,
            platform=platform,
        )
        session.add(job)
        await session.flush()
        return job

    @staticmethod
    async def get_owned(
        session: AsyncSession,
        job_id: uuid.UUID,
        user_id: int,
        lock: bool = False,
    ) -> DownloadJob | None:
        query = select(DownloadJob).where(
            DownloadJob.id == job_id,
            DownloadJob.user_id == user_id,
        )
        if lock:
            query = query.with_for_update()
        return await session.scalar(query)

    @staticmethod
    async def transition(
        session: AsyncSession,
        job_id: uuid.UUID,
        from_statuses: set[JobStatus],
        to_status: JobStatus,
        **values: object,
    ) -> bool:
        result = await session.execute(
            update(DownloadJob)
            .where(DownloadJob.id == job_id, DownloadJob.status.in_(from_statuses))
            .values(status=to_status, **values)
        )
        return bool(result.rowcount)

    @staticmethod
    async def finish_error(
        session: AsyncSession,
        job: DownloadJob,
        code: str,
        detail: str | None = None,
    ) -> None:
        job.status = JobStatus.ERROR
        job.error_code = code[:64]
        job.error_detail = detail[:1000] if detail else None
        job.source_url_encrypted = None
        job.completed_at = datetime.now(UTC)
        await session.flush()

    @staticmethod
    async def cancel(session: AsyncSession, job: DownloadJob) -> None:
        job.status = JobStatus.CANCELLED
        job.source_url_encrypted = None
        job.completed_at = datetime.now(UTC)
        await session.flush()


class MediaCacheRepository:
    @staticmethod
    async def get_source(
        session: AsyncSession,
        source_key: str,
        ttl_seconds: int,
    ) -> MediaSourceCache | None:
        cutoff = datetime.now(UTC) - timedelta(seconds=ttl_seconds)
        return await session.scalar(
            select(MediaSourceCache).where(
                MediaSourceCache.source_key == source_key,
                MediaSourceCache.updated_at >= cutoff,
            )
        )

    @staticmethod
    async def upsert_source(
        session: AsyncSession,
        source_key: str,
        platform: Platform,
        title: str,
        duration_seconds: int | None,
        available_qualities: list[int],
        available_quality_sizes: dict[str, dict[str, int | None]],
    ) -> None:
        now = datetime.now(UTC)
        values = {
            "source_key": source_key,
            "platform": platform,
            "title": title[:500],
            "duration_seconds": duration_seconds,
            "available_qualities": available_qualities,
            "available_quality_sizes": available_quality_sizes,
            "updated_at": now,
        }
        await MediaCacheRepository._upsert(
            session,
            MediaSourceCache,
            values,
            ["source_key"],
        )

    @staticmethod
    async def get_file(
        session: AsyncSession,
        source_key: str,
        media_type: MediaType,
        quality: str,
    ) -> TelegramFileCache | None:
        return await session.get(TelegramFileCache, (source_key, media_type, quality))

    @staticmethod
    async def upsert_file(
        session: AsyncSession,
        source_key: str,
        media_type: MediaType,
        quality: str,
        telegram_file_id: str,
        telegram_file_unique_id: str | None,
        title: str,
        duration_seconds: int | None,
        file_size_bytes: int | None,
    ) -> None:
        now = datetime.now(UTC)
        values = {
            "source_key": source_key,
            "media_type": media_type,
            "quality": quality,
            "telegram_file_id": telegram_file_id,
            "telegram_file_unique_id": telegram_file_unique_id,
            "title": title[:500],
            "duration_seconds": duration_seconds,
            "file_size_bytes": file_size_bytes,
            "created_at": now,
            "last_used_at": now,
        }
        await MediaCacheRepository._upsert(
            session,
            TelegramFileCache,
            values,
            ["source_key", "media_type", "quality"],
            preserve_created_at=True,
        )

    @staticmethod
    async def touch_file(
        session: AsyncSession,
        source_key: str,
        media_type: MediaType,
        quality: str,
    ) -> None:
        await session.execute(
            update(TelegramFileCache)
            .where(
                TelegramFileCache.source_key == source_key,
                TelegramFileCache.media_type == media_type,
                TelegramFileCache.quality == quality,
            )
            .values(last_used_at=datetime.now(UTC))
        )

    @staticmethod
    async def delete_file(
        session: AsyncSession,
        source_key: str,
        media_type: MediaType,
        quality: str,
    ) -> None:
        await session.execute(
            delete(TelegramFileCache).where(
                TelegramFileCache.source_key == source_key,
                TelegramFileCache.media_type == media_type,
                TelegramFileCache.quality == quality,
            )
        )

    @staticmethod
    async def _upsert(
        session: AsyncSession,
        model: type[MediaSourceCache] | type[TelegramFileCache],
        values: dict[str, object],
        conflict_columns: list[str],
        preserve_created_at: bool = False,
    ) -> None:
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "postgresql":
            statement = postgresql_insert(model).values(**values)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(model).values(**values)
        else:
            raise RuntimeError(f"Qo‘llab-quvvatlanmagan ma’lumotlar bazasi: {dialect_name}")
        updates = dict(values)
        for column in conflict_columns:
            updates.pop(column, None)
        if preserve_created_at:
            updates.pop("created_at", None)
        statement = statement.on_conflict_do_update(
            index_elements=conflict_columns,
            set_=updates,
        )
        await session.execute(statement)


class AdminRepository:
    @staticmethod
    async def create_login_token(
        session: AsyncSession,
        telegram_id: int,
        hashed_token: str,
        ttl_seconds: int,
    ) -> AdminLoginToken:
        now = datetime.now(UTC)
        await session.execute(
            update(AdminLoginToken)
            .where(
                AdminLoginToken.telegram_id == telegram_id,
                AdminLoginToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        token = AdminLoginToken(
            telegram_id=telegram_id,
            token_hash=hashed_token,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        session.add(token)
        await session.flush()
        return token

    @staticmethod
    async def consume_login_token(
        session: AsyncSession,
        hashed_token: str,
        allowed_admins: list[int],
    ) -> AdminLoginToken | None:
        now = datetime.now(UTC)
        token = await session.scalar(
            select(AdminLoginToken)
            .where(
                AdminLoginToken.token_hash == hashed_token,
                AdminLoginToken.used_at.is_(None),
                AdminLoginToken.expires_at > now,
                AdminLoginToken.telegram_id.in_(allowed_admins),
            )
            .with_for_update()
        )
        if token:
            token.used_at = now
            await session.flush()
        return token

    @staticmethod
    async def create_session(
        session: AsyncSession,
        telegram_id: int,
        hashed_token: str,
        csrf_hash: str,
        ttl_hours: int,
    ) -> AdminSession:
        now = datetime.now(UTC)
        admin_session = AdminSession(
            telegram_id=telegram_id,
            token_hash=hashed_token,
            csrf_hash=csrf_hash,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        session.add(admin_session)
        await session.flush()
        return admin_session

    @staticmethod
    async def get_session(
        session: AsyncSession,
        hashed_token: str,
        allowed_admins: list[int],
    ) -> AdminSession | None:
        now = datetime.now(UTC)
        admin_session = await session.scalar(
            select(AdminSession).where(
                AdminSession.token_hash == hashed_token,
                AdminSession.expires_at > now,
                AdminSession.telegram_id.in_(allowed_admins),
            )
        )
        if admin_session:
            admin_session.last_seen_at = now
            await session.flush()
        return admin_session

    @staticmethod
    async def dashboard_stats(session: AsyncSession) -> dict[str, int]:
        user_count = await session.scalar(
            select(func.count()).select_from(User).where(User.is_registered.is_(True))
        )
        job_counts = (
            await session.execute(
                select(
                    func.count(DownloadJob.id),
                    func.sum(case((DownloadJob.status == JobStatus.SUCCESS, 1), else_=0)),
                    func.sum(case((DownloadJob.status == JobStatus.ERROR, 1), else_=0)),
                    func.sum(case((DownloadJob.status == JobStatus.CANCELLED, 1), else_=0)),
                    func.sum(case((~DownloadJob.status.in_(TERMINAL_JOB_STATUSES), 1), else_=0)),
                )
            )
        ).one()
        return {
            "users": int(user_count or 0),
            "jobs": int(job_counts[0] or 0),
            "success": int(job_counts[1] or 0),
            "errors": int(job_counts[2] or 0),
            "cancelled": int(job_counts[3] or 0),
            "active": int(job_counts[4] or 0),
        }

    @staticmethod
    async def recent_users(session: AsyncSession, limit: int = 100) -> list[dict[str, object]]:
        result = await session.execute(
            select(
                User.telegram_id,
                User.first_name,
                User.last_name,
                User.username,
                User.phone_last4,
                User.registered_at,
                func.count(DownloadJob.id).label("jobs"),
                func.sum(case((DownloadJob.status == JobStatus.SUCCESS, 1), else_=0)).label(
                    "success"
                ),
                func.sum(case((DownloadJob.status == JobStatus.ERROR, 1), else_=0)).label("errors"),
            )
            .outerjoin(DownloadJob, DownloadJob.user_id == User.telegram_id)
            .where(User.is_registered.is_(True))
            .group_by(User.telegram_id)
            .order_by(User.registered_at.desc())
            .limit(limit)
        )
        return [dict(row._mapping) for row in result]

    @staticmethod
    async def recent_jobs(session: AsyncSession, limit: int = 100) -> list[DownloadJob]:
        result = await session.scalars(
            select(DownloadJob).order_by(DownloadJob.created_at.desc()).limit(limit)
        )
        return list(result)

    @staticmethod
    async def table_counts(session: AsyncSession) -> dict[str, int]:
        row = (
            await session.execute(
                select(
                    select(func.count()).select_from(User).scalar_subquery(),
                    select(func.count()).select_from(DownloadJob).scalar_subquery(),
                    select(func.count()).select_from(MediaSourceCache).scalar_subquery(),
                    select(func.count()).select_from(TelegramFileCache).scalar_subquery(),
                    select(func.count()).select_from(AdminLoginToken).scalar_subquery(),
                    select(func.count()).select_from(AdminSession).scalar_subquery(),
                )
            )
        ).one()
        keys = (
            "users",
            "download_jobs",
            "media_source_cache",
            "telegram_file_cache",
            "admin_login_tokens",
            "admin_sessions",
        )
        return {key: int(value or 0) for key, value in zip(keys, row, strict=True)}

    @staticmethod
    async def table_page(
        session: AsyncSession,
        view: str,
        page: int,
        page_size: int,
        query: str = "",
        status_filter: str = "",
        platform_filter: str = "",
    ) -> "AdminPage":
        model, statement, criteria, order_by = AdminRepository._table_query(
            view,
            query,
            status_filter,
            platform_filter,
        )
        filtered = statement.where(*criteria)
        total = int(
            await session.scalar(
                select(func.count()).select_from(filtered.order_by(None).subquery())
            )
            or 0
        )
        pages = max(1, (total + page_size - 1) // page_size)
        current_page = min(page, pages)
        result = await session.scalars(
            filtered.order_by(order_by).offset((current_page - 1) * page_size).limit(page_size)
        )
        return AdminPage(
            items=list(result),
            total=total,
            page=current_page,
            page_size=page_size,
            pages=pages,
            model=model,
        )

    @staticmethod
    def _table_query(
        view: str,
        query: str,
        status_filter: str,
        platform_filter: str,
    ) -> tuple[type[Any], Any, list[Any], Any]:
        criteria: list[Any] = []
        if view == "users":
            model = User
            if query:
                criteria.append(
                    or_(
                        cast(User.telegram_id, String).contains(query, autoescape=True),
                        User.username.contains(query, autoescape=True),
                        User.first_name.contains(query, autoescape=True),
                        User.last_name.contains(query, autoescape=True),
                        User.phone_last4.contains(query, autoescape=True),
                    )
                )
            return model, select(model), criteria, User.created_at.desc()
        if view == "download_jobs":
            model = DownloadJob
            if query:
                criteria.append(
                    or_(
                        cast(DownloadJob.id, String).contains(query, autoescape=True),
                        cast(DownloadJob.user_id, String).contains(query, autoescape=True),
                        DownloadJob.title.contains(query, autoescape=True),
                        DownloadJob.error_code.contains(query, autoescape=True),
                        DownloadJob.error_detail.contains(query, autoescape=True),
                    )
                )
            if status_filter:
                criteria.append(DownloadJob.status == status_filter)
            if platform_filter:
                criteria.append(DownloadJob.platform == platform_filter)
            return model, select(model), criteria, DownloadJob.created_at.desc()
        if view == "media_source_cache":
            model = MediaSourceCache
            if query:
                criteria.append(
                    or_(
                        MediaSourceCache.source_key.contains(query, autoescape=True),
                        MediaSourceCache.title.contains(query, autoescape=True),
                    )
                )
            if platform_filter:
                criteria.append(MediaSourceCache.platform == platform_filter)
            return model, select(model), criteria, MediaSourceCache.updated_at.desc()
        if view == "telegram_file_cache":
            model = TelegramFileCache
            if query:
                criteria.append(
                    or_(
                        TelegramFileCache.source_key.contains(query, autoescape=True),
                        TelegramFileCache.title.contains(query, autoescape=True),
                        TelegramFileCache.quality.contains(query, autoescape=True),
                    )
                )
            return model, select(model), criteria, TelegramFileCache.last_used_at.desc()
        if view == "admin_login_tokens":
            model = AdminLoginToken
            if query:
                criteria.append(
                    or_(
                        cast(AdminLoginToken.id, String).contains(query, autoescape=True),
                        cast(AdminLoginToken.telegram_id, String).contains(query, autoescape=True),
                    )
                )
            return model, select(model), criteria, AdminLoginToken.created_at.desc()
        if view == "admin_sessions":
            model = AdminSession
            if query:
                criteria.append(
                    or_(
                        cast(AdminSession.id, String).contains(query, autoescape=True),
                        cast(AdminSession.telegram_id, String).contains(query, autoescape=True),
                    )
                )
            return model, select(model), criteria, AdminSession.last_seen_at.desc()
        raise ValueError("Noma’lum admin moduli")


@dataclass(frozen=True, slots=True)
class AdminPage:
    items: list[Any]
    total: int
    page: int
    page_size: int
    pages: int
    model: type[Any]


def selected_quality(media_type: MediaType, quality: str) -> str:
    if media_type == MediaType.VIDEO:
        if quality == "best":
            return "Eng yuqori mavjud sifat"
        return f"{quality}p"
    if quality == "m4a":
        return "M4A"
    return f"MP3 {quality} kbps"
