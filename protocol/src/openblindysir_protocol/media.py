"""Single closed input-format policy shared by catalogue validation and the Bridge."""

from typing import Final

INPUT_DEMUXERS: Final = {
    "mp3": (".mp3",),
    "flac": (".flac",),
    "wav": (".wav",),
    "mov": (".m4a", ".mp4", ".mov", ".m4v", ".3gp"),
    "ogg": (".ogg", ".oga", ".opus"),
    "aiff": (".aiff", ".aif"),
    "asf": (".wma", ".wmv", ".asf"),
    "aac": (".aac",),
    "matroska": (".mkv", ".mka", ".webm"),
    "avi": (".avi",),
}
INPUT_EXTENSIONS: Final = frozenset(ext for exts in INPUT_DEMUXERS.values() for ext in exts)
INPUT_DEMUXER_BY_EXTENSION: Final = {
    ext: demuxer for demuxer, extensions in INPUT_DEMUXERS.items() for ext in extensions
}
DEMUXER_WHITELIST: Final = ",".join(INPUT_DEMUXERS)
