from enum import StrEnum


class Platform(StrEnum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"


class MediaType(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"


class JobStatus(StrEnum):
    PENDING_ANALYSIS = "pending_analysis"
    ANALYZING = "analyzing"
    WAITING_SELECTION = "waiting_selection"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    UPLOADING = "uploading"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES = {
    JobStatus.SUCCESS,
    JobStatus.ERROR,
    JobStatus.CANCELLED,
}
