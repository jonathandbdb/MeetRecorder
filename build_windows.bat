@echo off
REM ===================================================
REM MeetRec — Build script para Windows
REM Genera: dist\MeetRec\MeetRec.exe
REM ===================================================

echo.
echo ========================================
echo   MeetRec - Build Windows
echo ========================================
echo.

REM 1. Verificar entorno virtual
if not exist "venv" (
    echo [1/5] Creando entorno virtual...
    python -m venv venv
) else (
    echo [1/5] Entorno virtual existente.
)

call venv\Scripts\activate.bat

REM 2. Instalar dependencias
echo [2/5] Instalando dependencias...
pip install -r requirements.txt -q

REM 3. Instalar PyInstaller
echo [3/5] Instalando PyInstaller...
pip install pyinstaller -q

REM 4. Instalar Playwright (solo lib, no browsers)
echo [4/5] Instalando Playwright...
pip install playwright -q

REM 5. Build
echo [5/5] Construyendo ejecutable...
pyinstaller meetrec.spec --noconfirm

echo.
if exist "dist\MeetRec\MeetRec.exe" (
    echo ========================================
    echo   BUILD EXITOSO!
    echo   dist\MeetRec\MeetRec.exe
    echo ========================================
    echo.
    echo NOTA: Para distribuir, copia la carpeta
    echo dist\MeetRec\ completa.
    echo.
    echo Requisitos del usuario final:
    echo   - Google Chrome instalado
    echo   - ffmpeg en PATH (o copiar ffmpeg.exe
    echo     dentro de dist\MeetRec\ffmpeg\)
    echo   - Playwright browsers: ejecutar una vez
    echo     dist\MeetRec\MeetRec.exe --install-pw
    echo     (o instalar playwright browsers aparte)
) else (
    echo ========================================
    echo   ERROR: Build fallido.
    echo   Revisa los errores arriba.
    echo ========================================
)

echo.
pause
