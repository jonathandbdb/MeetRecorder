# -*- coding: utf-8 -*-
"""
MeetRec — FFmpeg detection and MP3 conversion.
"""
import os
import shutil
import subprocess
import sys

from .config import ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW, APP_DIR, MP3_BITRATE

# None = not checked, True = available, False = unavailable
_ffmpeg_status = None


def _find_ffmpeg() -> str | None:
    """Locate ffmpeg binary (bundled or system PATH)."""
    bundled = APP_DIR / "ffmpeg" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if bundled.exists():
        return str(bundled)
    return shutil.which("ffmpeg")


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available and cache the result."""
    global _ffmpeg_status
    ffmpeg = _find_ffmpeg()
    _ffmpeg_status = ffmpeg is not None
    return _ffmpeg_status


def get_ffmpeg_warning() -> str | None:
    """Return a warning message if ffmpeg is not available."""
    if _ffmpeg_status is False:
        return "⚠️ ffmpeg no encontrado - Subiendo WAV sin comprimir"
    return None


def get_ffmpeg_status() -> bool | None:
    return _ffmpeg_status


def convertir_a_mp3(wav_path: str, log_fn, progress_callback=None) -> str:
    """Convert WAV to MP3 using ffmpeg. Returns the final file path."""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        log_fn("ffmpeg no encontrado, subiendo WAV.", ACCENT_YELLOW)
        if progress_callback:
            progress_callback(100)
        return wav_path

    mp3_path = wav_path.rsplit(".", 1)[0] + ".mp3"
    wav_size_mb = os.path.getsize(wav_path) / (1024 * 1024)
    log_fn(f"Comprimiendo ({wav_size_mb:.0f} MB → MP3 {MP3_BITRATE})...", ACCENT_YELLOW)

    if progress_callback:
        progress_callback(20)

    result = subprocess.run(
        [ffmpeg, "-y", "-i", wav_path, "-ac", "1", "-b:a", MP3_BITRATE, mp3_path],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if result.returncode != 0:
        log_fn(f"Error ffmpeg: {result.stderr[:200]}", ACCENT_RED)
        if progress_callback:
            progress_callback(100)
        return wav_path

    if progress_callback:
        progress_callback(80)

    mp3_size_mb = os.path.getsize(mp3_path) / (1024 * 1024)
    ratio = (1 - mp3_size_mb / wav_size_mb) * 100 if wav_size_mb > 0 else 0
    log_fn(f"Comprimido: {mp3_size_mb:.1f} MB ({ratio:.0f}% reducción)", ACCENT_GREEN)
    os.remove(wav_path)

    if progress_callback:
        progress_callback(100)

    return mp3_path
