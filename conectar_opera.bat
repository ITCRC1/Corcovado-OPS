@echo off
REM Conecta el sistema con Opera Cloud para dejar de importar el PDF a mano.
REM
REM La PRIMERA vez deja un archivo listo para rellenar con las credenciales que dio
REM Oracle, y dice donde esta. Se rellena con el Bloc de notas y se vuelve a correr.
REM
REM No guarda nada en la base: solo comprueba y muestra que entraria.
cd /d "%~dp0backend"
python conectar_opera.py %1
echo.
pause
