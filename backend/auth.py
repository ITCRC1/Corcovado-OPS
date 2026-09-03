"""
Autenticación por usuario y control de permisos por rol.

Roles:
- recepcion: lectura y escritura (puede editar todo)
- gerencia:  solo lectura (dashboards, reportes, analítica)
- staff:     solo lectura (resúmenes del día)
"""
import hashlib
import os
import secrets
from fastapi import Header, HTTPException

PBKDF2_ITERATIONS = 200_000


# ---------------------------------------------------------------------------
# Vencimiento de la sesión
# ---------------------------------------------------------------------------
# Hasta ahora un token no vencía nunca: se guardaba al ingresar y valía hasta que
# alguien apretara "salir". El manual decía que caducaba a las 12 horas y documentaba
# esta variable, pero nadie la leía.
#
# Ahora la variable existe de verdad, y viene APAGADA: sin definirla, las sesiones se
# comportan exactamente como siempre. Se enciende cuando el hotel quiera, poniendo
# HOTEL_SESION_HORAS en el servidor.
#
# Se deja apagada a propósito en vez de fijar 12 horas: encenderla cierra la sesión a
# quien esté a media tarea, y ese plazo hay que elegirlo pensando en el turno del
# personal —un turno de recepción que empieza a las 6 y termina a las 18 no aguanta un
# vencimiento de 8 horas— no en lo que decía el manual.

def _horas_de_sesion():
    """Cuántas horas vale un token. 0 significa que no vence, como funcionó siempre.

    Un valor mal escrito no impide arrancar: se avisa en el registro y se queda apagado.
    Dejar al hotel sin poder entrar por un error de tecleo en una variable sería peor
    que no tener vencimiento.
    """
    crudo = (os.environ.get("HOTEL_SESION_HORAS") or "").strip()
    if not crudo:
        return 0
    try:
        horas = int(crudo)
    except ValueError:
        print(f"AVISO: HOTEL_SESION_HORAS='{crudo}' no es un número entero de horas. "
              "Las sesiones seguirán sin vencer.")
        return 0
    if horas <= 0:
        return 0
    return horas


SESION_HORAS = _horas_de_sesion()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return h.hex(), salt


def verify_password(password, password_hash, salt):
    h, _ = hash_password(password, salt)
    return secrets.compare_digest(h, password_hash)


def seed_default_users(conn):
    """Crea las cuentas iniciales, y SOLO si no hay ninguna todavía.

    En un sistema que ya tiene usuarios esto no hace nada: las cuentas y contraseñas
    existentes no se tocan nunca.

    La contraseña ya no se deduce del nombre ("recepcion2026"). Eso era predecible, y
    además estaba escrito en el código y publicado en la pantalla de ingreso, así que
    cualquiera que abriera la dirección tenía una cuenta válida. Ahora:

      · Si se define HOTEL_ADMIN_PASSWORD, se usa esa para las cuentas iniciales.
        Sirve para fijarla desde las variables del servidor.
      · Si no, se genera una al azar y se imprime UNA vez en el registro de arranque.
        Hay que leerla ahí para el primer ingreso, y cambiarla desde Usuarios.
    """
    existentes = conn.execute("SELECT COUNT(*) c FROM usuario").fetchone()["c"]
    if existentes > 0:
        return None
    fijada = os.environ.get("HOTEL_ADMIN_PASSWORD")
    clave = fijada or secrets.token_urlsafe(9)
    defaults = [
        ("recepcion", clave, "Recepción", "recepcion"),
        ("gerencia", clave, "Gerencia", "gerencia"),
        ("staff", clave, "Staff de campo", "staff"),
    ]
    import json as _json
    for username, password, nombre, rol in defaults:
        h, salt = hash_password(password)
        # Los permisos se escriben aquí mismo. El rol ya no otorga nada por sí solo, y
        # esta siembra corre DESPUÉS de la migración que rellena a los que no tienen
        # rejilla, así que un usuario creado sin permisos se quedaría sin poder entrar
        # a ninguna pantalla.
        conn.execute(
            """INSERT INTO usuario (username, password_hash, salt, nombre_completo, rol, permisos_json)
               VALUES (?,?,?,?,?,?)""",
            (username, h, salt, nombre, rol,
             _json.dumps(POR_ROL.get(rol, POR_ROL["staff"]), ensure_ascii=False)),
        )
    conn.commit()
    if fijada:
        print("Cuentas iniciales creadas con la contraseña de HOTEL_ADMIN_PASSWORD.")
    else:
        print("\n" + "=" * 66)
        print("  CUENTAS INICIALES CREADAS — esta contraseña se muestra UNA sola vez")
        print(f"     usuario: recepcion   contraseña: {clave}")
        print("  Entra con ella y cámbiala desde la pantalla de Usuarios.")
        print("  ('gerencia' y 'staff' se crearon con la misma; desactiva las que no uses.)")
        print("=" * 66 + "\n")
    return {"usuarios": [u for u, _, _, _ in defaults], "password": clave}


def crear_sesion(conn, usuario_id):
    token = secrets.token_hex(32)
    conn.execute("INSERT INTO sesion (token, usuario_id) VALUES (?, ?)", (token, usuario_id))
    conn.commit()
    return token


# permisos_json tiene que venir aquí: es lo que se consulta en CADA petición para
# decidir qué puede hacer el usuario. Sin esta columna, permisos_de() no encontraba nada
# y caía en los permisos del rol, así que lo configurado en la pantalla de Usuarios se
# guardaba pero no se aplicaba nunca.
_SQL_SESION = (
    "SELECT u.id, u.username, u.nombre_completo, u.rol, u.permisos_json FROM sesion s"
    " JOIN usuario u ON u.id = s.usuario_id WHERE s.token = ? AND u.activo = 1")


def usuario_por_token(conn, token):
    """El usuario dueño de ese token, o None si no vale.

    Con el vencimiento apagado se ejecuta exactamente la misma consulta de siempre. La
    condición de la fecha solo se agrega cuando el hotel encendió HOTEL_SESION_HORAS, así
    que por omisión no hay ni un cambio de comportamiento.

    La comparación se hace dentro de la base y no en Python: 'creado_en' lo escribe
    SQLite con datetime('now'), que va en UTC, y datetime('now', '-N hours') también.
    Restando en Python habría que adivinar la zona horaria del servidor, y en Railway no
    es la del hotel.
    """
    if SESION_HORAS:
        row = conn.execute(_SQL_SESION + " AND s.creado_en > datetime('now', ?)",
                           (token, f"-{SESION_HORAS} hours")).fetchone()
    else:
        row = conn.execute(_SQL_SESION, (token,)).fetchone()
    return dict(row) if row else None


def purgar_sesiones_vencidas(conn):
    """Borra los tokens que ya no sirven. Con el vencimiento apagado no borra nada.

    Sin esto la tabla de sesiones crecería para siempre, con una fila por cada ingreso
    de cada persona desde el primer día. Corre al arrancar, que es suficiente: las
    vencidas ya no dan acceso aunque sigan guardadas.
    """
    if not SESION_HORAS:
        return 0
    cur = conn.execute("DELETE FROM sesion WHERE creado_en <= datetime('now', ?)",
                       (f"-{SESION_HORAS} hours",))
    borradas = cur.rowcount or 0
    if borradas:
        conn.commit()
        print(f"Sesiones vencidas eliminadas: {borradas}")
    return borradas


def get_current_user(authorization: str = Header(None), get_connection=None):
    """Dependencia de FastAPI: exige un token válido en el header Authorization: Bearer <token>."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")
    token = authorization.split(" ", 1)[1]
    conn = get_connection()
    user = usuario_por_token(conn, token)
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    return user


def puede_alguna(user, pantallas, escribir=False):
    """Si el usuario tiene el permiso pedido en AL MENOS UNA de esas pantallas.

    Hace falta para los datos que consulta más de una pantalla —el catálogo de guías y
    botes, por ejemplo, que la Agenda necesita para sus listas—. Atarlos a una sola
    pantalla dejaría sin funcionar a quien tiene acceso a la otra.
    """
    return any(puede(user, p, escribir=escribir) for p in pantallas)


# ---------------------------------------------------------------------------
# Permisos por pantalla
# ---------------------------------------------------------------------------

# Pantallas del sistema. Cada usuario puede tener 'ver', 'escribir' o nada.
PANTALLAS = [
    ("dashboard", "Dashboard"),
    ("reservas", "Reservas"),
    ("agenda", "Agenda de tours"),
    ("transporte", "Transporte"),
    ("sinac", "Entradas SINAC"),
    ("amenidades", "Amenidades"),
    ("restaurantes", "Restaurantes"),
    # El spa va aquí, junto a las pantallas de operación del día. Es su propio permiso
    # porque quien atiende el spa no necesita ver el resto, y porque los avisos de citas
    # nuevas se mandan a quien tenga este permiso: recepción y spa.
    ("spa", "Spa"),
    ("analitica", "Analítica"),
    ("resumen", "Resumen de operación"),
    ("importar", "Importar PDF"),
    ("usuarios", "Usuarios"),
    ("catalogo", "Catálogo"),
    ("publicacion", "Publicación"),
]

# Permisos que se aplican cuando el usuario no tiene una configuración propia.
# Así los usuarios creados antes de esta función siguen funcionando igual.
POR_ROL = {
    "recepcion": {k: "escribir" for k, _ in PANTALLAS},
    "gerencia": {k: "escribir" for k, _ in PANTALLAS},
    # El staff de campo mira la operación, pero Usuarios no: ahí se ven las cuentas del
    # sistema y quién puede hacer qué. Antes lo tenía en "ver" junto con todo lo demás,
    # y como los permisos no se aplicaban nadie lo notó.
    "staff": {k: "ver" for k, _ in PANTALLAS if k != "usuarios"},
}

# Perfiles sugeridos para crear usuarios rápido
PERFILES = {
    "Recepción": {k: "escribir" for k, _ in PANTALLAS},
    "Gerencia": {k: "escribir" for k, _ in PANTALLAS},
    "Restaurante": {"restaurantes": "escribir", "resumen": "ver", "reservas": "ver"},
    "Cocina": {"restaurantes": "ver", "amenidades": "escribir", "resumen": "ver"},
    "Guías": {"agenda": "escribir", "transporte": "ver", "resumen": "ver"},
    # La terapeuta del spa: su agenda y poco más. Necesita ver Reservas para saber quién
    # está en casa, y el resumen del día. Tiene 'spa' en escribir, que es además lo que
    # hace que le lleguen los avisos de citas nuevas.
    "Spa": {"spa": "escribir", "reservas": "ver", "resumen": "ver"},
    "Solo lectura": {k: "ver" for k, _ in PANTALLAS},
}


def limpiar_permisos(permisos):
    """Deja solo pantallas que existen y niveles válidos.

    En un solo lugar porque se usa al crear el usuario y al editarle los permisos, y
    las dos entradas tienen que filtrar igual: es lo que decide qué puede hacer alguien.
    """
    if not isinstance(permisos, dict):
        return {}
    validas = {k for k, _ in PANTALLAS}
    return {k: v for k, v in permisos.items()
            if k in validas and v in ("ver", "escribir")}


def permisos_de(user):
    """Permisos del usuario: los de su rejilla, y nada más.

    El rol ya no otorga permisos —es solo una etiqueta para saber quién es alguien—.
    Antes servía de respaldo cuando la rejilla estaba vacía, y eso hacía que un usuario
    creado sin configurar quedara con escritura en las trece pantallas, incluidas
    Usuarios e Importar PDF. Con dos fuentes de verdad nunca quedaba claro cuál mandaba.

    init_db copia los permisos del rol a la rejilla de quien no la tenga, así que en la
    práctica siempre hay algo; si aun así estuviera vacía, no se asume nada.
    """
    import json as _json
    propios = user.get("permisos_json")
    if propios:
        try:
            p = _json.loads(propios)
            if isinstance(p, dict):
                return limpiar_permisos(p)
        except (ValueError, TypeError):
            pass
    return {}


def puede(user, pantalla, escribir=False):
    nivel = permisos_de(user).get(pantalla)
    if not nivel:
        return False
    return nivel == "escribir" if escribir else nivel in ("ver", "escribir")


def requiere_permiso(user, pantalla):
    """Exige permiso de escritura sobre esa pantalla."""
    from fastapi import HTTPException
    if not puede(user, pantalla, escribir=True):
        raise HTTPException(
            status_code=403,
            detail=f"Tu usuario no tiene permiso para modificar {pantalla}.")
    return True


def requiere_lectura(user, pantalla):
    from fastapi import HTTPException
    if not puede(user, pantalla):
        raise HTTPException(status_code=403,
                            detail=f"Tu usuario no tiene acceso a {pantalla}.")
    return True
