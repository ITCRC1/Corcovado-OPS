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


def main():
    # Toda la información que debe sobrevivir a un reinicio vive en esta carpeta.
    # En Railway apunta al volumen montado en /data; en una computadora, a la
    # carpeta data/ junto al programa.
    data_dir = os.environ.get("HOTEL_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(data_dir, exist_ok=True)
    os.environ["HOTEL_DATA_DIR"] = data_dir

    import uvicorn
    import init_db
    init_db.init_db(reset=False)  # crea la BD y carga el catálogo si es la primera vez
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
