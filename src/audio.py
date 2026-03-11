# -*- coding: utf-8 -*-
"""
MeetRec — Audio recording and post-recording processing.
"""
import datetime

import numpy as np
import soundcard as sc
import soundfile as sf

from .config import ACCENT_RED, ACCENT_YELLOW, DATA_DIR, MUTED_COLOR, SAMPLE_RATE
from .ffmpeg_utils import convertir_a_mp3, get_ffmpeg_warning
from .notebooklm_client import subir_audio

is_recording = False
audio_data = []


def record_audio(log_fn):
    """Capture mixed microphone + speaker audio."""
    global is_recording, audio_data
    try:
        mic = sc.default_microphone()
        spk = sc.get_microphone(
            id=str(sc.default_speaker().name), include_loopback=True,
        )
        log_fn(f"Micrófono : {mic.name}", MUTED_COLOR)
        log_fn(f"Altavoces : {spk.name}", MUTED_COLOR)

        with mic.recorder(samplerate=SAMPLE_RATE) as mic_rec, \
             spk.recorder(samplerate=SAMPLE_RATE) as spk_rec:
            while is_recording:
                data_mic = mic_rec.record(numframes=1024)
                data_spk = spk_rec.record(numframes=1024)
                mixed = (data_mic + data_spk) / 2.0
                audio_data.append(mixed)

    except Exception as e:
        log_fn(f"Error durante la grabación: {e}", ACCENT_RED)


def procesar_grabacion(log_fn, on_done, progress_callback=None):
    """Save WAV, compress to MP3 and upload to NotebookLM."""
    global audio_data
    try:
        log_fn("Guardando audio...", ACCENT_YELLOW)
        if progress_callback:
            progress_callback(5)

        audio_np = np.concatenate(audio_data)
        fecha = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        wav_path = str(DATA_DIR / f"reunion_{fecha}.wav")
        sf.write(wav_path, audio_np, SAMPLE_RATE)
        log_fn("Audio guardado", MUTED_COLOR)

        if progress_callback:
            progress_callback(15)

        ffmpeg_warning = get_ffmpeg_warning()
        if ffmpeg_warning:
            log_fn(ffmpeg_warning, ACCENT_YELLOW)

        upload_path = convertir_a_mp3(
            wav_path, log_fn,
            lambda p: progress_callback(15 + int(p * 0.35)) if progress_callback else None,
        )

        if progress_callback:
            progress_callback(50)

        subir_audio(
            upload_path, log_fn,
            lambda p: progress_callback(50 + int(p * 0.5)) if progress_callback else None,
        )
    except Exception as e:
        log_fn(f"Error: {e}", ACCENT_RED)
    finally:
        on_done()
