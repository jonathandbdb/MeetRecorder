#!/usr/bin/env bash
# ===================================================
# MeetRec — Build script para Linux (Ubuntu/Debian)
# Genera: dist/MeetRec/MeetRec
#
# Uso:
#   chmod +x build_linux.sh
#   ./build_linux.sh
#
# Requisitos mínimos: Ubuntu 20.04+ / Debian 11+
# El script instala automáticamente las dependencias
# que falten (requiere sudo para paquetes de sistema).
# ===================================================

set -euo pipefail

PYTHON_MIN="3.8"
VENV_DIR="venv"

# ---------------------------------------------------
# Colores para output
# ---------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # Sin color

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
echo "========================================"
echo "  MeetRec — Build Linux"
echo "========================================"
echo ""

# ---------------------------------------------------
# 1. Verificar Python mínimo
# ---------------------------------------------------
info "Verificando Python..."

if ! command -v python3 &>/dev/null; then
    error "python3 no encontrado. Instalá Python 3.8+ antes de continuar."
    exit 1
fi

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_OK=$(python3 -c "import sys; print(1 if sys.version_info >= (3,8) else 0)")

if [ "$PYTHON_OK" -eq 0 ]; then
    error "Se requiere Python >= $PYTHON_MIN (actual: $PYTHON_VER)"
    exit 1
fi

info "Python $PYTHON_VER ✓"

# ---------------------------------------------------
# 2. Instalar dependencias del sistema (apt)
# ---------------------------------------------------
info "Verificando dependencias del sistema..."

# Paquetes necesarios para compilar las dependencias de Python y para runtime
APT_PACKAGES=(
    python3-venv       # venv
    python3-dev        # headers para compilar C extensions
    python3-tk         # tkinter (GUI)
    libpulse-dev       # PulseAudio headers (soundcard)
    libasound2-dev     # ALSA headers (soundcard)
    libsndfile1-dev    # libsndfile (soundfile)
    ffmpeg             # Compresión audio
    build-essential    # gcc, make, etc.
)

MISSING_PKGS=()
for pkg in "${APT_PACKAGES[@]}"; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        MISSING_PKGS+=("$pkg")
    fi
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    warn "Faltan paquetes: ${MISSING_PKGS[*]}"
    info "Instalando con apt..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq "${MISSING_PKGS[@]}"
    info "Dependencias del sistema instaladas ✓"
else
    info "Todas las dependencias del sistema presentes ✓"
fi

# ---------------------------------------------------
# 3. Crear/activar entorno virtual
# ---------------------------------------------------
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    if [ -d "$VENV_DIR" ]; then
        warn "Entorno virtual corrupto, recreando..."
        rm -rf "$VENV_DIR"
    fi
    info "Creando entorno virtual..."
    python3 -m venv "$VENV_DIR"
else
    info "Entorno virtual existente."
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Entorno virtual activado ($(python3 --version))"

# ---------------------------------------------------
# 4. Instalar dependencias de Python
# ---------------------------------------------------
info "Instalando dependencias de Python..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
info "Dependencias de Python instaladas ✓"

# ---------------------------------------------------
# 5. Instalar navegadores de Playwright
# ---------------------------------------------------
info "Instalando navegadores de Playwright (Chromium)..."
playwright install chromium --with-deps 2>/dev/null || python3 -m playwright install chromium --with-deps 2>/dev/null || true
info "Playwright configurado ✓"

# ---------------------------------------------------
# 6. Build con PyInstaller
# ---------------------------------------------------
info "Construyendo ejecutable con PyInstaller..."
pyinstaller meetrec.spec --noconfirm

echo ""
if [ -f "dist/MeetRec/MeetRec" ]; then
    echo "========================================"
    echo -e "  ${GREEN}BUILD EXITOSO!${NC}"
    echo "  dist/MeetRec/MeetRec"
    echo "========================================"
    echo ""
    echo "Para distribuir, copiá la carpeta dist/MeetRec/ completa."
    echo ""
    echo "Requisitos del usuario final:"
    echo "  - Google Chrome instalado"
    echo "  - ffmpeg en PATH (o copiar binario"
    echo "    dentro de dist/MeetRec/ffmpeg/)"
    echo "  - Playwright browsers: ejecutar una vez"
    echo "    dist/MeetRec/MeetRec --install-pw"
    echo ""
else
    echo "========================================"
    error "Build fallido. Revisá los errores arriba."
    echo "========================================"
    exit 1
fi
