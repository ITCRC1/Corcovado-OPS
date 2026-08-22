"""
Inicializa la base de datos SQLite y carga el catálogo de reglas de negocio
definido en el Documento de Requerimientos (tours, botes, guías, amenidades).
"""
import sqlite3
import os

_data_dir = os.environ.get("HOTEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data")
_resource_dir = os.environ.get("HOTEL_RESOURCE_DIR") or os.path.dirname(__file__)
DB_PATH = os.path.join(_data_dir, "hotel.db")
SCHEMA_PATH = os.path.join(_resource_dir, "schema.sql")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


TOURS = [
    # codigo, nombre, h_ini, h_fin, h_alt_ini, h_alt_fin, max_pax_guia, requiere_entrada, requiere_bote, es_privado, tour_base
    ("BALLENAS", "Ballenas", "08:00", "12:00", None, None, 8, 0, 1, 0, None),
    ("BUCEO", "Buceo", "07:15", "12:30", None, None, 6, 1, 1, 0, None),
    ("BUCEO PRIVADO", "Buceo privado", "07:15", "12:30", None, None, 6, 1, 1, 1, "BUCEO"),
    ("CABALGATA", "Cabalgata", "07:30", "11:30", "14:00", "16:30", 6, 0, 0, 0, None),
    ("GTT", "GTT", "15:00", "17:00", None, None, 6, 0, 0, 0, None),
    ("ISLA", "Isla", "07:15", "12:30", None, None, 8, 1, 1, 0, None),
    ("ISLA PRIVADO", "Isla privado", "07:15", "12:30", None, None, 8, 1, 1, 1, "ISLA"),
    ("MANGLAR", "Manglar", "06:30", "13:00", None, None, 7, 0, 1, 0, None),
    ("NW", "NW", "17:45", "19:45", None, None, 4, 0, 0, 0, None),
    ("PAJAREO", "Pajareo", "06:00", "08:00", None, None, 6, 0, 0, 0, None),
    ("PAJAREO PRIVADO", "Pajareo privado", "06:00", "08:00", None, None, 6, 0, 0, 1, "PAJAREO"),
    ("PESCA", "Pesca (medio día)", "08:00", "12:00", None, None, 6, 0, 1, 0, None),
    ("PNC", "PNC", "07:30", "12:30", None, None, 8, 1, 1, 0, None),
    ("PNC PRIVADO", "PNC privado", "07:30", "12:30", None, None, 8, 1, 1, 1, "PNC"),
    ("SIRENA", "Sirena", "06:15", "13:30", None, None, 8, 1, 1, 0, None),
    ("SNORKEL", "Snorkel", "07:15", "12:30", None, None, 8, 1, 1, 0, None),
    # Actividades en el lodge: no llevan bote ni entrada al SINAC. El horario es
    # variable (lo coordina recepción), así que se deja sin hora fija y el
    # itinerario del huésped lo pide completar.
    ("CLARO", "Claro del Bosque", None, None, None, None, 10, 0, 0, 0, None),
    ("SPA", "Spa / Masajes", None, None, None, None, 20, 0, 0, 0, None),
    ("TREENET", "Treenet", "16:00", "18:00", None, None, 4, 0, 0, 0, None),
]

BOTES = [
    ("CHULIN", 13, 1),
    ("COATI", 10, 1),
    ("TIBURON", 20, 1),
    ("TAMANDUA", 8, 1),
    ("PRIVADO", None, 0),
    ("EXTERNO", None, 0),
]

GUIAS = [
    ("DIEGO", 0), ("JOSE", 0), ("RAFA", 0), ("STEVEN", 0),
    ("TIBI", 0), ("JOHAN", 0), ("EXTERNO", 1),
]

AMENIDADES = [
    ("Cena privada", "Notificar a cocina/servicio para coordinar montaje y menú", "Cocina/Servicio"),
    ("Decoración por cumpleaños", "Notificar a housekeeping para preparar decoración en la habitación", "Housekeeping"),
    ("Luna de miel / cliente VIP", "Marcar reserva como VIP en el dashboard + notificar a gerencia/recepción", "Gerencia/Recepción"),
    ("Botella de vino cortesía", "Notificar a bar/bodega para dejarla en la habitación antes del check-in", "Bar/Bodega"),
    ("Frutas de cortesía", "Notificar a cocina para preparar canasta antes del check-in", "Cocina"),
    ("Tarjeta de bienvenida", "Notificar a recepción para colocarla antes del check-in", "Recepción"),
    ("Frutas con chocolate cortesía", "Notificar a cocina para preparar antes del check-in", "Cocina"),
    ("Sofá cama extra", "Notificar a housekeeping para armar la habitación con anticipación", "Housekeeping"),
    ("Restricción alimentaria / alergia", "AVISAR A COCINA antes del check-in — revisar el detalle en la reserva", "Cocina"),
    ("Requerimiento de movilidad / accesibilidad", "Coordinar habitación accesible y apoyo en traslados", "Recepción/Operaciones"),
    ("Cuna / bebé", "Notificar a housekeeping para colocar cuna en la habitación", "Housekeeping"),
]


# Columnas agregadas después de que el sistema ya estaba en uso. El esquema se crea
# con CREATE TABLE IF NOT EXISTS, así que en una base que ya existe estas columnas
# NO aparecen solas: hay que agregarlas explícitamente. Sin esto fallan al importar
# el PDF, al abrir Restaurantes y al guardar permisos.
COLUMNAS_NUEVAS = [
    ("reserva", "block_code", "TEXT"),
    ("reserva", "forzar_restaurante", "TEXT"),
    ("usuario", "permisos_json", "TEXT"),
    ("amenidad_tarea", "fecha", "TEXT"),
]


def _migrar(conn):
    """Agrega las columnas que falten. Es idempotente: se puede correr siempre."""
    agregadas = []
    for tabla, columna, tipo in COLUMNAS_NUEVAS:
        existentes = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})")}
        if not existentes:
            continue          # la tabla aún no existe; el esquema ya la creará con la columna
        if columna not in existentes:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
            agregadas.append(f"{tabla}.{columna}")
    if agregadas:
        conn.commit()
        print("Base actualizada, columnas agregadas: " + ", ".join(agregadas))
    _renombrar_restaurante(conn, "Vitrales", "Bar el Bosque")
    return agregadas


# Dónde quedó guardado el nombre del restaurante. Son los tres lugares donde el
# sistema lo escribe como texto, no como referencia a un catálogo.
CAMPOS_CON_RESTAURANTE = [
    ("restaurante_cambio", "restaurante"),      # cambios manuales de una fecha
    ("restaurante_historico", "cena"),          # histórico congelado de la rotación
    ("restaurante_historico", "almuerzo"),
    ("reserva", "forzar_restaurante"),          # restaurante fijo de toda la estadía
]


def _renombrar_restaurante(conn, viejo, nuevo):
    """Pasa al nombre nuevo los datos que quedaron guardados con el anterior.

    El nombre del restaurante se guarda como texto en el histórico de rotación, en los
    cambios manuales y en el restaurante fijo de estadía. Si solo se cambiara el nombre
    en el código, esas filas dejarían de coincidir: la rotación perdería el historial,
    los cambios manuales dejarían de aplicarse y una cena de bienvenida pendiente
    desaparecería sin que nadie se enterara.

    Es idempotente: corre en cada arranque y no hace nada cuando ya no queda nada
    con el nombre viejo.
    """
    cambiadas = 0
    for tabla, columna in CAMPOS_CON_RESTAURANTE:
        existentes = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})")}
        if columna not in existentes:
            continue
        cur = conn.execute(
            f"UPDATE {tabla} SET {columna} = ? WHERE {columna} = ?", (nuevo, viejo))
        cambiadas += cur.rowcount or 0
    if cambiadas:
        conn.commit()
        print(f"Restaurante renombrado: «{viejo}» → «{nuevo}» en {cambiadas} registro(s)")
    return cambiadas


def init_db(reset=False):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    _migrar(conn)

    cur = conn.cursor()

    cur.executemany(
        """INSERT OR IGNORE INTO tour_catalogo
           (codigo, nombre, horario_inicio, horario_fin, horario_alterno_inicio,
            horario_alterno_fin, max_pax_guia, requiere_entrada_sinac, requiere_bote,
            es_privado, tour_base)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        TOURS,
    )
    cur.executemany(
        "INSERT OR IGNORE INTO bote (nombre, capacidad_max, gestionado_por_hotel) VALUES (?,?,?)",
        BOTES,
    )
    cur.executemany(
        "INSERT OR IGNORE INTO guia (nombre, es_externo) VALUES (?,?)",
        GUIAS,
    )
    cur.executemany(
        "INSERT OR IGNORE INTO amenidad_catalogo (nombre, tarea_automatica, area_responsable) VALUES (?,?,?)",
        AMENIDADES,
    )

    conn.commit()
    conn.close()
    print(f"Base de datos inicializada en {DB_PATH}")
    print(f"Catálogo cargado: {len(TOURS)} tours, {len(BOTES)} botes, {len(GUIAS)} guías, {len(AMENIDADES)} amenidades")


if __name__ == "__main__":
    init_db(reset=True)
