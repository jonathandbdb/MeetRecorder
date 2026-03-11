# -*- coding: utf-8 -*-
"""
MeetRec — Persistent state management.
"""
import json

from .config import STATE_FILE


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
