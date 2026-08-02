from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.admin.router import admin_router, login_router
from app.admin.schemas import HealthResponse
from app.config import Settings, get_settings
from app.database import Database
from app.logging import configure_logging

APP_DIR = Path(__file__).resolve().parents[1]


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.LOG_LEVEL)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.database = Database(resolved_settings.DATABASE_URL)
        app.state.redis = Redis.from_url(resolved_settings.REDIS_URL, decode_responses=True)
        templates = Jinja2Templates(directory=APP_DIR / "templates")
        templates.env.autoescape = True
        app.state.templates = templates
        yield
        await app.state.redis.aclose()
        await app.state.database.close()

    app = FastAPI(
        title="MediaDownUzBot Admin",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        lifespan=lifespan,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=resolved_settings.ALLOWED_HOSTS,
    )
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store"
        if resolved_settings.APP_ENV == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if request.url.path.startswith("/admin") and exc.status_code in {401, 403}:
            templates = request.app.state.templates
            message = (
                "Bu sahifani ko‘rish uchun bot orqali yangi admin havolasini oling."
                if exc.status_code == 401
                else "Ushbu amal uchun ruxsat berilmadi."
            )
            return templates.TemplateResponse(
                request=request,
                name="access_denied.html",
                context={"message": message},
                status_code=exc.status_code,
            )
        return HTMLResponse(status_code=exc.status_code, content="So‘rov bajarilmadi")

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def live() -> HealthResponse:
        return HealthResponse(status="ok", service="admin", version=__version__)

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def ready(request: Request) -> HealthResponse:
        try:
            async with request.app.state.database.session_factory() as session:
                await session.execute(text("SELECT 1"))
            await request.app.state.redis.ping()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE) from exc
        return HealthResponse(status="ok", service="admin", version=__version__)

    app.include_router(login_router)
    app.include_router(admin_router)
    return app


app = create_app()
