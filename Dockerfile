FROM denoland/deno:bin-2.9.4 AS deno_runtime

FROM python:3.14.0-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app

COPY --from=deno_runtime /deno /usr/local/bin/deno

WORKDIR /opt/dependency-build

COPY pyproject.toml README.md ./

RUN mkdir app \
    && touch app/__init__.py \
    && pip install . \
    && rm -rf /opt/dependency-build

WORKDIR /app

COPY --chown=app:app . /app

RUN pip install --no-deps . \
    && mkdir -p /app/videos \
    && chown -R app:app /app

USER app

CMD ["python", "-m", "app.bot.main"]
