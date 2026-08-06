#!/bin/sh
# Arranca como root solo para dejar el volumen escribible y baja de inmediato a un
# usuario sin privilegios.
#
# Hace falta porque el volumen de Railway se monta SOBRE /data despues de construir
# la imagen: el chown del Dockerfile queda tapado y el volumen recien creado
# pertenece a root. Sin este paso, el proceso no podria crear hotel.db.
set -e

DATA_DIR="${HOTEL_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"
chown -R hotel:hotel "$DATA_DIR" 2>/dev/null || true

exec gosu hotel "$@"
