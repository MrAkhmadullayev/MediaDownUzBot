import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.dependencies import get_db_session, require_admin
from app.config import Settings
from app.enums import JobStatus
from app.models import AdminSession
from app.repositories import AdminRepository
from app.services.crypto import create_token, csrf_token, token_hash, tokens_match

login_router = APIRouter(prefix="/admin", tags=["admin-auth"])
admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)

TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


@login_router.get("/login/{raw_token}", include_in_schema=False, response_model=None)
async def admin_login(
    raw_token: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse | HTMLResponse:
    settings: Settings = request.app.state.settings
    if not TOKEN_PATTERN.fullmatch(raw_token):
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="access_denied.html",
            context={"message": "Kirish havolasi noto‘g‘ri."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    login_token = await AdminRepository.consume_login_token(
        session,
        token_hash(raw_token),
        settings.ADMIN_TELEGRAM_IDS,
    )
    if login_token is None:
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="access_denied.html",
            context={"message": "Havola eskirgan yoki avval ishlatilgan."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    raw_session_token = create_token()
    raw_csrf_token = csrf_token(
        raw_session_token,
        settings.FIELD_ENCRYPTION_KEY.get_secret_value(),
    )
    await AdminRepository.create_session(
        session,
        login_token.telegram_id,
        token_hash(raw_session_token),
        token_hash(raw_csrf_token),
        settings.ADMIN_SESSION_TTL_HOURS,
    )
    await session.commit()
    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="md_admin_session",
        value=raw_session_token,
        max_age=settings.ADMIN_SESSION_TTL_HOURS * 3600,
        path="/admin",
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    return response


@admin_router.get("", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _: AdminSession = Depends(require_admin),
) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    stats = await AdminRepository.dashboard_stats(session)
    users = await AdminRepository.recent_users(session)
    jobs = await AdminRepository.recent_jobs(session)
    raw_session_token = request.state.admin_session_token
    raw_csrf_token = csrf_token(
        raw_session_token,
        settings.FIELD_ENCRYPTION_KEY.get_secret_value(),
    )
    status_labels = {
        JobStatus.PENDING_ANALYSIS: "Tahlil navbatida",
        JobStatus.ANALYZING: "Tahlil qilinmoqda",
        JobStatus.WAITING_SELECTION: "Tanlov kutilmoqda",
        JobStatus.QUEUED: "Navbatda",
        JobStatus.DOWNLOADING: "Yuklanmoqda",
        JobStatus.UPLOADING: "Yuborilmoqda",
        JobStatus.SUCCESS: "Muvaffaqiyatli",
        JobStatus.ERROR: "Xatolik",
        JobStatus.CANCELLED: "Bekor qilingan",
    }
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "stats": stats,
            "users": users,
            "jobs": jobs,
            "csrf_token": raw_csrf_token,
            "status_labels": status_labels,
        },
    )


@admin_router.post("/logout", include_in_schema=False)
async def logout(
    request: Request,
    csrf: str = Form(alias="csrf_token", min_length=64, max_length=64),
    admin_session: AdminSession = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    expected = csrf_token(
        request.state.admin_session_token,
        settings.FIELD_ENCRYPTION_KEY.get_secret_value(),
    )
    if not tokens_match(csrf, expected) or not tokens_match(
        token_hash(csrf), admin_session.csrf_hash
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    await session.delete(admin_session)
    await session.commit()
    response = RedirectResponse(url="/admin/signed-out", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="md_admin_session", path="/admin")
    return response


@login_router.get("/signed-out", response_class=HTMLResponse, include_in_schema=False)
async def signed_out(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="access_denied.html",
        context={"message": "Admin paneldan xavfsiz chiqdingiz."},
    )
