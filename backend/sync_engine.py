"""
Sincronización automática Sierpe <-> Drake.

Modelo: cada estación tiene su propia base de datos local (SQLite) y funciona
100% offline. Cuando hay conexión, esta estación intenta conectarse a la otra
(peer_url configurado) e intercambia los cambios pendientes (sync_log).

Resolución de conflictos: "last write wins" por tabla+registro, comparando el
timestamp de creado_en de cada cambio.
"""
import json
import os
import secrets
import time
import threading
import urllib.request
import urllib.error
from fastapi import HTTPException
from init_db import get_connection

CONFIG_PATH = os.path.join(
    os.environ.get("HOTEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data"),
    "sync_config.json",
)

# Secreto compartido entre las dos estaciones. Los endpoints /api/sync/pending y
# /api/sync/apply no llevan sesión de usuario (los usa la otra máquina, no una
# persona), así que sin este token quedaban abiertos: cualquiera podía leer todas
# las reservas o escribir en la base. Si no está definido, se apagan.
SYNC_TOKEN = (os.environ.get("HOTEL_SYNC_TOKEN") or "").strip()


def exigir_token(recibido):
    if not SYNC_TOKEN:
        raise HTTPException(status_code=404,
                            detail="La sincronización entre estaciones no está habilitada")
    if not recibido or not secrets.compare_digest(recibido, SYNC_TOKEN):
        raise HTTPException(status_code=401, detail="Token de sincronización inválido")

TABLAS_SINCRONIZABLES = {
    "reserva": "conf_no",
    "tour_asignado": "id",
    "entrada_sinac": "id",
    "grupo": "id",
    "huesped": "id",
}


def load_sync_config():
    if not os.path.exists(CONFIG_PATH):
        return {"nombre_estacion": "Sierpe", "peer_url": ""}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sync_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def ensure_station_name(conn, nombre):
    conn.execute(
        "INSERT INTO config_estacion (clave, valor) VALUES ('nombre_estacion', ?) "
        "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
        (nombre,),
    )
    conn.commit()


def get_pending_changes(conn, origen_local):
    """Devuelve los cambios locales (de esta estación) aún no marcados como sincronizados,
    con el contenido completo del registro para poder aplicarlo remotamente."""
    rows = conn.execute(
        "SELECT * FROM sync_log WHERE sincronizado = 0 AND origen_estacion = ? ORDER BY version",
        (origen_local,),
    ).fetchall()
    changes = []
    for row in rows:
        tabla, pk_col = row["tabla"], TABLAS_SINCRONIZABLES.get(row["tabla"])
        if not pk_col:
            continue
        record = conn.execute(
            f"SELECT * FROM {tabla} WHERE {pk_col} = ?", (row["registro_id"],)
        ).fetchone()
        if record:
            changes.append({
                "log_id": row["id"], "tabla": tabla, "registro_id": row["registro_id"],
                "accion": row["accion"], "creado_en": row["creado_en"],
                "data": dict(record),
            })
    return changes


def apply_remote_changes(conn, changes):
    """Aplica cambios recibidos de la otra estación usando last-write-wins."""
    aplicados = 0
    for ch in changes:
        tabla, pk_col = ch["tabla"], TABLAS_SINCRONIZABLES.get(ch["tabla"])
        if not pk_col:
            continue
        data = ch["data"]
        local = conn.execute(
            f"SELECT * FROM {tabla} WHERE {pk_col} = ?", (ch["registro_id"],)
        ).fetchone()
        if local:
            local_ts = conn.execute(
                "SELECT MAX(creado_en) t FROM sync_log WHERE tabla=? AND registro_id=?",
                (tabla, str(ch["registro_id"])),
            ).fetchone()["t"]
            if local_ts and local_ts >= ch["creado_en"]:
                continue  # el registro local es más reciente o igual: no se sobreescribe
        cols = [c for c in data.keys() if c != pk_col]
        set_clause = ", ".join(f"{c} = ?" for c in cols)
        values = [data[c] for c in cols]
        if local:
            conn.execute(f"UPDATE {tabla} SET {set_clause} WHERE {pk_col} = ?", values + [ch["registro_id"]])
        else:
            all_cols = list(data.keys())
            placeholders = ", ".join("?" for _ in all_cols)
            conn.execute(f"INSERT INTO {tabla} ({', '.join(all_cols)}) VALUES ({placeholders})", list(data.values()))
        # El trigger de la tabla acaba de crear una entrada en sync_log para este registro
        # (como si fuera un cambio local nuevo). Como en realidad es un dato que ya viene
        # sincronizado desde la otra estación, se marca de una vez como sincronizado para
        # evitar un ciclo de ida y vuelta infinito entre las dos estaciones.
        conn.execute(
            "UPDATE sync_log SET sincronizado = 1 WHERE tabla = ? AND registro_id = ? AND sincronizado = 0",
            (tabla, str(ch["registro_id"])),
        )
        aplicados += 1
    conn.commit()
    return aplicados


def mark_synced(conn, log_ids):
    if not log_ids:
        return
    conn.execute(
        f"UPDATE sync_log SET sincronizado = 1 WHERE id IN ({','.join('?' for _ in log_ids)})",
        log_ids,
    )
    conn.commit()


def http_post_json(url, payload, timeout=5):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "X-Sync-Token": SYNC_TOKEN},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_json(url, timeout=5):
    req = urllib.request.Request(url, headers={"X-Sync-Token": SYNC_TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def intentar_sincronizar():
    """Un ciclo de sincronización: si hay peer configurado y responde, intercambia cambios.
    Si no hay señal o el peer no responde, no falla — simplemente no sincroniza esta vez."""
    cfg = load_sync_config()
    peer = cfg.get("peer_url", "").strip()
    resultado = {"estado": "SIN_PEER_CONFIGURADO", "enviados": 0, "recibidos": 0}
    if not peer:
        return resultado
    if not SYNC_TOKEN:
        return {"estado": "SIN_TOKEN", "enviados": 0, "recibidos": 0,
                "mensaje": "Define HOTEL_SYNC_TOKEN (el mismo valor en ambas estaciones)."}

    conn = get_connection()
    try:
        mis_cambios = get_pending_changes(conn, cfg["nombre_estacion"])
        remotos = http_get_json(f"{peer}/api/sync/pending", timeout=5)
        recibidos = apply_remote_changes(conn, remotos.get("changes", []))

        if mis_cambios:
            http_post_json(f"{peer}/api/sync/apply", {"changes": mis_cambios}, timeout=5)
            mark_synced(conn, [c["log_id"] for c in mis_cambios])

        resultado = {"estado": "OK", "enviados": len(mis_cambios), "recibidos": recibidos}
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        resultado = {"estado": "SIN_CONEXION", "enviados": 0, "recibidos": 0}
    finally:
        conn.close()
    return resultado


def sync_loop(intervalo_segundos=30):
    """Hilo en segundo plano: intenta sincronizar cada N segundos, sin bloquear la app
    ni mostrar errores si no hay conexión (offline-first)."""
    while True:
        try:
            intentar_sincronizar()
        except Exception:
            pass
        time.sleep(intervalo_segundos)


def iniciar_sync_en_segundo_plano():
    hilo = threading.Thread(target=sync_loop, daemon=True)
    hilo.start()
    return hilo


if __name__ == "__main__":
    conn = get_connection()
    ensure_station_name(conn, "Sierpe")
    conn.close()
    print("Estación configurada como Sierpe.")
    print(intentar_sincronizar())
