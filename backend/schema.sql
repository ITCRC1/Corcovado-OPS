-- Usuarios del sistema y control de acceso por rol
CREATE TABLE IF NOT EXISTS usuario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    nombre_completo TEXT NOT NULL,
    rol TEXT NOT NULL, -- 'recepcion' (lectura/escritura) | 'gerencia' (solo lectura) | 'staff' (solo lectura)
    -- Permisos por pantalla. JSON del tipo {"restaurantes":"escribir","resumen":"ver"}.
    -- Si viene NULL se usan los permisos del rol, para no romper los usuarios ya creados.
    permisos_json TEXT,
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sesion (
    token TEXT PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuario(id),
    creado_en TEXT DEFAULT (datetime('now'))
);

-- ============================================================
-- Sistema de Operación Hotelera - Sierpe / Drake
-- Esquema de base de datos (SQLite)
-- ============================================================

-- Catálogo de tours (reglas fijas: horario, capacidad por guía, si requiere entrada SINAC)
CREATE TABLE IF NOT EXISTS tour_catalogo (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    horario_inicio TEXT,
    horario_fin TEXT,
    horario_alterno_inicio TEXT,
    horario_alterno_fin TEXT,
    max_pax_guia INTEGER NOT NULL,
    requiere_entrada_sinac INTEGER NOT NULL DEFAULT 0,
    requiere_bote INTEGER NOT NULL DEFAULT 0,  -- las caminatas y actividades en el lodge no llevan bote
    es_privado INTEGER NOT NULL DEFAULT 0,
    tour_base TEXT, -- si es privado, referencia al tour normal equivalente
    activo INTEGER NOT NULL DEFAULT 1
);

-- Catálogo de botes
CREATE TABLE IF NOT EXISTS bote (
    nombre TEXT PRIMARY KEY,
    capacidad_max INTEGER, -- NULL para Privado/Externo (no gestionado por el hotel)
    gestionado_por_hotel INTEGER NOT NULL DEFAULT 1,
    activo INTEGER NOT NULL DEFAULT 1
);

-- Catálogo de guías
CREATE TABLE IF NOT EXISTS guia (
    nombre TEXT PRIMARY KEY,
    es_externo INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1
);

-- Catálogo de amenidades y su tarea automática asociada
CREATE TABLE IF NOT EXISTS amenidad_catalogo (
    nombre TEXT PRIMARY KEY,
    tarea_automatica TEXT NOT NULL,
    area_responsable TEXT NOT NULL
);

-- Grupos (vinculación entre reservas)
CREATE TABLE IF NOT EXISTS grupo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conf_no_principal TEXT,
    origen_vinculo TEXT, -- 'texto_explicito' | 'coincidencia_nombre' | 'manual'
    confianza TEXT, -- 'ALTA' | 'MEDIA'
    confirmado_por_recepcion INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT DEFAULT (datetime('now'))
);

-- Reservas
CREATE TABLE IF NOT EXISTS reserva (
    conf_no TEXT PRIMARY KEY,
    grupo_id INTEGER REFERENCES grupo(id),
    room_no TEXT,
    nombre_principal TEXT,
    company_travel_agent TEXT,
    arr_date TEXT NOT NULL,
    dep_date TEXT,
    arr_time TEXT,
    room_type TEXT,
    adl INTEGER DEFAULT 0,
    chl INTEGER DEFAULT 0,
    rooms INTEGER DEFAULT 1,
    mkt_code TEXT,
    src_code TEXT,
    res_status TEXT, -- CKIN | POR INGRESAR | EN CASA | SALIO | CANCELADA
    vip INTEGER DEFAULT 0,
    guia_sugerido TEXT,
    guia_confirmado INTEGER NOT NULL DEFAULT 0,
    punto_entrada TEXT, -- Sierpe | Drake
    punto_salida TEXT,
    punto_entrada_sin_confirmar TEXT,
    punto_salida_sin_confirmar TEXT,
    -- Código de bloque del PMS (ej. 2608RUSSTI). Sirve para agrupar reservas que
    -- viajan juntas y que no traen la nota "viene con rsv".
    block_code TEXT,
    -- Restaurante fijo para toda la estadía, si recepción lo define
    forzar_restaurante TEXT,
    hora_vuelo_entrada TEXT,
    hora_vuelo_salida TEXT,
    vuelo_entrada TEXT,
    vuelo_salida TEXT,
    nota_ingreso TEXT,
    nota_en_casa TEXT,
    nota_salida TEXT,
    notas_operacion TEXT,  -- notas en texto libre que aparecen tras el itinerario
    notas_libres TEXT,
    fuente_pdf TEXT,
    actualizado_en TEXT DEFAULT (datetime('now'))
);

-- Huéspedes (rooming list)
CREATE TABLE IF NOT EXISTS huesped (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conf_no TEXT REFERENCES reserva(conf_no),
    nombre_completo TEXT NOT NULL,
    pasaporte TEXT,
    nacionalidad TEXT
);

-- Tours asignados (agenda real, día por día)
CREATE TABLE IF NOT EXISTS tour_asignado (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conf_no TEXT REFERENCES reserva(conf_no),
    fecha TEXT NOT NULL,
    tour_codigo TEXT REFERENCES tour_catalogo(codigo),
    bote_nombre TEXT REFERENCES bote(nombre),
    guia_nombre TEXT REFERENCES guia(nombre),
    pax INTEGER NOT NULL DEFAULT 1,
    conf_entrada_sinac TEXT, -- número de confirmación (si aplica)
    es_cambio_ultimo_momento INTEGER NOT NULL DEFAULT 0,
    -- Cuando un tour excede la capacidad de un guía o bote, se divide en grupos
    -- separados (A, B, C...), cada uno con su propio guía y bote. Si el tour no
    -- está dividido, grupo_operativo queda como 'A' por defecto.
    grupo_operativo TEXT NOT NULL DEFAULT 'A',
    dividido_de_id INTEGER,  -- id del registro original del que se dividió
    creado_en TEXT DEFAULT (datetime('now'))
);

-- Entradas SINAC (deduplicadas por tour+fecha+conf_entrada)
CREATE TABLE IF NOT EXISTS entrada_sinac (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tour_codigo TEXT REFERENCES tour_catalogo(codigo),
    fecha TEXT NOT NULL,
    conf_entrada TEXT,
    pax_total_grupo INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'SIN_COMPRAR', -- SIN_COMPRAR | COMPRADA | VER_NOTA
    nota TEXT,
    UNIQUE(tour_codigo, fecha, conf_entrada)
);

-- Tareas generadas por amenidades
CREATE TABLE IF NOT EXISTS amenidad_tarea (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conf_no TEXT REFERENCES reserva(conf_no),
    -- Sin clave foránea: además de las amenidades del catálogo (detectadas del PDF),
    -- recepción puede agregar requerimientos libres del huésped (alergias que llegan
    -- por teléfono, preferencias, peticiones especiales).
    amenidad TEXT,
    origen TEXT NOT NULL DEFAULT 'PDF',  -- 'PDF' | 'MANUAL'
    detalle TEXT,
    tarea TEXT NOT NULL,
    area_responsable TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE', -- PENDIENTE | HECHA
    -- Noche concreta a la que aplica, en formato ISO. La usa la cena privada: el PDF
    -- avisa que existe pero casi nunca dice el día, así que recepción lo confirma
    -- desde la pantalla de restaurantes.
    fecha TEXT,
    creado_en TEXT DEFAULT (datetime('now'))
);

-- Alertas de cambios de último momento
CREATE TABLE IF NOT EXISTS alerta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL, -- 'CAMBIO_ULTIMO_MOMENTO' | 'CAPACIDAD_BOTE' | 'CAPACIDAD_GUIA' | 'ENTRADA_SINAC_VENCE'
    referencia_id INTEGER,
    mensaje TEXT NOT NULL,
    resuelto INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT DEFAULT (datetime('now'))
);

-- Itinerario de bienvenida de cada reserva.
-- Se genera automáticamente al importar el PDF y recepción puede editarlo libremente.
-- Las filas se guardan como JSON para permitir agregar, quitar y reordenar sin
-- restricciones, que es lo que necesita recepción para cambios de último momento.
CREATE TABLE IF NOT EXISTS itinerario (
    conf_no TEXT PRIMARY KEY REFERENCES reserva(conf_no),
    nombre_bienvenida TEXT,
    filas_json TEXT NOT NULL,
    editado INTEGER NOT NULL DEFAULT 0,   -- 1 si recepción lo modificó a mano
    idioma TEXT NOT NULL DEFAULT 'en',   -- idioma en que se entrega al huésped
    aviso_cambios TEXT,                   -- si la reserva cambió tras la edición
    actualizado_en TEXT DEFAULT (datetime('now'))
);

-- Código fijo de cada habitación para su enlace público.
-- Se genera UNA sola vez y nunca cambia: es lo que hace que el código QR impreso
-- siga sirviendo para siempre, aunque cambie el huésped. El código aleatorio evita
-- que alguien adivine el enlace de otra habitación probando números.
CREATE TABLE IF NOT EXISTS habitacion_qr (
    room_no TEXT PRIMARY KEY,
    token TEXT NOT NULL,
    creado_en TEXT DEFAULT (datetime('now'))
);

-- Registro de publicaciones del sitio de itinerarios
CREATE TABLE IF NOT EXISTS publicacion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estado TEXT NOT NULL,          -- 'PENDIENTE' | 'PUBLICADO' | 'ERROR'
    detalle TEXT,
    habitaciones INTEGER,
    intentos INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT DEFAULT (datetime('now')),
    publicado_en TEXT
);

-- Qué se publicó de cada habitación, para saber si su contenido cambió desde la
-- última publicación (y así avisar cuáles quedan pendientes de publicar).
CREATE TABLE IF NOT EXISTS publicacion_habitacion (
    room_no TEXT PRIMARY KEY,
    conf_no TEXT,                  -- huésped que estaba publicado
    huella TEXT,                   -- huella del contenido publicado
    publicado_en TEXT
);

-- ---------------------------------------------------------------------------
-- Distribución de restaurantes
-- ---------------------------------------------------------------------------

-- Cambios manuales de restaurante. Solo se guarda la EXCEPCIÓN: el resto se
-- calcula al vuelo con las reglas. Afecta una sola fecha y una sola reserva.
CREATE TABLE IF NOT EXISTS restaurante_cambio (
    fecha TEXT NOT NULL,
    conf_no TEXT NOT NULL,
    comida TEXT NOT NULL,          -- 'ALMUERZO' | 'CENA'
    restaurante TEXT NOT NULL,     -- 'Terra Kitchen' | 'Bar el Bosque'
    motivo TEXT,
    creado_en TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (fecha, conf_no, comida),
    FOREIGN KEY (conf_no) REFERENCES reserva(conf_no) ON DELETE CASCADE
);

-- Asignación de los días que ya pasaron. Se congela al terminar el día para que
-- el historial de rotación no se reescriba cuando entra un PDF nuevo, y para que
-- una deuda de cena en Terra Kitchen no desaparezca sola.
CREATE TABLE IF NOT EXISTS restaurante_historico (
    fecha TEXT NOT NULL,
    conf_no TEXT NOT NULL,
    almuerzo TEXT,
    cena TEXT,
    era_entrada INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (fecha, conf_no)
);

-- Hora reservada de cada mesa para la cena. La registra el salonero.
CREATE TABLE IF NOT EXISTS restaurante_hora (
    fecha TEXT NOT NULL,
    conf_no TEXT NOT NULL,
    hora TEXT,
    PRIMARY KEY (fecha, conf_no)
);

-- Log de sincronización (para el modelo offline-first Sierpe/Drake)
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tabla TEXT NOT NULL,
    registro_id TEXT NOT NULL,
    accion TEXT NOT NULL, -- INSERT | UPDATE | DELETE
    origen_estacion TEXT, -- 'Sierpe' | 'Drake'
    version INTEGER NOT NULL,
    sincronizado INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT DEFAULT (datetime('now'))
);

-- Configuración local de esta instalación (estación, contador de versión)
CREATE TABLE IF NOT EXISTS config_estacion (
    clave TEXT PRIMARY KEY,
    valor TEXT
);

-- ============================================================
-- Triggers: cada cambio en las tablas sincronizables se anota
-- automáticamente en sync_log, usando el nombre de estación
-- guardado en config_estacion (clave 'nombre_estacion').
-- ============================================================
CREATE TRIGGER IF NOT EXISTS trg_huesped_insert AFTER INSERT ON huesped
BEGIN
    INSERT INTO sync_log (tabla, registro_id, accion, origen_estacion, version)
    VALUES ('huesped', NEW.id, 'INSERT',
            (SELECT valor FROM config_estacion WHERE clave='nombre_estacion'),
            (SELECT COALESCE(MAX(version),0)+1 FROM sync_log));
END;

CREATE TRIGGER IF NOT EXISTS trg_reserva_insert AFTER INSERT ON reserva
BEGIN
    INSERT INTO sync_log (tabla, registro_id, accion, origen_estacion, version)
    VALUES ('reserva', NEW.conf_no, 'INSERT',
            (SELECT valor FROM config_estacion WHERE clave='nombre_estacion'),
            (SELECT COALESCE(MAX(version),0)+1 FROM sync_log));
END;

CREATE TRIGGER IF NOT EXISTS trg_reserva_update AFTER UPDATE ON reserva
BEGIN
    INSERT INTO sync_log (tabla, registro_id, accion, origen_estacion, version)
    VALUES ('reserva', NEW.conf_no, 'UPDATE',
            (SELECT valor FROM config_estacion WHERE clave='nombre_estacion'),
            (SELECT COALESCE(MAX(version),0)+1 FROM sync_log));
END;

CREATE TRIGGER IF NOT EXISTS trg_tour_asignado_insert AFTER INSERT ON tour_asignado
BEGIN
    INSERT INTO sync_log (tabla, registro_id, accion, origen_estacion, version)
    VALUES ('tour_asignado', NEW.id, 'INSERT',
            (SELECT valor FROM config_estacion WHERE clave='nombre_estacion'),
            (SELECT COALESCE(MAX(version),0)+1 FROM sync_log));
END;

CREATE TRIGGER IF NOT EXISTS trg_tour_asignado_update AFTER UPDATE ON tour_asignado
BEGIN
    INSERT INTO sync_log (tabla, registro_id, accion, origen_estacion, version)
    VALUES ('tour_asignado', NEW.id, 'UPDATE',
            (SELECT valor FROM config_estacion WHERE clave='nombre_estacion'),
            (SELECT COALESCE(MAX(version),0)+1 FROM sync_log));
END;

CREATE TRIGGER IF NOT EXISTS trg_entrada_sinac_insert AFTER INSERT ON entrada_sinac
BEGIN
    INSERT INTO sync_log (tabla, registro_id, accion, origen_estacion, version)
    VALUES ('entrada_sinac', NEW.id, 'INSERT',
            (SELECT valor FROM config_estacion WHERE clave='nombre_estacion'),
            (SELECT COALESCE(MAX(version),0)+1 FROM sync_log));
END;

CREATE TRIGGER IF NOT EXISTS trg_entrada_sinac_update AFTER UPDATE ON entrada_sinac
BEGIN
    INSERT INTO sync_log (tabla, registro_id, accion, origen_estacion, version)
    VALUES ('entrada_sinac', NEW.id, 'UPDATE',
            (SELECT valor FROM config_estacion WHERE clave='nombre_estacion'),
            (SELECT COALESCE(MAX(version),0)+1 FROM sync_log));
END;

CREATE TRIGGER IF NOT EXISTS trg_grupo_insert AFTER INSERT ON grupo
BEGIN
    INSERT INTO sync_log (tabla, registro_id, accion, origen_estacion, version)
    VALUES ('grupo', NEW.id, 'INSERT',
            (SELECT valor FROM config_estacion WHERE clave='nombre_estacion'),
            (SELECT COALESCE(MAX(version),0)+1 FROM sync_log));
END;

CREATE TRIGGER IF NOT EXISTS trg_grupo_update AFTER UPDATE ON grupo
BEGIN
    INSERT INTO sync_log (tabla, registro_id, accion, origen_estacion, version)
    VALUES ('grupo', NEW.id, 'UPDATE',
            (SELECT valor FROM config_estacion WHERE clave='nombre_estacion'),
            (SELECT COALESCE(MAX(version),0)+1 FROM sync_log));
END;
