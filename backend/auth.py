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


def _quiere_reset():
    return (os.environ.get("HOTEL_RESET_ADMIN") or "").strip().lower() in (
        "1", "true", "si", "sí", "yes")


def asegurar_cuenta_admin(conn):
    """Garantiza que SIEMPRE haya una forma de entrar al sistema.

    Corre en cada arranque, no solo la primera vez. Antes solo creaba usuarios con la
    tabla completamente vacía, y eso dejaba dos formas de quedar encerrado para
    siempre: desactivar la última cuenta de recepción (el usuario seguía existiendo,
    así que nunca se recreaba) u olvidar la contraseña.

    Reglas:
    - Sin ningún usuario: se crea la cuenta inicial desde HOTEL_ADMIN_PASSWORD. En
      producción esa variable es obligatoria, porque las contraseñas de los usuarios
      de demostración son públicas.
    - Sin ninguna cuenta de recepción ACTIVA: se restaura la cuenta de administración
      desde HOTEL_ADMIN_PASSWORD (se reactiva y se le repone la contraseña).
    - Con HOTEL_RESET_ADMIN=1: se repone la contraseña aunque todo esté bien. Sirve
      para cuando nadie la recuerda.
    """
    admin_user = (os.environ.get("HOTEL_ADMIN_USER") or "recepcion").strip() or "recepcion"
    admin_pass = os.environ.get("HOTEL_ADMIN_PASSWORD") or ""
    if admin_pass and len(admin_pass) < LARGO_MINIMO_PASSWORD:
        raise RuntimeError(
            f"HOTEL_ADMIN_PASSWORD debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres."
        )

    total = conn.execute("SELECT COUNT(*) c FROM usuario").fetchone()["c"]
    recepcion_activa = conn.execute(
        "SELECT COUNT(*) c FROM usuario WHERE rol = 'recepcion' AND activo = 1"
    ).fetchone()["c"]

    # --- Primer arranque: no hay absolutamente nada ---
    if total == 0 and not admin_pass:
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
                "INSERT INTO usuario (username, password_hash, salt, nombre_completo, rol) "
                "VALUES (?,?,?,?,?)",
                (username, h, salt, nombre, rol),
            )
        conn.commit()
        print("AVISO: se crearon los usuarios de DEMOSTRACIÓN (recepcion/gerencia/staff).")
        print("       Cámbiales la contraseña antes de usar el sistema con datos reales.")
        return

    if not admin_pass:
        if recepcion_activa == 0:
            print("=" * 62)
            print(" ATENCION: no hay ninguna cuenta de Recepcion activa.")
            print(" Nadie puede administrar el sistema.")
            print(" Define HOTEL_ADMIN_PASSWORD y vuelve a desplegar para recuperarlo.")
            print("=" * 62)
        return

    forzar = _quiere_reset()
    if recepcion_activa > 0 and not forzar:
        return

    # --- Recuperación ---
    h, salt = hash_password(admin_pass)
    fila = conn.execute("SELECT id FROM usuario WHERE username = ?", (admin_user,)).fetchone()
    if fila:
        conn.execute(
            "UPDATE usuario SET password_hash = ?, salt = ?, activo = 1, rol = 'recepcion' "
            "WHERE id = ?",
            (h, salt, fila["id"]),
        )
        # Se cierran las sesiones viejas de esa cuenta, como en cualquier cambio de
        # contraseña: si alguien tenía una abierta, deja de servirle.
        conn.execute("DELETE FROM sesion WHERE usuario_id = ?", (fila["id"],))
        accion = "restaurada"
    else:
        conn.execute(
            "INSERT INTO usuario (username, password_hash, salt, nombre_completo, rol) "
            "VALUES (?,?,?,?,?)",
            (admin_user, h, salt, "Recepción", "recepcion"),
        )
        accion = "creada"
    conn.commit()

    print("=" * 62)
    print(f" Cuenta de administracion {accion}: '{admin_user}' (rol recepcion).")
    print(" Entra con la contrasena de HOTEL_ADMIN_PASSWORD y cambiala desde")
    print(" la pantalla Usuarios.")
    if forzar:
        print(" HOTEL_RESET_ADMIN esta activa: BORRALA de las variables, o la")
        print(" contrasena volvera a reponerse en cada despliegue.")
    print("=" * 62)


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
