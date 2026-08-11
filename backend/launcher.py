"""
Punto de entrada del sistema.

Crea la base de datos si no existe, registra las rutas de la API y levanta el
servidor. Sirve igual en la nube (Railway) que en una computadora del lodge.
"""
import os
import time
import threading
import webbrowser


def open_browser_delayed(url, delay=1.5):
    time.sleep(delay)
    webbrowser.open(url)


def _diagnostico_almacenamiento(data_dir, db_existia, init_db):
    """Deja escrito en el log si los datos están sobreviviendo a los despliegues."""
    try:
        conn = init_db.get_connection()
        reservas = conn.execute("SELECT COUNT(*) c FROM reserva").fetchone()["c"]
        usuarios = conn.execute("SELECT COUNT(*) c FROM usuario").fetchone()["c"]
        conn.close()
    except Exception as e:
        print(f"AVISO: no se pudo leer la base para el diagnostico: {e}")
        return

    print("-" * 62)
    print(f" Carpeta de datos: {data_dir}")
    if db_existia:
        print(f" Base ENCONTRADA. Reservas: {reservas} · Usuarios: {usuarios}")
        print(" El almacenamiento esta conservando los datos entre despliegues.")
    else:
        print(" Base NUEVA (no habia hotel.db en esa carpeta).")
        print("")
        print(" Si es el primer arranque, es lo normal.")
        print(" Si YA habia cargado reservas, entonces esos datos se perdieron:")
        print(" la carpeta no es un volumen persistente. Revisa en Railway que el")
        print(" servicio tenga un volumen montado exactamente en la ruta de arriba.")
    print("-" * 62)


def main():
    # Toda la información que debe sobrevivir a un reinicio vive en esta carpeta.
    # En Railway apunta al volumen montado en /data; en una computadora, a la
    # carpeta data/ junto al programa.
    data_dir = os.environ.get("HOTEL_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(data_dir, exist_ok=True)
    os.environ["HOTEL_DATA_DIR"] = data_dir

    # Si el archivo ya existía, el almacenamiento está conservando los datos entre
    # despliegues. Si no, o falta el volumen, o está montado en otra ruta: el
    # contenedor escribe igual, pero en disco temporal que se borra al redesplegar.
    # Sin este aviso, la única señal era que un día el sistema aparecía vacío.
    db_existia = os.path.exists(os.path.join(data_dir, "hotel.db"))

    import uvicorn
    import init_db
    init_db.init_db(reset=False)  # crea la BD y carga el catálogo si es la primera vez
    _diagnostico_almacenamiento(data_dir, db_existia, init_db)
    import main as backend_main  # noqa: F401  (registra las rutas de la API)

    # Configuración por variables de entorno, para poder instalarlo en cualquier
    # servidor sin tocar el código:
    #   PORT / HOTEL_PORT      puerto (por defecto 8000). Railway inyecta PORT.
    #   HOTEL_HOST             dirección de escucha (por defecto 0.0.0.0)
    #   HOTEL_ABRIR_NAVEGADOR  poner en 0 en un servidor sin pantalla
    puerto = int(os.environ.get("PORT") or os.environ.get("HOTEL_PORT") or "8000")
    escucha = os.environ.get("HOTEL_HOST", "0.0.0.0")

    # En un servidor no hay navegador que abrir ni tiene sentido anunciar una IP
    # de red local: la dirección pública la asigna el hosting.
    en_servidor = bool(os.environ.get("RAILWAY_ENVIRONMENT")
                       or os.environ.get("RAILWAY_ENVIRONMENT_NAME")
                       or os.environ.get("HOTEL_ENTORNO"))
    abrir_navegador = os.environ.get("HOTEL_ABRIR_NAVEGADOR",
                                     "0" if en_servidor else "1") != "0"

    if en_servidor:
        print(f"Sistema de Operacion Hotelera escuchando en el puerto {puerto}")
        print(f"Datos en: {data_dir}")
    else:
        if abrir_navegador:
            threading.Thread(target=open_browser_delayed,
                             args=(f"http://localhost:{puerto}",), daemon=True).start()
        print("=" * 58)
        print(" Sistema de Operacion Hotelera - Corcovado Wilderness Lodge")
        print("=" * 58)
        print(f" Abre el navegador en:  http://localhost:{puerto}")
        print(" Para cerrar el programa, cierra esta ventana.")
        print("=" * 58)

    # proxy_headers: detras del proxy de Railway, para que la IP del cliente que
    # se usa al frenar los intentos de login sea la real y no la del proxy.
    uvicorn.run(backend_main.app, host=escucha, port=puerto, log_level="warning",
                proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
