import uuid

from redis.asyncio import Redis

RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def active_job_key(user_id: int) -> str:
    return f"active-job:{user_id}"


def media_download_key(source_key: str, media_type: str, quality: str) -> str:
    return f"media-download:{source_key}:{media_type}:{quality}"


async def acquire_active_job(
    redis: Redis,
    user_id: int,
    job_id: uuid.UUID,
    ttl_seconds: int,
) -> bool:
    return bool(await redis.set(active_job_key(user_id), str(job_id), ex=ttl_seconds, nx=True))


async def release_active_job(redis: Redis, user_id: int, job_id: uuid.UUID) -> None:
    await redis.eval(RELEASE_SCRIPT, 1, active_job_key(user_id), str(job_id))


async def acquire_media_download(
    redis: Redis,
    source_key: str,
    media_type: str,
    quality: str,
    job_id: uuid.UUID,
    ttl_seconds: int,
) -> bool:
    return bool(
        await redis.set(
            media_download_key(source_key, media_type, quality),
            str(job_id),
            ex=ttl_seconds,
            nx=True,
        )
    )


async def release_media_download(
    redis: Redis,
    source_key: str,
    media_type: str,
    quality: str,
    job_id: uuid.UUID,
) -> None:
    await redis.eval(
        RELEASE_SCRIPT,
        1,
        media_download_key(source_key, media_type, quality),
        str(job_id),
    )
