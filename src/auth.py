# -*- coding: utf-8 -*-
"""
MeetRec — Google authentication via Chrome CDP + auth verification.
"""
import asyncio
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from .config import (
    ACCENT_GREEN,
    ACCENT_RED,
    ACCENT_YELLOW,
    DATA_DIR,
    DEBUG_PORT,
    STORAGE_PATH,
)


def _storage_auth_ok() -> tuple[bool, str]:
    """Validate that current storage can actually access NotebookLM."""

    async def _check():
        from notebooklm import NotebookLMClient

        async with await NotebookLMClient.from_storage(path=str(STORAGE_PATH)) as client:
            await client.refresh_auth()
            notebooks = await client.notebooks.list()
            return len(notebooks)

    try:
        count = asyncio.run(_check())
        return True, f"Sesion validada. {count} notebooks accesibles."
    except Exception as e:
        return False, str(e)


def _find_chrome() -> str | None:
    """Locate Chrome/Chromium binary."""
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    else:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
        ]
    for p in candidates:
        if Path(p).exists():
            return p
    return shutil.which("google-chrome") or shutil.which("chromium")


def iniciar_login(log_fn, on_success, on_fail):
    """Open Chrome with remote debugging to capture Google cookies."""
    chrome_exe = _find_chrome()
    if not chrome_exe:
        log_fn("No se encontró Chrome/Chromium.", ACCENT_RED)
        on_fail()
        return

    temp_profile = DATA_DIR / "temp_chrome_profile"
    if temp_profile.exists():
        shutil.rmtree(temp_profile, ignore_errors=True)
    temp_profile.mkdir(parents=True, exist_ok=True)

    log_fn("Abriendo Chrome para login...", ACCENT_YELLOW)
    log_fn("Logueate y esperá al dashboard de NotebookLM.", ACCENT_YELLOW)

    proc = subprocess.Popen([
        chrome_exe,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={temp_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://accounts.google.com/ServiceLogin?continue=https://notebooklm.google.com/",
    ])

    required = {"SID", "HSID", "SSID", "APISID", "SAPISID"}

    def _poll():
        import time

        from playwright.sync_api import sync_playwright
        already_warned_invalid = False

        for _ in range(60):
            time.sleep(5)
            try:
                with sync_playwright() as p:
                    browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
                    ctx = browser.contexts[0]
                    cookies = ctx.cookies()
                    cookie_names = {c["name"] for c in cookies}
                    current_urls = [page.url for page in ctx.pages]
                    reached_notebooklm = any(url.startswith("https://notebooklm.google.com") for url in current_urls)

                    if required.issubset(cookie_names) and reached_notebooklm:
                        with open(STORAGE_PATH, "w") as f:
                            json.dump({"cookies": cookies, "origins": []}, f, indent=2)

                        is_valid, detail = _storage_auth_ok()
                        if is_valid:
                            log_fn(f"Login exitoso! {len(cookies)} cookies.", ACCENT_GREEN)
                            log_fn(detail, ACCENT_GREEN)
                            browser.close()
                            if proc.poll() is None:
                                proc.terminate()
                            on_success()
                            return

                        if not already_warned_invalid:
                            log_fn("Login detectado, pero la sesion aun no es valida. Esperando...")
                            already_warned_invalid = True

                    browser.close()
            except Exception:
                pass

        log_fn("Timeout: login no completado.", ACCENT_RED)
        if proc.poll() is None:
            proc.terminate()
        on_fail()

    threading.Thread(target=_poll, daemon=True).start()


def verificar_auth(log_fn, on_ok, on_fail):
    """Check if NotebookLM authentication is valid."""
    async def _check():
        from notebooklm import NotebookLMClient
        async with await NotebookLMClient.from_storage(
            path=str(STORAGE_PATH),
        ) as client:
            await client.refresh_auth()
            return len(await client.notebooks.list())

    try:
        count = asyncio.run(_check())
        log_fn(f"Autenticado. {count} notebooks.", ACCENT_GREEN)
        log_fn("Listo para grabar.", ACCENT_GREEN)
        on_ok()
    except FileNotFoundError:
        log_fn("No autenticado. Usá el botón de login.", ACCENT_RED)
        on_fail()
    except Exception as e:
        log_fn(f"Sesión expirada: {e}", ACCENT_RED)
        log_fn("Usá el botón de login.", ACCENT_RED)
        on_fail()
