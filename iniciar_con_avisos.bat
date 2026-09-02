@echo off
REM YA NO HACE FALTA ESTE ARCHIVO: iniciar.bat trae los avisos encendidos.
REM
REM Antes las notificaciones estaban apagadas hasta que alguien pusiera dos llaves a
REM mano en las variables del servidor. Ahora el sistema se las genera solo la primera
REM vez que arranca y las guarda en data\llaves_avisos.json.
REM
REM Se deja este archivo para no romperle el atajo a nadie: arranca el sistema normal.
REM
REM PARA PROBARLOS EN ESTA COMPUTADORA: entra por http://localhost:8000
REM   El navegador solo da notificaciones por conexion segura, y localhost cuenta como
REM   segura. La notificacion aparece en ESTA computadora, no en el telefono.
REM
REM PARA QUE LLEGUEN A UN TELEFONO: hace falta la direccion de internet del hotel
REM   (https). Con la direccion de esta computadora (192.168.x.x) el navegador del
REM   telefono no registra nada y el boton de activar no puede funcionar.
echo.
echo Los avisos ya vienen encendidos en iniciar.bat: arrancando el sistema normal.
echo Entra por http://localhost:8000 -- NO por la direccion de red (192.168.x.x):
echo el navegador solo da notificaciones por conexion segura.
echo.
cd /d "%~dp0"
call iniciar.bat
