from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import AdminSession
from app.repositories import AdminRepository
from app.services.crypto import token_hash


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def require_admin(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AdminSession:
    settings: Settings = request.app.state.settings
    raw_token = request.cookies.get("md_admin_session")
    if raw_token is None or not 32 <= len(raw_token) <= 256:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    admin_session = await AdminRepository.get_session(
        session,
        token_hash(raw_token),
        settings.ADMIN_TELEGRAM_IDS,
    )
    if admin_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    request.state.admin_session_token = raw_token
    return admin_session
