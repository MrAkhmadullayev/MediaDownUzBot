from app.enums import MediaType


def estimated_size_for(
    quality_sizes: dict[str, dict[str, int | None]] | None,
    media_type: MediaType,
    quality: str,
) -> int | None:
    if not quality_sizes:
        return None
    return quality_sizes.get(media_type.value, {}).get(quality)


def exceeds_upload_limit(size_bytes: int | None, upload_limit_bytes: int) -> bool:
    return size_bytes is not None and size_bytes > upload_limit_bytes
