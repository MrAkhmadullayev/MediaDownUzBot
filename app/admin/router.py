import re
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.dependencies import get_db_session, require_admin
from app.admin.presentation import MODULES, STATUS_LABELS, module_by_key, present_table
from app.config import Settings
from app.enums import JobStatus, Platform
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
    view: str = Query(default="download_jobs", max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=25, le=100),
    q: str = Query(default="", max_length=100),
    status_filter: str = Query(default="", alias="status", max_length=32),
    platform_filter: str = Query(default="", alias="platform", max_length=16),
    session: AsyncSession = Depends(get_db_session),
    _: AdminSession = Depends(require_admin),
) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    allowed_views = {module["key"] for module in MODULES}
    selected_view = view if view in allowed_views else "download_jobs"
    selected_page_size = page_size if page_size in {25, 50, 100} else 25
    selected_status = status_filter if status_filter in {item.value for item in JobStatus} else ""
    selected_platform = (
        platform_filter if platform_filter in {item.value for item in Platform} else ""
    )
    search_query = q.strip()
    stats = await AdminRepository.dashboard_stats(session)
    counts = await AdminRepository.table_counts(session)
    table_page = await AdminRepository.table_page(
        session,
        selected_view,
        page,
        selected_page_size,
        search_query,
        selected_status,
        selected_platform,
    )
    columns, rows = present_table(selected_view, table_page.items)
    raw_session_token = request.state.admin_session_token
    raw_csrf_token = csrf_token(
        raw_session_token,
        settings.FIELD_ENCRYPTION_KEY.get_secret_value(),
    )
    modules = [{**module, "count": counts[module["key"]]} for module in MODULES]

    def page_url(target_page: int) -> str:
        params = {
            "view": selected_view,
            "page": target_page,
            "page_size": selected_page_size,
        }
        if search_query:
            params["q"] = search_query
        if selected_status:
            params["status"] = selected_status
        if selected_platform:
            params["platform"] = selected_platform
        return f"/admin?{urlencode(params)}"

    first_item = (table_page.page - 1) * table_page.page_size + 1 if table_page.total else 0
    last_item = min(table_page.page * table_page.page_size, table_page.total)
    page_numbers = range(
        max(1, table_page.page - 2),
        min(table_page.pages, table_page.page + 2) + 1,
    )
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "stats": stats,
            "modules": modules,
            "current_module": module_by_key(selected_view),
            "selected_view": selected_view,
            "columns": columns,
            "rows": rows,
            "table_page": table_page,
            "first_item": first_item,
            "last_item": last_item,
            "page_numbers": page_numbers,
            "page_url": page_url,
            "query": search_query,
            "status_filter": selected_status,
            "platform_filter": selected_platform,
            "status_options": [(item.value, STATUS_LABELS[item]) for item in JobStatus],
            "platform_options": [(item.value, item.value.capitalize()) for item in Platform],
            "csrf_token": raw_csrf_token,
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
