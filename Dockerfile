# Imagen para desplegar en Railway (o cualquier hosting con contenedores).
FROM python:3.12-slim

# Evita archivos .pyc y deja los prints salir en tiempo real al log de Railway
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# gosu permite arrancar como root (para ajustar los permisos del volumen, que se
# monta después de construir la imagen) y bajar a un usuario sin privilegios antes
# de ejecutar la aplicación.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Las dependencias se instalan antes de copiar el código, para que Railway
# reutilice esta capa en cada despliegue y compile mucho más rápido.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# La base de datos y la configuración van en /data, que debe ser un volumen de
# Railway. Sin volumen, el disco del contenedor se borra en cada despliegue y se
# perderían las reservas importadas.
ENV HOTEL_DATA_DIR=/data \
    HOTEL_ABRIR_NAVEGADOR=0

RUN useradd --create-home --uid 10001 hotel \
    && mkdir -p /data \
    && chown -R hotel:hotel /data /app

WORKDIR /app/backend

# El entrypoint corrige el dueño del volumen y baja a 'hotel' antes de arrancar:
# si alguien lograra ejecutar algo dentro del contenedor, no sería root.
ENTRYPOINT ["docker-entrypoint.sh"]

# Railway inyecta PORT; launcher.py lo respeta y crea la base si no existe.
CMD ["python", "launcher.py"]
