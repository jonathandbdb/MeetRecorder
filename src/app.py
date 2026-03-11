# -*- coding: utf-8 -*-
"""
MeetRec — Grabador de Reuniones para NotebookLM
Standalone desktop application.
"""
import soundcard as sc
import soundfile as sf
import numpy as np
import subprocess
import shutil
import threading
import datetime
import asyncio
import json
import sys
import os
import tkinter as tk
from tkinter import scrolledtext, messagebox
from pathlib import Path

# --- Resolución de rutas (funciona tanto en dev como empaquetado) ---
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.path.expanduser("~")) / ".meetrec"
DATA_DIR.mkdir(exist_ok=True)

# --- CONFIGURACIÓN ---
SAMPLE_RATE     = 44100
MP3_BITRATE     = "128k"  # MP3 a 128kbps - buena calidad y compatible
MAX_SOURCES     = 50
NOTEBOOK_PREFIX = "Reuniones"
STATE_FILE      = DATA_DIR / "notebooklm_state.json"
STORAGE_PATH    = DATA_DIR / "storage_state.json"
DEBUG_PORT      = 9234

# --- PALETA DE COLORES (Catppuccin Mocha) ---
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

is_recording = False
audio_data   = []

# --- VALIDACIÓN DE FFMPEG ---
_ffmpeg_status = None  # None = no chequeado, True = disponible, False = no disponible

def check_ffmpeg():
    """Verifica si ffmpeg está disponible y guarda el resultado."""
    global _ffmpeg_status
    ffmpeg = _find_ffmpeg()
    _ffmpeg_status = ffmpeg is not None
    return _ffmpeg_status

def get_ffmpeg_warning():
    """Retorna mensaje de warning si ffmpeg no está disponible."""
    if _ffmpeg_status is False:
        return "⚠️ ffmpeg no encontrado - Subiendo WAV sin comprimir"
    return None


# ---------------------------------------------------------------------------
# ffmpeg — busca bundled o en PATH
# ---------------------------------------------------------------------------

def _find_ffmpeg() -> str | None:
    # 1. Bundled junto al ejecutable
    bundled = APP_DIR / "ffmpeg" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if bundled.exists():
        return str(bundled)
    # 2. En PATH del sistema
    return shutil.which("ffmpeg")


# ---------------------------------------------------------------------------
# Estado persistente
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


# ---------------------------------------------------------------------------
# Lógica de audio
# ---------------------------------------------------------------------------

def record_audio(log_fn):
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


# ---------------------------------------------------------------------------
# NotebookLM
# ---------------------------------------------------------------------------

async def _get_or_create_notebook(client, log_fn) -> str:
    from notebooklm import RPCError

    state = _load_state()
    nb_id = state.get("notebook_id")

    if nb_id:
        try:
            sources = await client.sources.list(nb_id)
            count = len(sources)
            log_fn(f"Notebook activo: {count}/{MAX_SOURCES} fuentes", MUTED_COLOR)
            if count < MAX_SOURCES:
                return nb_id
            else:
                log_fn(f"Notebook lleno. Creando uno nuevo...", ACCENT_YELLOW)
        except (RPCError, Exception):
            log_fn("Notebook previo no encontrado. Creando uno nuevo...", ACCENT_YELLOW)

    fecha = datetime.datetime.now().strftime("%Y-%m")
    titulo = f"{NOTEBOOK_PREFIX} {fecha}"
    nb = await client.notebooks.create(titulo)
    log_fn(f"Notebook creado: '{titulo}'", ACCENT_GREEN)
    _save_state({"notebook_id": nb.id, "title": titulo})
    return nb.id


async def _subir_a_notebooklm(file_path: str, log_fn, progress_callback=None):
    from notebooklm import NotebookLMClient

    log_fn("Conectando con NotebookLM...", ACCENT_YELLOW)
    if progress_callback:
        progress_callback(10)

    async with await NotebookLMClient.from_storage(
        path=str(STORAGE_PATH),
    ) as client:
        nb_id = await _get_or_create_notebook(client, log_fn)
        
        if progress_callback:
            progress_callback(30)

        log_fn("Subiendo audio al notebook...", ACCENT_YELLOW)
        if progress_callback:
            progress_callback(50)
        
        source = await client.sources.add_file(nb_id, Path(file_path))
        
        if progress_callback:
            progress_callback(80)
            
        log_fn(f"Fuente agregada: {source.title}", ACCENT_GREEN)

        fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        nuevo_titulo = f"Reunión {fecha}"
        await client.sources.rename(nb_id, source.id, nuevo_titulo)
        log_fn(f"Renombrada a: '{nuevo_titulo}'", MUTED_COLOR)
        log_fn("Audio subido a NotebookLM!", ACCENT_GREEN)
        log_fn("Abrí NotebookLM para ver la transcripción.", ACCENT_BLUE)
        
        if progress_callback:
            progress_callback(100)


def subir_audio(file_path: str, log_fn, progress_callback=None):
    asyncio.run(_subir_a_notebooklm(file_path, log_fn, progress_callback))


# ---------------------------------------------------------------------------
# Conversión a MP3
# ---------------------------------------------------------------------------

def convertir_a_mp3(wav_path: str, log_fn, progress_callback=None) -> str:
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


# ---------------------------------------------------------------------------
# Procesamiento post-grabación
# ---------------------------------------------------------------------------

def procesar_grabacion(log_fn, on_done, progress_callback=None):
    global audio_data
    try:
        log_fn("Guardando audio...", ACCENT_YELLOW)
        if progress_callback:
            progress_callback(5)
            
        audio_np = np.concatenate(audio_data)
        fecha = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        wav_path = str(DATA_DIR / f"reunion_{fecha}.wav")
        sf.write(wav_path, audio_np, SAMPLE_RATE)
        log_fn(f"Audio guardado", MUTED_COLOR)

        if progress_callback:
            progress_callback(15)

        # Check for ffmpeg warning
        ffmpeg_warning = get_ffmpeg_warning()
        if ffmpeg_warning:
            log_fn(ffmpeg_warning, ACCENT_YELLOW)

        upload_path = convertir_a_mp3(wav_path, log_fn, 
            lambda p: progress_callback(15 + int(p * 0.35)) if progress_callback else None)
        
        if progress_callback:
            progress_callback(50)
            
        subir_audio(upload_path, log_fn,
            lambda p: progress_callback(50 + int(p * 0.5)) if progress_callback else None)
    except Exception as e:
        log_fn(f"Error: {e}", ACCENT_RED)
    finally:
        on_done()


# ---------------------------------------------------------------------------
# Login integrado — Chrome CDP
# ---------------------------------------------------------------------------

def _find_chrome() -> str | None:
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    else:  # Linux
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
    # Fallback: buscar en PATH
    return shutil.which("google-chrome") or shutil.which("chromium")


def iniciar_login(log_fn, on_success, on_fail):
    chrome_exe = _find_chrome()
    if not chrome_exe:
        log_fn("No se encontró Chrome/Chromium.", ACCENT_RED)
        on_fail()
        return

    temp_profile = DATA_DIR / "temp_chrome_profile"
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

        for _ in range(60):
            time.sleep(5)
            try:
                with sync_playwright() as p:
                    browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
                    ctx = browser.contexts[0]
                    cookies = ctx.cookies([
                        "https://notebooklm.google.com",
                        "https://google.com",
                        "https://.google.com",
                    ])
                    if required.issubset({c["name"] for c in cookies}):
                        with open(STORAGE_PATH, "w") as f:
                            json.dump({"cookies": cookies, "origins": []}, f, indent=2)
                        log_fn(f"Login exitoso! {len(cookies)} cookies.", ACCENT_GREEN)
                        browser.close()
                        proc.kill()
                        on_success()
                        return
                    browser.close()
            except Exception:
                pass

        log_fn("Timeout: login no completado.", ACCENT_RED)
        proc.kill()
        on_fail()

    threading.Thread(target=_poll, daemon=True).start()


# ---------------------------------------------------------------------------
# Verificación de autenticación
# ---------------------------------------------------------------------------

def listar_notebooks_con_fuentes():
    async def _fetch():
        from notebooklm import NotebookLMClient
        async with await NotebookLMClient.from_storage(
            path=str(STORAGE_PATH),
        ) as client:
            notebooks = await client.notebooks.list()
            result = []
            for nb in notebooks:
                try:
                    sources = await client.sources.list(nb.id)
                    count = len(sources)
                except Exception:
                    count = -1
                result.append({
                    "id": nb.id,
                    "title": nb.title or "(Sin título)",
                    "source_count": count,
                })
            return result
    return asyncio.run(_fetch())


def verificar_auth(log_fn, on_ok, on_fail):
    async def _check():
        from notebooklm import NotebookLMClient
        async with await NotebookLMClient.from_storage(
            path=str(STORAGE_PATH),
        ) as client:
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


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def _make_card(parent, **kw):
    outer = tk.Frame(parent, bg=BG_DARKER, padx=1, pady=1)
    inner = tk.Frame(outer, bg=CARD_BG, **kw)
    inner.pack(fill="both", expand=True)
    return outer, inner


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MeetRec — Grabador de Reuniones")
        self.configure(bg=BG_DARKER)
        self.resizable(False, False)
        self._recording_seconds = 0
        self._timer_id = None
        self._processing = False
        self._build_ui()
        
        # Bind keyboard shortcuts
        self.bind("<Control-r>", lambda e: self._toggle_recording())
        self.bind("<Control-R>", lambda e: self._toggle_recording())
        self.bind("<Escape>", lambda e: self._escape_pressed())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Check ffmpeg status
        check_ffmpeg()
        
        threading.Thread(
            target=verificar_auth,
            args=(self._log, self._on_auth_ok, self._on_auth_fail),
            daemon=True,
        ).start()

    def _escape_pressed(self):
        """Maneja la presión de Escape - detiene grabación si está activa."""
        if is_recording:
            self._toggle_recording()

    def _on_close(self):
        """Maneja el cierre de la ventana."""
        if is_recording:
            result = messagebox.askyesno(
                "Grabación en progreso",
                "¡Estás grabando! ¿Querés detener la grabación y salir?",
                icon="warning"
            )
            if result:
                self._toggle_recording()
                # Wait a bit then close
                self.after(500, self.destroy)
        else:
            self.destroy()

    def _build_ui(self):
        PADX = 20

        # HEADER
        header = tk.Frame(self, bg=BG_DARKER, pady=20)
        header.pack(fill="x")

        title_row = tk.Frame(header, bg=BG_DARKER)
        title_row.pack()
        
        # Title with icon
        tk.Label(
            title_row, text="🎙️",
            font=("Segoe UI", 20), bg=BG_DARKER, fg=ACCENT_RED,
        ).pack(side="left", padx=(0, 5))
        tk.Label(
            title_row, text="MeetRec",
            font=("Segoe UI", 20, "bold"), bg=BG_DARKER, fg=TEXT_COLOR,
        ).pack(side="left")
        tk.Label(
            title_row, text="  for NotebookLM",
            font=("Segoe UI", 11), bg=BG_DARKER, fg=MUTED_COLOR,
        ).pack(side="left", pady=(6, 0))

        tk.Label(
            header,
            text="Graba tu reunión  ·  Comprime a MP3  ·  Sube automáticamente",
            font=("Segoe UI", 9), bg=BG_DARKER, fg=MUTED_COLOR,
        ).pack(pady=(2, 0))

        # RECORDING CARD
        rec_outer, rec_card = _make_card(self, padx=20, pady=16)
        rec_outer.pack(fill="x", padx=PADX, pady=(0, 8))

        status_row = tk.Frame(rec_card, bg=CARD_BG)
        status_row.pack(fill="x")

        # Improved recording indicator with pulse effect
        self.dot_canvas = tk.Canvas(
            status_row, width=24, height=24, bg=CARD_BG, highlightthickness=0,
        )
        self.dot_canvas.pack(side="left", padx=(0, 8))
        # Outer glow circle
        self.dot_outer = self.dot_canvas.create_oval(2, 2, 22, 22, fill="", outline=ACCENT_RED, width=0)
        # Inner solid circle
        self.dot = self.dot_canvas.create_oval(7, 7, 17, 17, fill=MUTED_COLOR, outline="")

        self.status_label = tk.Label(
            status_row, text="Verificando autenticación...",
            font=("Segoe UI", 10), bg=CARD_BG, fg=MUTED_COLOR,
        )
        self.status_label.pack(side="left")

        self.timer_label = tk.Label(
            status_row, text="", font=("Consolas", 10, "bold"), bg=CARD_BG, fg=MUTED_COLOR,
        )
        self.timer_label.pack(side="right")

        self.rec_btn = tk.Button(
            rec_card, text="⏺  Iniciar grabación",
            font=("Segoe UI", 13, "bold"),
            bg=BTN_IDLE_BG, fg=TEXT_COLOR,
            activebackground=ACCENT_RED, activeforeground="#1e1e2e",
            relief="flat", cursor="hand2", padx=30, pady=12,
            state="disabled", command=self._toggle_recording,
        )
        self.rec_btn.pack(fill="x", pady=(14, 0))
        self._bind_hover(self.rec_btn, BTN_HOVER_BG, BTN_IDLE_BG)

        # Progress bar (hidden by default)
        self.progress_frame = tk.Frame(rec_card, bg=CARD_BG)
        self.progress_frame.pack(fill="x", pady=(8, 0))
        self.progress_frame.pack_forget()  # Hide initially
        
        self.progress_bar = tk.Canvas(
            self.progress_frame, height=6, bg=SURFACE_COLOR, highlightthickness=0,
        )
        self.progress_bar.pack(fill="x")
        self.progress_fill = self.progress_bar.create_rectangle(0, 0, 0, 6, fill=ACCENT_BLUE, outline="")
        self.progress_label = tk.Label(
            self.progress_frame, text="", font=("Segoe UI", 8),
            bg=CARD_BG, fg=MUTED_COLOR,
        )
        self.progress_label.pack()

        self.login_btn = tk.Button(
            rec_card, text="🔑  Iniciar sesión en Google",
            font=("Segoe UI", 10),
            bg=ACCENT_BLUE, fg="#1e1e2e",
            activebackground="#7ba3e0", activeforeground="#1e1e2e",
            relief="flat", cursor="hand2", padx=18, pady=10,
            command=self._start_login,
        )

        # Keyboard shortcuts hint
        shortcuts_frame = tk.Frame(rec_card, bg=CARD_BG)
        shortcuts_frame.pack(fill="x", pady=8)
        tk.Label(
            shortcuts_frame, text="Ctrl+R: Grabar  |  Esc: Detener",
            font=("Segoe UI", 7), bg=CARD_BG, fg=MUTED_COLOR,
        ).pack()

        # NOTEBOOKS CARD
        self.nb_card_outer, self.nb_card = _make_card(self, padx=16, pady=12)

        nb_top = tk.Frame(self.nb_card, bg=CARD_BG)
        nb_top.pack(fill="x")
        tk.Label(
            nb_top, text="📒  Notebooks",
            font=("Segoe UI", 10, "bold"), bg=CARD_BG, fg=SUBTEXT_COLOR,
        ).pack(side="left")

        btn_row = tk.Frame(nb_top, bg=CARD_BG)
        btn_row.pack(side="right")
        self.nb_refresh_btn = tk.Button(
            btn_row, text="↻", font=("Segoe UI", 10),
            bg=CARD_BG, fg=MUTED_COLOR, relief="flat",
            cursor="hand2", padx=6, pady=0, bd=0,
            command=self._refresh_notebooks,
        )
        self.nb_refresh_btn.pack(side="right")
        self.nb_new_btn = tk.Button(
            btn_row, text="+ Nuevo", font=("Segoe UI", 9),
            bg=ACCENT_LAVENDER, fg="#1e1e2e", relief="flat",
            cursor="hand2", padx=10, pady=2,
            command=self._create_notebook_dialog,
        )
        self.nb_new_btn.pack(side="right", padx=(0, 6))

        self._notebooks_data = []

        # Search
        search_frame = tk.Frame(self.nb_card, bg=SURFACE_COLOR, padx=8, pady=4)
        search_frame.pack(fill="x", pady=(8, 6))
        tk.Label(
            search_frame, text="🔍", font=("Segoe UI", 9),
            bg=SURFACE_COLOR, fg=MUTED_COLOR,
        ).pack(side="left")
        self.nb_search_var = tk.StringVar()
        self._nb_search_entry = tk.Entry(
            search_frame, textvariable=self.nb_search_var,
            font=("Segoe UI", 9), bg=SURFACE_COLOR, fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR, relief="flat", bd=0,
        )
        self._nb_search_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._nb_search_placeholder = True
        self._nb_search_entry.insert(0, "Buscar notebook...")
        self._nb_search_entry.configure(fg=MUTED_COLOR)
        self._nb_search_entry.bind("<FocusIn>", self._search_focus_in)
        self._nb_search_entry.bind("<FocusOut>", self._search_focus_out)

        # Notebook list
        nb_list_frame = tk.Frame(self.nb_card, bg=SURFACE_COLOR)
        nb_list_frame.pack(fill="x", pady=(0, 6))
        self.nb_listbox_canvas = tk.Canvas(
            nb_list_frame, bg=SURFACE_COLOR, highlightthickness=0, height=110,
        )
        self.nb_scrollbar = tk.Scrollbar(
            nb_list_frame, orient="vertical",
            command=self.nb_listbox_canvas.yview,
            bg=SURFACE_COLOR, troughcolor=SURFACE_COLOR,
        )
        self.nb_inner_frame = tk.Frame(self.nb_listbox_canvas, bg=SURFACE_COLOR)
        self.nb_inner_frame.bind(
            "<Configure>",
            lambda e: self.nb_listbox_canvas.configure(
                scrollregion=self.nb_listbox_canvas.bbox("all"),
            ),
        )
        self.nb_listbox_canvas.create_window((0, 0), window=self.nb_inner_frame, anchor="nw")
        self.nb_listbox_canvas.configure(yscrollcommand=self.nb_scrollbar.set)
        self.nb_listbox_canvas.pack(side="left", fill="both", expand=True)
        self.nb_scrollbar.pack(side="right", fill="y")

        self.nb_active_label = tk.Label(
            self.nb_card, text="Destino:  (ninguno)",
            font=("Segoe UI", 9), bg=CARD_BG, fg=MUTED_COLOR, anchor="w",
        )
        self.nb_active_label.pack(fill="x")

        # Conectar trace DESPUÉS de crear todos los widgets del notebook
        self.nb_search_var.trace_add("write", lambda *_: self._filter_notebooks())

        # LOG
        log_outer, log_card = _make_card(self, padx=0, pady=0)
        log_outer.pack(fill="x", padx=PADX, pady=(8, 14))
        self.log_frame = log_outer

        self.log_box = scrolledtext.ScrolledText(
            log_card, width=66, height=12,
            bg=CARD_BG, fg=TEXT_COLOR, font=("Consolas", 9),
            relief="flat", state="disabled",
            insertbackground=TEXT_COLOR, selectbackground=SURFACE_LIGHT,
            padx=10, pady=8,
        )
        self.log_box.pack(fill="both")

        for tag, color in [
            ("yellow", ACCENT_YELLOW), ("green", ACCENT_GREEN),
            ("red", ACCENT_RED), ("blue", ACCENT_BLUE),
            ("lavender", ACCENT_LAVENDER), ("muted", MUTED_COLOR),
            ("normal", TEXT_COLOR),
        ]:
            self.log_box.tag_config(tag, foreground=color)

        self._color_tag = {
            ACCENT_YELLOW: "yellow", ACCENT_GREEN: "green",
            ACCENT_RED: "red", ACCENT_BLUE: "blue",
            ACCENT_LAVENDER: "lavender", MUTED_COLOR: "muted",
            TEXT_COLOR: "normal",
        }

        # FOOTER
        self.footer_frame = tk.Frame(self, bg=BG_DARKER)
        self.footer_frame.pack(pady=(0, 10))
        
        # ffmpeg status indicator in footer
        self.ffmpeg_label = tk.Label(
            self.footer_frame, text="",
            font=("Segoe UI", 8), bg=BG_DARKER, fg=MUTED_COLOR,
        )
        self.ffmpeg_label.pack()
        
        tk.Label(
            self.footer_frame, text="MP3 128kbps  ·  NotebookLM API  ·  v2.2",
            font=("Segoe UI", 8), bg=BG_DARKER, fg=MUTED_COLOR,
        ).pack()

    def _update_ffmpeg_status(self):
        """Actualiza el indicador de estado de ffmpeg."""
        check_ffmpeg()
        if _ffmpeg_status:
            self.ffmpeg_label.configure(text="✓ ffmpeg disponible", fg=ACCENT_GREEN)
        else:
            self.ffmpeg_label.configure(text="⚠️ ffmpeg no encontrado", fg=ACCENT_YELLOW)

    # -- Utilities --

    @staticmethod
    def _bind_hover(widget, hover_bg, normal_bg):
        widget.bind("<Enter>", lambda e: widget.configure(bg=hover_bg))
        widget.bind("<Leave>", lambda e: widget.configure(bg=normal_bg))

    def _log(self, msg: str, color: str = TEXT_COLOR):
        def _write():
            self.log_box.configure(state="normal")
            tag = self._color_tag.get(color, "normal")
            self.log_box.insert("end", f"  {msg}\n", tag)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _write)

    def _set_status(self, text: str, color: str):
        self.dot_canvas.itemconfig(self.dot, fill=color)
        self.status_label.configure(text=text, fg=color)

    def _show_progress(self, show: bool):
        """Muestra u oculta la barra de progreso."""
        if show:
            self.progress_frame.pack(fill="x", pady=(8, 0))
        else:
            self.progress_frame.pack_forget()

    def _update_progress(self, value: int, label: str = ""):
        """Actualiza la barra de progreso."""
        # Get width of progress bar
        try:
            width = self.progress_bar.winfo_width()
            if width > 0:
                fill_width = int((value / 100) * width)
                self.progress_bar.coords(self.progress_fill, 0, 0, fill_width, 6)
        except:
            pass
        
        if label:
            self.progress_label.configure(text=label)

    # -- Auth --

    def _on_auth_ok(self):
        def _show():
            self.rec_btn.configure(state="normal")
            self.login_btn.pack_forget()
            self.nb_card_outer.pack(fill="x", padx=20, pady=(0, 0), before=self.log_frame)
            self._set_status("Listo para grabar", ACCENT_GREEN)
            self._update_active_label()
            self._update_ffmpeg_status()
            self._refresh_notebooks()
        self.after(0, _show)

    def _on_auth_fail(self):
        self.after(0, lambda: (
            self.login_btn.pack(fill="x", pady=(8, 0)),
            self._set_status("No autenticado", ACCENT_RED),
            self._update_ffmpeg_status(),
        ))

    def _start_login(self):
        self.login_btn.configure(state="disabled", text="⏳  Esperando login...")
        self._set_status("Esperando login en Chrome...", ACCENT_YELLOW)
        threading.Thread(
            target=iniciar_login,
            args=(self._log, self._on_login_success, self._on_login_fail),
            daemon=True,
        ).start()

    def _on_login_success(self):
        def _show():
            self.login_btn.pack_forget()
            self.rec_btn.configure(state="normal")
            self.nb_card_outer.pack(fill="x", padx=20, pady=(0, 0), before=self.log_frame)
            self._set_status("Listo para grabar", ACCENT_GREEN)
            self._update_active_label()
            self._refresh_notebooks()
        self.after(0, _show)

    def _on_login_fail(self):
        self.after(0, lambda: (
            self.login_btn.configure(state="normal", text="🔑  Iniciar sesión en Google"),
            self._set_status("Login fallido", ACCENT_RED),
        ))

    # -- Notebooks --

    def _refresh_notebooks(self):
        self.nb_refresh_btn.configure(state="disabled", text="⏳")
        threading.Thread(target=self._fetch_notebooks, daemon=True).start()

    def _fetch_notebooks(self):
        try:
            data = listar_notebooks_con_fuentes()
            self._notebooks_data = data
            self.after(0, lambda: self._render_notebooks(data))
        except Exception as e:
            self._log(f"Error cargando notebooks: {e}", ACCENT_RED)
        finally:
            self.after(0, lambda: self.nb_refresh_btn.configure(state="normal", text="↻"))

    def _render_notebooks(self, data):
        for w in self.nb_inner_frame.winfo_children():
            w.destroy()

        state = _load_state()
        active_id = state.get("notebook_id")

        if not data:
            tk.Label(
                self.nb_inner_frame, text="  Sin notebooks",
                font=("Segoe UI", 9), bg=SURFACE_COLOR, fg=MUTED_COLOR,
            ).pack(anchor="w", padx=8, pady=8)
            return

        for i, nb in enumerate(data):
            bg = SURFACE_COLOR if i % 2 == 0 else SURFACE_LIGHT
            row = tk.Frame(self.nb_inner_frame, bg=bg)
            row.pack(fill="x")

            count = nb["source_count"]
            is_full = count >= MAX_SOURCES
            is_active = nb["id"] == active_id

            bar_color = ACCENT_GREEN if is_active else (ACCENT_RED if is_full else bg)
            tk.Frame(row, bg=bar_color, width=3).pack(side="left", fill="y")

            title = nb["title"][:32] + ("…" if len(nb["title"]) > 32 else "")
            tk.Label(
                row, text=title, font=("Segoe UI", 9), bg=bg,
                fg=TEXT_COLOR if not is_full else MUTED_COLOR, anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=(8, 4), pady=3)

            count_color = ACCENT_RED if is_full else (ACCENT_YELLOW if count >= 40 else MUTED_COLOR)
            tk.Label(
                row, text=f"{count}/{MAX_SOURCES}", font=("Consolas", 8),
                bg=bg, fg=count_color, width=6,
            ).pack(side="right", padx=(0, 6))

            if is_full:
                tk.Label(row, text="LLENO", font=("Segoe UI", 7, "bold"), bg=bg, fg=ACCENT_RED).pack(side="right", padx=(0, 4))
            elif is_active:
                tk.Label(row, text="ACTIVO", font=("Segoe UI", 7, "bold"), bg=bg, fg=ACCENT_GREEN).pack(side="right", padx=(0, 4))
            else:
                nb_id, nb_title = nb["id"], nb["title"]
                tk.Button(
                    row, text="Usar", font=("Segoe UI", 7),
                    bg=BTN_IDLE_BG, fg=TEXT_COLOR, relief="flat",
                    cursor="hand2", padx=6, pady=0,
                    command=lambda nid=nb_id, nt=nb_title: self._select_notebook(nid, nt),
                ).pack(side="right", padx=(0, 4))

        self._update_active_label()

    def _select_notebook(self, nb_id, nb_title):
        _save_state({"notebook_id": nb_id, "title": nb_title})
        self._log(f"Notebook seleccionado: '{nb_title}'", ACCENT_GREEN)
        self._update_active_label()
        self._render_notebooks(self._notebooks_data)

    def _update_active_label(self):
        state = _load_state()
        self.nb_active_label.configure(text=f"Destino:  {state.get('title', '(ninguno)')}")

    def _search_focus_in(self, _):
        if self._nb_search_placeholder:
            self._nb_search_entry.delete(0, "end")
            self._nb_search_entry.configure(fg=TEXT_COLOR)
            self._nb_search_placeholder = False

    def _search_focus_out(self, _):
        if not self.nb_search_var.get():
            self._nb_search_placeholder = True
            self._nb_search_entry.insert(0, "Buscar notebook...")
            self._nb_search_entry.configure(fg=MUTED_COLOR)

    def _filter_notebooks(self):
        q = self.nb_search_var.get().strip().lower()
        if self._nb_search_placeholder or not q:
            self._render_notebooks(self._notebooks_data)
        else:
            self._render_notebooks([nb for nb in self._notebooks_data if q in nb["title"].lower()])

    def _create_notebook_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Nuevo Notebook")
        dialog.configure(bg=BG_DARKER)
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(
            dialog, text="Nombre del notebook:",
            font=("Segoe UI", 10), bg=BG_DARKER, fg=TEXT_COLOR,
        ).pack(padx=20, pady=(20, 4))

        entry = tk.Entry(
            dialog, font=("Segoe UI", 10),
            bg=SURFACE_COLOR, fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR, relief="flat", width=30,
        )
        default = f"{NOTEBOOK_PREFIX} {datetime.datetime.now().strftime('%Y-%m')}"
        entry.insert(0, default)
        entry.select_range(0, "end")
        entry.pack(padx=20, pady=4, ipady=4)
        entry.focus_set()

        def _create():
            name = entry.get().strip()
            if not name:
                return
            dialog.destroy()
            self._log(f"Creando '{name}'...", ACCENT_YELLOW)
            threading.Thread(target=self._do_create_notebook, args=(name,), daemon=True).start()

        bf = tk.Frame(dialog, bg=BG_DARKER)
        bf.pack(pady=(12, 20))
        tk.Button(bf, text="Crear", font=("Segoe UI", 10), bg=ACCENT_GREEN, fg="#1e1e2e", relief="flat", cursor="hand2", padx=20, pady=4, command=_create).pack(side="left", padx=4)
        tk.Button(bf, text="Cancelar", font=("Segoe UI", 10), bg=BTN_IDLE_BG, fg=TEXT_COLOR, relief="flat", cursor="hand2", padx=20, pady=4, command=dialog.destroy).pack(side="left", padx=4)
        entry.bind("<Return>", lambda e: _create())

    def _do_create_notebook(self, name):
        try:
            async def _create():
                from notebooklm import NotebookLMClient
                async with await NotebookLMClient.from_storage(path=str(STORAGE_PATH)) as client:
                    return await client.notebooks.create(name)
            nb = asyncio.run(_create())
            _save_state({"notebook_id": nb.id, "title": name})
            self._log(f"Notebook '{name}' creado.", ACCENT_GREEN)
            self._refresh_notebooks()
        except Exception as e:
            self._log(f"Error: {e}", ACCENT_RED)

    # -- Recording --

    def _toggle_recording(self):
        global is_recording, audio_data

        if is_recording:
            # Stop recording
            is_recording = False
            self._stop_timer()
            self.rec_btn.configure(
                text="⏳  Comprimiendo y subiendo...",
                bg=BTN_IDLE_BG, fg=MUTED_COLOR, state="disabled",
            )
            self._set_status("Procesando...", ACCENT_YELLOW)
            self._log("Grabación detenida. Procesando...", ACCENT_YELLOW)
            
            # Show and start progress bar
            self._show_progress(True)
            self._processing = True
            
            def progress_callback(value):
                self.after(0, lambda: self._update_progress(value, f"Procesando... {value}%"))
            
            threading.Thread(
                target=procesar_grabacion,
                args=(self._log, self._on_processing_done, progress_callback),
                daemon=True,
            ).start()
        else:
            # Start recording
            is_recording = True
            audio_data = []
            self._recording_seconds = 0

            self.rec_btn.configure(
                text="⏹  Detener grabación",
                bg=ACCENT_RED, fg="#1e1e2e",
                activebackground="#d55f7a",
            )
            self.rec_btn.unbind("<Enter>")
            self.rec_btn.unbind("<Leave>")
            self._set_status("GRABANDO", ACCENT_RED)
            self._start_pulse_animation()
            self._start_timer()
            self._log("Grabación iniciada.", ACCENT_RED)
            threading.Thread(target=record_audio, args=(self._log,), daemon=True).start()

    def _on_processing_done(self):
        def _reset():
            self._show_progress(False)
            self._processing = False
            self.rec_btn.configure(text="⏺  Iniciar grabación", bg=BTN_IDLE_BG, fg=TEXT_COLOR, state="normal")
            self._bind_hover(self.rec_btn, BTN_HOVER_BG, BTN_IDLE_BG)
            self.timer_label.configure(text="")
            self._set_status("Listo para grabar", ACCENT_GREEN)
        self.after(0, _reset)

    def _start_timer(self):
        self._recording_seconds = 0
        self._update_timer()

    def _update_timer(self):
        if not is_recording:
            return
        m, s = divmod(self._recording_seconds, 60)
        h, m = divmod(m, 60)
        self.timer_label.configure(
            text=f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}",
            fg=ACCENT_RED,
        )
        self._recording_seconds += 1
        self._timer_id = self.after(1000, self._update_timer)

    def _stop_timer(self):
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None

    def _start_pulse_animation(self):
        """Inicia la animación de pulso en el indicador de grabación."""
        if not is_recording:
            self.dot_canvas.itemconfig(self.dot, fill=ACCENT_GREEN)
            self.dot_canvas.itemconfig(self.dot_outer, outline=ACCENT_GREEN)
            return
        
        # Pulse animation - alternate between sizes
        current_width = self.dot_canvas.itemcget(self.dot_outer, "width")
        new_width = "3" if current_width == "0" else "0"
        self.dot_canvas.itemconfig(self.dot_outer, width=new_width)
        
        # Also pulse the fill color
        cur = self.dot_canvas.itemcget(self.dot, "fill")
        new_color = CARD_BG if cur == ACCENT_RED else ACCENT_RED
        self.dot_canvas.itemconfig(self.dot, fill=new_color)
        
        self.after(400, self._start_pulse_animation)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    App().mainloop()
