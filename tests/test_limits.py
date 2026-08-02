from app.enums import MediaType
from app.services.limits import estimated_size_for, exceeds_upload_limit


def test_estimated_size_for_selected_format() -> None:
    sizes = {"video": {"1080": 1_500_000_000}, "audio": {"192": 20_000_000}}

    assert estimated_size_for(sizes, MediaType.VIDEO, "1080") == 1_500_000_000
    assert estimated_size_for(sizes, MediaType.AUDIO, "192") == 20_000_000


def test_only_known_size_over_limit_is_blocked() -> None:
    assert exceeds_upload_limit(2_000_000_001, 2_000_000_000)
    assert not exceeds_upload_limit(2_000_000_000, 2_000_000_000)
    assert not exceeds_upload_limit(None, 2_000_000_000)
