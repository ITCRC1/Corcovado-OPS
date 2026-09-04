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


_wal_puesto = False


def get_connection():
    global _wal_puesto
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    # El modo WAL queda escrito en el propio archivo de la base: se pone UNA vez y
    # sobrevive a los reinicios. Antes se pedía en cada conexión —y hay unas 170 por
    # ronda de pantalla—, y cada una tomaba un bloqueo momentáneo del archivo para
    # confirmar algo que ya estaba puesto.
    if not _wal_puesto:
        conn.execute("PRAGMA journal_mode = WAL")
        _wal_puesto = True
    # Caché de páginas por conexión (16 MB). Es lo que evita volver al disco al recorrer
    # la misma tabla varias veces dentro de una sola petición.
    conn.execute("PRAGMA cache_size = -16000")
    # Los ORDER BY y los GROUP BY grandes se resuelven en memoria en vez de escribir
    # un archivo temporal en el volumen.
    conn.execute("PRAGMA temp_store = MEMORY")
    # Con WAL, NORMAL no espera a que el disco confirme cada commit. Un corte de luz
    # del servidor puede costar las últimas transacciones; una caída del programa, no
    # (el WAL se recupera igual). Es el ajuste recomendado para WAL y el que más rinde
    # al importar un PDF, que son cientos de escrituras seguidas.
    conn.execute("PRAGMA synchronous = NORMAL")
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


# Los tratamientos del spa, con los nombres y las duraciones EXACTAS del formulario que
# el spa ya le manda al huésped. Se siembran para que el sistema arranque con lo que ya
# se ofrece, y son editables desde el Catálogo: la duración, el nombre y "Promo of the
# week" cambian sin tocar código.
#
# (codigo, nombre, minutos, tipo, orden)
SERVICIOS_SPA = [
    ("DEEP",    "Deep Connection",    90, "MASAJE", 1),
    ("PACHA",   "Pachamama Touch",    60, "MASAJE", 2),
    ("FRESH",   "Fresh Soul",         90, "MASAJE", 3),
    ("FLORA",   "Flora Experience",   60, "FACIAL", 4),
    ("OCEAN",   "Ocean Breeze",       60, "MASAJE", 5),
    ("RAIN",    "Rainforest Delight", 60, "MASAJE", 6),
    ("JUNGLE",  "Jungle Bliss",       40, "MASAJE", 7),
    ("SOUL",    "Soul and Body",      30, "MASAJE", 8),
    ("PROMO",   "Promo of the week",  60, "OTRO",   9),
]

# Las dos terapeutas. Sin nombre todavía: se editan desde el Catálogo. Se siembran para
# que la agenda pueda repartir citas desde el primer día sin tener que configurar nada.
TERAPEUTAS_SPA = [("Terapeuta 1",), ("Terapeuta 2",)]


# Columnas agregadas después de que el sistema ya estaba en uso. El esquema se crea
# con CREATE TABLE IF NOT EXISTS, así que en una base que ya existe estas columnas
# NO aparecen solas: hay que agregarlas explícitamente. Sin esto fallan al importar
# el PDF, al abrir Restaurantes y al guardar permisos.
COLUMNAS_NUEVAS = [
    ("reserva", "block_code", "TEXT"),
    ("reserva", "forzar_restaurante", "TEXT"),
    ("usuario", "permisos_json", "TEXT"),
    ("amenidad_tarea", "fecha", "TEXT"),
    ("reserva", "regimen", "TEXT"),
    # Las dos que protegen el trabajo hecho a mano de la siguiente importación del PDF.
    # Ver los comentarios en schema.sql y en loader.py.
    ("amenidad_tarea", "editado_a_mano", "INTEGER NOT NULL DEFAULT 0"),
    ("tour_asignado", "origen", "TEXT NOT NULL DEFAULT 'PDF'"),
    # La marca de modificación de Opera, para no reprocesar lo que no cambió.
    ("reserva", "opera_modificado_en", "TEXT"),
]


# ---------------------------------------------------------------------------
# Índices
# ---------------------------------------------------------------------------
# La base no tenía ninguno (solo el UNIQUE de entrada_sinac, que está por corrección
# y no por velocidad), así que cada consulta por fecha, por reserva o por habitación
# leía la tabla entera. No se nota con pocos datos: se nota cada mes que pasa.
#
# Van aquí y no en schema.sql porque schema.sql se ejecuta con CREATE TABLE IF NOT
# EXISTS y no vuelve a correr sobre una base que ya existe; esto sí corre en cada
# arranque, así que una base vieja también los recibe.


def _iso_de(columna):
    """La expresión con que el sistema reordena 'DD-MM-YY' a 'YY-MM-DD' para comparar.

    TIENE que ser idéntica, carácter por carácter, a la que generan main.sql_fecha() y
    qr_huesped.sql_fecha(): SQLite solo usa un índice por expresión cuando la consulta
    trae exactamente la misma expresión. Si alguien cambia una de las dos, el índice
    deja de servir en silencio y todo vuelve a escanear la tabla.
    """
    return (f"(substr({columna},7,2)||'-'||substr({columna},4,2)"
            f"||'-'||substr({columna},1,2))")


INDICES = [
    # --- reserva ---
    # Igualdad exacta sobre el texto 'DD-MM-YY': quién entra y quién sale ese día.
    ("idx_reserva_arr_date", "CREATE INDEX IF NOT EXISTS idx_reserva_arr_date ON reserva (arr_date)"),
    ("idx_reserva_dep_date", "CREATE INDEX IF NOT EXISTS idx_reserva_dep_date ON reserva (dep_date)"),
    # Rangos de fechas. Sin estos, pedir un mes de reservas recorre toda la historia.
    ("idx_reserva_arr_iso",
     f"CREATE INDEX IF NOT EXISTS idx_reserva_arr_iso ON reserva ({_iso_de('arr_date')})"),
    ("idx_reserva_dep_iso",
     f"CREATE INDEX IF NOT EXISTS idx_reserva_dep_iso ON reserva ({_iso_de('dep_date')})"),
    # El que más se usa de todos: la página del huésped busca "quién ocupa esta
    # habitación hoy" y se consulta una vez por habitación en cada carga.
    ("idx_reserva_room_arr",
     f"CREATE INDEX IF NOT EXISTS idx_reserva_room_arr ON reserva (room_no, {_iso_de('arr_date')})"),
    ("idx_reserva_grupo", "CREATE INDEX IF NOT EXISTS idx_reserva_grupo ON reserva (grupo_id)"),
    # --- tours ---
    ("idx_tour_asig_fecha", "CREATE INDEX IF NOT EXISTS idx_tour_asig_fecha ON tour_asignado (fecha)"),
    ("idx_tour_asig_conf", "CREATE INDEX IF NOT EXISTS idx_tour_asig_conf ON tour_asignado (conf_no)"),
    ("idx_tour_asig_tour_fecha",
     "CREATE INDEX IF NOT EXISTS idx_tour_asig_tour_fecha ON tour_asignado (tour_codigo, fecha)"),
    # --- el resto de los JOIN por número de reserva ---
    ("idx_huesped_conf", "CREATE INDEX IF NOT EXISTS idx_huesped_conf ON huesped (conf_no)"),
    ("idx_amenidad_conf", "CREATE INDEX IF NOT EXISTS idx_amenidad_conf ON amenidad_tarea (conf_no)"),
    ("idx_amenidad_fecha", "CREATE INDEX IF NOT EXISTS idx_amenidad_fecha ON amenidad_tarea (fecha)"),
    ("idx_amenidad_estado", "CREATE INDEX IF NOT EXISTS idx_amenidad_estado ON amenidad_tarea (estado)"),
    # Por área: es como agrupa la pantalla de Amenidades y como filtra el resumen las
    # restricciones de cocina. La clave primaria (amenidad_id, area) ya sirve para buscar
    # las áreas DE una amenidad; esto sirve para el camino contrario.
    ("idx_amenidad_area_area",
     "CREATE INDEX IF NOT EXISTS idx_amenidad_area_area ON amenidad_area (area)"),
    ("idx_entrada_sinac_fecha", "CREATE INDEX IF NOT EXISTS idx_entrada_sinac_fecha ON entrada_sinac (fecha)"),
    ("idx_alerta_resuelto", "CREATE INDEX IF NOT EXISTS idx_alerta_resuelto ON alerta (resuelto)"),
    ("idx_sugerencia_estado",
     "CREATE INDEX IF NOT EXISTS idx_sugerencia_estado ON sugerencia_grupo (estado)"),
    # --- sync_log ---
    # Los nueve disparadores de schema.sql hacen 'SELECT MAX(version) FROM sync_log' en
    # CADA alta y CADA modificación. Sin índice eso recorre la tabla, y sync_log no se
    # purga nunca: importar un PDF era más lento cada mes. Medido: 48 veces más rápido.
    ("idx_sync_log_version", "CREATE INDEX IF NOT EXISTS idx_sync_log_version ON sync_log (version)"),
    ("idx_sync_log_pendiente",
     "CREATE INDEX IF NOT EXISTS idx_sync_log_pendiente ON sync_log (sincronizado)"),
    # No se indexa restaurante_historico(fecha): su clave primaria (fecha, conf_no) ya
    # sirve las consultas por fecha. Un índice más ahí solo costaría escrituras.
]


def _crear_indices(conn):
    """Crea los índices que falten. Idempotente, y no puede impedir el arranque.

    Cada índice va por separado a propósito: si uno falla —una versión de SQLite sin
    índices por expresión, una tabla que todavía no existe— se anota y se sigue con los
    demás. Un sistema sin un índice va lento; un sistema que no arranca no sirve.
    """
    creados, fallos = [], []
    existentes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index'")}
    for nombre, sql in INDICES:
        if nombre in existentes:
            continue
        try:
            conn.execute(sql)
            creados.append(nombre)
        except sqlite3.Error as e:
            fallos.append(f"{nombre} ({e})")
    if creados:
        conn.commit()
        # Con los índices recién puestos, el planificador todavía no sabe cuántas filas
        # hay en cada uno. ANALYZE se lo dice, y solo se paga cuando se crearon.
        try:
            conn.execute("ANALYZE")
            conn.commit()
        except sqlite3.Error:
            pass
        print(f"Índices creados: {len(creados)} ({', '.join(creados)})")
    if fallos:
        print("AVISO: no se pudieron crear estos índices: " + "; ".join(fallos))
    return creados


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
    _materializar_permisos(conn)
    # Después de materializar: primero se le da rejilla a quien no la tenga, y luego se
    # le agregan a todos las pantallas nuevas. En ese orden, un usuario recién creado no
    # pasa dos veces por lo mismo.
    _pantallas_nuevas_a_las_rejillas(conn)
    _sembrar_perfiles(conn)
    _arreglar_entradas_sinac(conn)
    _sembrar_areas_de_amenidades(conn)
    _limpiar_grupos_sueltos(conn)
    _purgar_sesiones(conn)
    # Al final, con las tablas ya creadas y los duplicados ya limpios.
    _crear_indices(conn)
    return agregadas


def _sembrar_areas_de_amenidades(conn):
    """Le da a cada amenidad existente su fila en amenidad_area.

    Las amenidades de antes tenían un solo departamento, guardado en
    amenidad_tarea.area_responsable. Se copia tal cual, con su estado, para que sigan
    comportándose EXACTAMENTE igual: un solo área, un solo estado.

    Se corre en cada arranque y solo toca las que no tengan ninguna fila. Así una base
    vieja se pone al día sola, y las que ya se migraron no se vuelven a tocar.

    Un requerimiento SIN filas de área sería invisible para todos los departamentos, y
    eso es una tarea perdida. Por eso esto corre siempre y no una sola vez.
    """
    if not {r[1] for r in conn.execute("PRAGMA table_info(amenidad_area)")}:
        return 0
    if not {r[1] for r in conn.execute("PRAGMA table_info(amenidad_tarea)")}:
        return 0
    cur = conn.execute(
        """INSERT OR IGNORE INTO amenidad_area (amenidad_id, area, estado)
           SELECT a.id, a.area_responsable, a.estado
           FROM amenidad_tarea a
           WHERE a.area_responsable IS NOT NULL AND TRIM(a.area_responsable) != ''
             AND NOT EXISTS (SELECT 1 FROM amenidad_area x WHERE x.amenidad_id = a.id)""")
    n = cur.rowcount or 0
    if n:
        conn.commit()
        print(f"Departamentos de amenidades sembrados: {n}")
    return n


def _limpiar_grupos_sueltos(conn):
    """Grupos de una sola habitación, que no son grupos.

    Los creaba la importación al leer 'Viene con rsv 594008465': le ponía el grupo a la
    reserva que TRAÍA la nota y no a la nombrada, así que quedaba un grupo de uno solo
    que ninguna pantalla mostraba —piden dos habitaciones o más—. Ahora esos vínculos se
    proponen y los confirma recepción, así que estos restos solo estorban.

    Se tocan únicamente los que nadie confirmó: si recepción ya dijo que sí, se respeta
    aunque haya quedado con una sola habitación (la otra pudo cancelarse).
    """
    if not {r[1] for r in conn.execute("PRAGMA table_info(grupo)")}:
        return 0
    sueltos = [r[0] for r in conn.execute(
        """SELECT g.id FROM grupo g
           WHERE g.confirmado_por_recepcion = 0
             AND (SELECT COUNT(*) FROM reserva r WHERE r.grupo_id = g.id) < 2""")]
    for gid in sueltos:
        conn.execute("UPDATE reserva SET grupo_id = NULL WHERE grupo_id = ?", (gid,))
        conn.execute("DELETE FROM grupo WHERE id = ?", (gid,))
    if sueltos:
        conn.commit()
        print(f"Grupos de una sola habitación eliminados: {len(sueltos)}")
    return len(sueltos)


def _arreglar_entradas_sinac(conn):
    """Quita las entradas del SINAC duplicadas y evita que vuelvan a aparecer.

    La tabla declaraba UNIQUE(tour_codigo, fecha, conf_entrada), pero en SQLite dos
    valores NULL NO se consideran iguales. Y justamente las entradas pendientes de
    comprar son las que no tienen número de confirmación: cada vez que se reimportaba
    el reporte de llegadas se insertaba otra copia de cada una.

    Se corrige en dos pasos:
      1. Se juntan las que ya están duplicadas, conservando la comprada si hay alguna
         —una entrada ya pagada no se puede perder— y el pax más alto registrado.
      2. Se crea un índice único que trata la ausencia de número como un valor más,
         así la base misma impide que vuelva a pasar.

    El índice se crea aquí y no en el esquema a propósito: en una base que ya tiene
    duplicados, crearlo antes de limpiarlos falla y el sistema no arrancaría.
    """
    existentes = {r[1] for r in conn.execute("PRAGMA table_info(entrada_sinac)")}
    if not existentes:
        return 0

    grupos_dup = conn.execute(
        """SELECT tour_codigo, fecha, IFNULL(conf_entrada,'') AS conf, COUNT(*) AS n
           FROM entrada_sinac
           GROUP BY tour_codigo, fecha, IFNULL(conf_entrada,'')
           HAVING n > 1""").fetchall()

    borradas = 0
    for g in grupos_dup:
        filas = conn.execute(
            """SELECT id, estado, pax_total_grupo, nota FROM entrada_sinac
               WHERE tour_codigo = ? AND fecha = ? AND IFNULL(conf_entrada,'') = ?
               ORDER BY id""", (g["tour_codigo"], g["fecha"], g["conf"])).fetchall()
        # Se conserva la comprada si existe; si no, la más antigua (su id es la que
        # referencian los avisos y el botón de marcar).
        compradas = [f for f in filas if f["estado"] == "COMPRADA"]
        queda = (compradas or filas)[0]
        pax = max((f["pax_total_grupo"] or 0) for f in filas)
        nota = next((f["nota"] for f in filas if f["nota"]), None)
        conn.execute("UPDATE entrada_sinac SET pax_total_grupo = ?, nota = ? WHERE id = ?",
                     (pax, nota, queda["id"]))
        for f in filas:
            if f["id"] != queda["id"]:
                conn.execute("DELETE FROM entrada_sinac WHERE id = ?", (f["id"],))
                borradas += 1

    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_entrada_sinac_unica
           ON entrada_sinac (tour_codigo, fecha, IFNULL(conf_entrada, ''))""")

    # Y las que quedaron sin dueño se limpian aquí también, no solo al importar un PDF:
    # las que ya están en la base tienen que desaparecer al arrancar, sin obligar a
    # nadie a volver a subir el reporte para que la pantalla se vea bien.
    import sinac
    sin_duenio, anotadas = sinac.limpiar_huerfanas(conn)

    conn.commit()
    if borradas:
        print(f"Entradas SINAC duplicadas unificadas: se quitaron {borradas}")
    if sin_duenio or anotadas:
        print(f"Entradas SINAC sin reservas: {sin_duenio} borradas, {anotadas} anotadas")
    return borradas


def _materializar_permisos(conn):
    """Escribe en cada usuario los permisos que hoy le da su rol.

    El rol deja de otorgar permisos y pasa a ser solo una etiqueta: manda lo que está
    en la rejilla de cada usuario. Para que nadie pierda ni gane acceso el día del
    cambio, aquí se copia tal cual lo que su rol le daba hasta ahora.

    Es idempotente: solo toca a quien no tenga rejilla propia. Si mañana se crea un
    usuario a mano en la base sin permisos, este paso le pone los de su rol.
    """
    import json as _json
    try:
        import auth
    except ImportError:
        return 0
    filas = conn.execute(
        "SELECT id, rol FROM usuario WHERE permisos_json IS NULL OR permisos_json = ''"
    ).fetchall()
    if not filas:
        return 0
    for f in filas:
        permisos = auth.POR_ROL.get(f["rol"]) or auth.POR_ROL["staff"]
        conn.execute("UPDATE usuario SET permisos_json = ? WHERE id = ?",
                     (_json.dumps(permisos, ensure_ascii=False), f["id"]))
    conn.commit()
    print(f"Permisos materializados desde el rol en {len(filas)} usuario(s)")
    return len(filas)


def _meta(conn, clave, valor=None):
    """Lee o escribe un dato que el propio sistema necesita recordar entre arranques."""
    if valor is None:
        fila = conn.execute("SELECT valor FROM sistema_meta WHERE clave = ?",
                            (clave,)).fetchone()
        return dict(fila)["valor"] if fila else None
    conn.execute(
        "INSERT INTO sistema_meta (clave, valor) VALUES (?,?) "
        "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (clave, valor))
    conn.commit()
    return valor


def _pantallas_nuevas_a_las_rejillas(conn):
    """Le agrega a cada usuario las pantallas NUEVAS del sistema, al nivel de su rol.

    EL PROBLEMA QUE RESUELVE, que pasó de verdad: al agregar la pantalla del Spa, el
    sistema se desplegó bien pero el botón no le aparecía a nadie y las rutas del spa
    respondían 403. La razón es que _materializar_permisos solo le pone la rejilla a
    quien NO la tiene, y en una instalación que lleva meses corriendo todos la tienen.
    La pantalla nueva quedaba fuera de la rejilla de todos, y una pantalla que no está
    en la rejilla es una pantalla que no existe.

    Se veía como "el despliegue no funcionó", que es lo peor: manda a buscar el problema
    donde no está.

    POR QUÉ HACE FALTA RECORDAR QUÉ PANTALLAS HABÍA. Sin eso, "está en el sistema y no
    en la rejilla" es ambiguo: puede ser una pantalla nueva, o una que alguien le quitó
    a ese usuario a propósito. Devolverle un acceso que se le quitó es peor que no
    agregarle uno nuevo. Con la lista guardada, solo se agregan las que de verdad son
    nuevas desde el último arranque.

    Se respeta el rol: solo se agrega lo que POR_ROL le daría. Así el staff de campo no
    recibe pantallas que su rol nunca le dio.
    """
    import json as _json
    try:
        import auth
    except ImportError:
        return 0
    if not {r[1] for r in conn.execute("PRAGMA table_info(sistema_meta)")}:
        return 0

    actuales = [k for k, _ in auth.PANTALLAS]
    guardadas = _meta(conn, "pantallas_conocidas")
    if guardadas:
        try:
            conocidas = _json.loads(guardadas)
        except ValueError:
            conocidas = []
        nuevas = [p for p in actuales if p not in conocidas]
    else:
        # Primera vez con este mecanismo: no hay lista anterior, así que se completa lo
        # que le falte a cada rejilla según el rol. Es el caso de la instalación que ya
        # está corriendo, y es lo que hace aparecer la pantalla del Spa.
        nuevas = actuales

    if not nuevas:
        return 0

    tocados = 0
    for u in conn.execute(
            "SELECT id, rol, permisos_json FROM usuario "
            "WHERE permisos_json IS NOT NULL AND permisos_json != ''").fetchall():
        try:
            rejilla = _json.loads(dict(u)["permisos_json"])
        except ValueError:
            continue
        if not isinstance(rejilla, dict):
            continue
        del_rol = auth.POR_ROL.get(u["rol"]) or {}
        agregadas = []
        for p in nuevas:
            # Nunca se toca lo que ya está: ni para dar más ni para quitar.
            if p not in rejilla and p in del_rol:
                rejilla[p] = del_rol[p]
                agregadas.append(p)
        if agregadas:
            conn.execute("UPDATE usuario SET permisos_json = ? WHERE id = ?",
                         (_json.dumps(rejilla, ensure_ascii=False), u["id"]))
            tocados += 1

    if tocados:
        conn.commit()
        print(f"Pantallas nuevas agregadas a la rejilla de {tocados} usuario(s): "
              f"{', '.join(nuevas)}")
    _meta(conn, "pantallas_conocidas", _json.dumps(actuales))
    return tocados


def _purgar_sesiones(conn):
    """Quita las sesiones vencidas al arrancar. No hace nada si nadie encendió el
    vencimiento (HOTEL_SESION_HORAS), que es el caso por omisión."""
    try:
        import auth
    except ImportError:
        return 0
    if not {r[1] for r in conn.execute("PRAGMA table_info(sesion)")}:
        return 0          # la tabla aún no existe
    return auth.purgar_sesiones_vencidas(conn)


def _sembrar_perfiles(conn):
    """Deja los perfiles sugeridos como punto de partida, sin pisar los del hotel."""
    import json as _json
    try:
        import auth
    except ImportError:
        return
    for nombre, permisos in auth.PERFILES.items():
        conn.execute(
            "INSERT OR IGNORE INTO perfil_permisos (nombre, permisos_json) VALUES (?,?)",
            (nombre, _json.dumps(permisos, ensure_ascii=False)))
    conn.commit()


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
    cur.executemany(
        """INSERT OR IGNORE INTO spa_servicio (codigo, nombre, minutos, tipo, orden)
           VALUES (?,?,?,?,?)""",
        SERVICIOS_SPA,
    )
    cur.executemany(
        "INSERT OR IGNORE INTO spa_terapeuta (nombre) VALUES (?)",
        TERAPEUTAS_SPA,
    )

    conn.commit()
    conn.close()
    print(f"Base de datos inicializada en {DB_PATH}")
    print(f"Catálogo cargado: {len(TOURS)} tours, {len(BOTES)} botes, {len(GUIAS)} guías, "
          f"{len(AMENIDADES)} amenidades, {len(SERVICIOS_SPA)} servicios de spa")


if __name__ == "__main__":
    init_db(reset=True)
