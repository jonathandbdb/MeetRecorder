# -*- coding: utf-8 -*-
"""
MeetRec — Configuration constants, paths and color palette.
"""
import os
import sys
from pathlib import Path

# --- Path resolution (works both in dev and packaged) ---
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.path.expanduser("~")) / ".meetrec"
DATA_DIR.mkdir(exist_ok=True)

# --- Settings ---
SAMPLE_RATE     = 44100
MP3_BITRATE     = "128k"
MAX_SOURCES     = 50
NOTEBOOK_PREFIX = "Reuniones"
STATE_FILE      = DATA_DIR / "notebooklm_state.json"
STORAGE_PATH    = DATA_DIR / "storage_state.json"
DEBUG_PORT      = 9234

# --- Color palette (Catppuccin Mocha) ---
BG_COLOR        = "#1e1e2e"
BG_DARKER       = "#181825"
SURFACE_COLOR   = "#313244"
SURFACE_LIGHT   = "#45475a"
TEXT_COLOR       = "#cdd6f4"
SUBTEXT_COLOR   = "#a6adc8"
MUTED_COLOR     = "#6c7086"
ACCENT_RED      = "#f38ba8"
ACCENT_GREEN    = "#a6e3a1"
ACCENT_YELLOW   = "#f9e2af"
ACCENT_BLUE     = "#89b4fa"
ACCENT_LAVENDER = "#b4befe"
BTN_IDLE_BG     = "#45475a"
BTN_HOVER_BG    = "#585b70"
CARD_BG         = "#1e1e2e"
