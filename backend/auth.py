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


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return h.hex(), salt


def verify_password(password, password_hash, salt):
    h, _ = hash_password(password, salt)
    return secrets.compare_digest(h, password_hash)


def seed_default_users(conn):
    existentes = conn.execute("SELECT COUNT(*) c FROM usuario").fetchone()["c"]
    if existentes > 0:
        return
    defaults = [
        ("recepcion", "recepcion2026", "Recepción", "recepcion"),
        ("gerencia", "gerencia2026", "Gerencia", "gerencia"),
        ("staff", "staff2026", "Staff de campo", "staff"),
    ]
    for username, password, nombre, rol in defaults:
        h, salt = hash_password(password)
        conn.execute(
            "INSERT INTO usuario (username, password_hash, salt, nombre_completo, rol) VALUES (?,?,?,?,?)",
            (username, h, salt, nombre, rol),
        )
    conn.commit()


def crear_sesion(conn, usuario_id):
    token = secrets.token_hex(32)
    conn.execute("INSERT INTO sesion (token, usuario_id) VALUES (?, ?)", (token, usuario_id))
    conn.commit()
    return token


def usuario_por_token(conn, token):
    row = conn.execute(
        # permisos_json tiene que venir aquí: es lo que se consulta en CADA petición
        # para decidir qué puede hacer el usuario. Sin esta columna, permisos_de() no
        # encontraba nada y caía en los permisos del rol, así que lo configurado en la
        # pantalla de Usuarios se guardaba pero no se aplicaba nunca.
        """SELECT u.id, u.username, u.nombre_completo, u.rol, u.permisos_json FROM sesion s
           JOIN usuario u ON u.id = s.usuario_id WHERE s.token = ? AND u.activo = 1""",
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
    "staff": {k: "ver" for k, _ in PANTALLAS},
}

# Perfiles sugeridos para crear usuarios rápido
PERFILES = {
    "Recepción": {k: "escribir" for k, _ in PANTALLAS},
    "Gerencia": {k: "escribir" for k, _ in PANTALLAS},
    "Restaurante": {"restaurantes": "escribir", "resumen": "ver", "reservas": "ver"},
    "Cocina": {"restaurantes": "ver", "amenidades": "escribir", "resumen": "ver"},
    "Guías": {"agenda": "escribir", "transporte": "ver", "resumen": "ver"},
    "Solo lectura": {k: "ver" for k, _ in PANTALLAS},
}


def permisos_de(user):
    """Permisos efectivos del usuario: los propios, o los de su rol."""
    import json as _json
    propios = user.get("permisos_json")
    if propios:
        try:
            p = _json.loads(propios)
            if isinstance(p, dict) and p:
                return p
        except (ValueError, TypeError):
            pass
    return POR_ROL.get(user.get("rol"), POR_ROL["staff"])


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
