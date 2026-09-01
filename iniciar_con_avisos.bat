@echo off
REM Arranca el sistema con los AVISOS AL CELULAR encendidos, para probarlos.
REM
REM iniciar.bat arranca el sistema normal, SIN avisos: las llaves viven en las variables
REM del servidor y en una computadora no estan puestas, asi que la pantalla de Amenidades
REM dice "no estan configurados". Este archivo genera unas llaves de prueba y las usa.
REM
REM Los datos van en data-avisos\, aparte de la base real.
cd /d "%~dp0"
python probar_avisos.py
pause
