"""
Autenticación por usuario y control de permisos por rol.

Roles:
- recepcion: lectura y escritura + administración de usuarios
- gerencia:  lectura y escritura (no administra usuarios)
- staff:     solo lectura (resúmenes del día)
"""
import hashlib
import os
import secrets
import threading
import time
from fastapi import Header, HTTPException

PBKDF2_ITERATIONS = 200_000

# Largo mínimo exigido a cualquier contraseña que se cree desde el sistema.
LARGO_MINIMO_PASSWORD = 10

# Duración de la sesión. Sin esto un token robado servía para siempre.
SESION_HORAS = int(os.environ.get("HOTEL_SESION_HORAS", "12"))


def es_produccion():
    """El sistema está expuesto a internet (Railway u otro hosting), no en la
    red cerrada del lodge. En ese caso no se permiten contraseñas de demostración."""
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_ENVIRONMENT_NAME"):
        return True
    return os.environ.get("HOTEL_ENTORNO", "").strip().lower() in ("produccion", "production", "prod")


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return h.hex(), salt


def verify_password(password, password_hash, salt):
    h, _ = hash_password(password, salt)
    return secrets.compare_digest(h, password_hash)


def validar_password(password):
    """Rechaza contraseñas demasiado cortas antes de guardarlas."""
    if not password or len(password) < LARGO_MINIMO_PASSWORD:
        raise HTTPException(
            status_code=400,
            detail=f"La contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres",
        )
    return password


# --------------------------------------------------------------------------
# Usuarios iniciales
# --------------------------------------------------------------------------

DEMO_USERS = [
    ("recepcion", "recepcion2026", "Recepción", "recepcion"),
    ("gerencia", "gerencia2026", "Gerencia", "gerencia"),
    ("staff", "staff2026", "Staff de campo", "staff"),
]


def seed_default_users(conn):
    """Crea el primer usuario la primera vez que arranca el sistema.

    En producción NO se crean los usuarios de demostración: sus contraseñas están
    publicadas en la documentación y cualquiera podría entrar. Ahí se exige definir
    HOTEL_ADMIN_PASSWORD, y con eso se crea una sola cuenta de recepción.
    """
    existentes = conn.execute("SELECT COUNT(*) c FROM usuario").fetchone()["c"]
    if existentes > 0:
        return

    admin_user = (os.environ.get("HOTEL_ADMIN_USER") or "recepcion").strip() or "recepcion"
    admin_pass = os.environ.get("HOTEL_ADMIN_PASSWORD") or ""

    if admin_pass:
        if len(admin_pass) < LARGO_MINIMO_PASSWORD:
            raise RuntimeError(
                f"HOTEL_ADMIN_PASSWORD debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres."
            )
        h, salt = hash_password(admin_pass)
        conn.execute(
            "INSERT INTO usuario (username, password_hash, salt, nombre_completo, rol) VALUES (?,?,?,?,?)",
            (admin_user, h, salt, "Recepción", "recepcion"),
        )
        conn.commit()
        print(f"Usuario inicial creado: '{admin_user}' (rol recepción).")
        return

    if es_produccion():
        raise RuntimeError(
            "No hay usuarios en la base y el sistema está en producción.\n"
            "Define la variable de entorno HOTEL_ADMIN_PASSWORD (y opcionalmente\n"
            "HOTEL_ADMIN_USER) para crear la primera cuenta de recepción.\n"
            "Los usuarios de demostración no se crean en producción porque sus\n"
            "contraseñas son públicas."
        )

    for username, password, nombre, rol in DEMO_USERS:
        h, salt = hash_password(password)
        conn.execute(
            "INSERT INTO usuario (username, password_hash, salt, nombre_completo, rol) VALUES (?,?,?,?,?)",
            (username, h, salt, nombre, rol),
        )
    conn.commit()
    print("AVISO: se crearon los usuarios de DEMOSTRACIÓN (recepcion/gerencia/staff).")
    print("       Cámbiales la contraseña antes de usar el sistema con datos reales.")


# --------------------------------------------------------------------------
# Sesiones
# --------------------------------------------------------------------------

def crear_sesion(conn, usuario_id):
    purgar_sesiones_vencidas(conn)
    token = secrets.token_hex(32)
    conn.execute("INSERT INTO sesion (token, usuario_id) VALUES (?, ?)", (token, usuario_id))
    conn.commit()
    return token


def purgar_sesiones_vencidas(conn):
    conn.execute(
        f"DELETE FROM sesion WHERE creado_en <= datetime('now', '-{SESION_HORAS} hours')"
    )
    conn.commit()


def usuario_por_token(conn, token):
    row = conn.execute(
        f"""SELECT u.id, u.username, u.nombre_completo, u.rol FROM sesion s
           JOIN usuario u ON u.id = s.usuario_id
           WHERE s.token = ? AND u.activo = 1
             AND s.creado_en > datetime('now', '-{SESION_HORAS} hours')""",
        (token,),
    ).fetchone()
    return dict(row) if row else None


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


# --------------------------------------------------------------------------
# Permisos
# --------------------------------------------------------------------------

def requiere_escritura(user):
    if user["rol"] not in ("recepcion", "gerencia"):
        raise HTTPException(status_code=403, detail="Tu rol solo tiene permiso de lectura")


def requiere_admin(user):
    """Administrar usuarios (crear, desactivar, cambiar contraseñas) es exclusivo de
    recepción: quien puede cambiar la contraseña de otro puede tomar su rol."""
    if user["rol"] != "recepcion":
        raise HTTPException(status_code=403,
                            detail="Solo una cuenta de Recepción puede administrar usuarios")


# --------------------------------------------------------------------------
# Freno a los intentos de adivinar contraseñas
# --------------------------------------------------------------------------

MAX_INTENTOS = 8
VENTANA_SEGUNDOS = 300

_intentos = {}
_intentos_lock = threading.Lock()


def _limpiar(ahora):
    for k, (n, hasta) in list(_intentos.items()):
        if hasta <= ahora:
            _intentos.pop(k, None)


def verificar_intentos(clave):
    """Bloquea temporalmente tras varios fallos seguidos desde el mismo origen."""
    ahora = time.time()
    with _intentos_lock:
        _limpiar(ahora)
        n, hasta = _intentos.get(clave, (0, 0))
        if n >= MAX_INTENTOS and hasta > ahora:
            raise HTTPException(
                status_code=429,
                detail=f"Demasiados intentos fallidos. Espera {int(hasta - ahora) + 1} segundos.",
            )


def registrar_fallo(clave):
    ahora = time.time()
    with _intentos_lock:
        n, hasta = _intentos.get(clave, (0, 0))
        if hasta <= ahora:
            n = 0
        _intentos[clave] = (n + 1, ahora + VENTANA_SEGUNDOS)


def limpiar_intentos(clave):
    with _intentos_lock:
        _intentos.pop(clave, None)
