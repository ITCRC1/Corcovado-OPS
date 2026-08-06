@echo off
echo ============================================
echo Sistema de Operacion Hotelera - Sierpe/Drake
echo ============================================
cd /d "%~dp0backend"

if not exist "..\data\hotel.db" (
    echo Inicializando base de datos por primera vez...
    python init_db.py
    python loader.py
)

echo.
echo Iniciando servidor local...
echo Abre tu navegador en: http://localhost:8000
echo (Para detener el programa, cierra esta ventana)
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
