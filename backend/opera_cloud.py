"""
Conexión con Opera Cloud (Oracle Hospitality) a través de OHIP.

Estado: HERRAMIENTA DE DESCUBRIMIENTO. Todavía no alimenta el sistema — sirve para
autenticarse, traer las reservas de unos días y ver con qué forma exacta llegan los
datos. El mapeo de campos se hace después, contra respuestas reales.

Las rutas y los nombres de parámetros de abajo son los habituales de OHIP, pero
cada instalación puede diferir según versión y módulos contratados. Si algo falla,
el error se imprime completo para poder ajustarlo: son constantes en un solo lugar.

Nada de esto se ejecuta al arrancar el sistema; hay que invocarlo a mano.

Uso:
    python opera_cloud.py probar
    python opera_cloud.py descubrir 2026-08-10 2026-08-12
"""
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Configuración: SIEMPRE por variables de entorno. Ninguna credencial se escribe
# en el código ni se sube al repositorio.
# ---------------------------------------------------------------------------

BASE_URL = (os.environ.get("OPERA_BASE_URL") or "").rstrip("/")   # "Gateway URL"
APP_KEY = os.environ.get("OPERA_APP_KEY") or ""                   # "App Key"
CLIENT_ID = os.environ.get("OPERA_CLIENT_ID") or ""
CLIENT_SECRET = os.environ.get("OPERA_CLIENT_SECRET") or ""
SCOPE = os.environ.get("OPERA_SCOPE") or ""                       # "Scope"
ENTERPRISE_ID = os.environ.get("OPERA_ENTERPRISE_ID") or ""       # "Enterprise ID"
HOTEL_ID = os.environ.get("OPERA_HOTEL_ID") or ""                 # código del hotel

# Solo aplican si el esquema de autenticación es de usuario (grant_type=password).
# Si en OHIP les dieron Scope y Enterprise ID sin usuario, no hacen falta.
USUARIO = os.environ.get("OPERA_USER") or ""
CLAVE = os.environ.get("OPERA_PASSWORD") or ""

# "Authentication Scheme" de la ficha de OHIP. Si no se indica, se deduce: con
# usuario y contraseña se usa 'password'; sin ellos, 'client_credentials'.
GRANT_TYPE = (os.environ.get("OPERA_GRANT_TYPE") or "").strip()

RUTA_TOKEN = "/oauth/v1/tokens"
RUTA_RESERVAS = "/rsv/v1/hotels/{hotel}/reservations"

# El endpoint de reservas devuelve un esqueleto mínimo si no se le pide más. Cada
# bloque de datos hay que solicitarlo por nombre. Esta lista cubre lo que el sistema
# necesita; el descubrimiento informa cuáles respondió Oracle de verdad, porque
# depende de los módulos contratados y de la versión.
FETCH_INSTRUCTIONS = [
    "Reservation",       # núcleo: fechas, habitación, adultos/niños, estado
    "ReservationPackages",   # paquetes y adicionales -> de aquí saldrían los tours
    "ReservationComments",   # notas de la reserva
    "GuestComments",         # notas del perfil del huésped
    "ReservationPreferences",  # preferencias (alergias, almohadas, etc.)
    "ReservationTransportation",  # traslados: llegada/salida y horas
    "ReservationMemberships",    # programas de fidelidad, útil para detectar VIP
    "ReservationAlerts",         # avisos que recepción debe ver
    "ReservationTraces",         # instrucciones por departamento
    "ReservationLinkedReservations",  # reservas vinculadas -> grupos
    "ReservationGuestList",      # acompañantes
]

DIR_MUESTRAS = os.path.join(
    os.environ.get("HOTEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data"),
    "opera_muestras",
)


class OperaError(Exception):
    pass


def tipo_de_autenticacion():
    """Qué flujo de OAuth se va a usar."""
    if GRANT_TYPE:
        return GRANT_TYPE
    return "password" if (USUARIO and CLAVE) else "client_credentials"


def _faltantes():
    requeridas = {
        "OPERA_BASE_URL": BASE_URL, "OPERA_APP_KEY": APP_KEY,
        "OPERA_CLIENT_ID": CLIENT_ID, "OPERA_CLIENT_SECRET": CLIENT_SECRET,
        "OPERA_HOTEL_ID": HOTEL_ID,
    }
    if tipo_de_autenticacion() == "password":
        requeridas["OPERA_USER"] = USUARIO
        requeridas["OPERA_PASSWORD"] = CLAVE
    return [k for k, v in requeridas.items() if not v]


def _pedir(req, timeout=45):
    """Ejecuta la petición y, si falla, muestra el cuerpo del error completo.

    Sin esto, OHIP devuelve un 400 o 401 pelado y no hay forma de saber si el
    problema es la credencial, el hotel, un parámetro o un módulo no contratado.
    """
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detalle = e.read().decode("utf-8")[:2000]
        except Exception:
            detalle = "(sin cuerpo)"
        raise OperaError(f"HTTP {e.code} en {req.full_url}\n{detalle}") from None
    except urllib.error.URLError as e:
        raise OperaError(f"No se pudo conectar con {req.full_url}: {e.reason}") from None


# El token se guarda SOLO en memoria: dura menos de una hora y volver a pedirlo es
# barato. No va a la base de datos ni a ningún archivo — un secreto que no se
# escribe en disco no se puede filtrar por un respaldo ni por un descuido.
# Si el contenedor se reinicia, simplemente se pide uno nuevo.
_token = {"valor": None, "expira_en": 0.0}
_token_lock = threading.Lock()

# Se renueva un poco antes de que venza, para que una petición no se quede a mitad
# de camino con un token que expiró entre que se comprobó y se usó.
MARGEN_RENOVACION = 120


def _autenticar():
    faltan = _faltantes()
    if faltan:
        raise OperaError("Faltan variables de entorno: " + ", ".join(faltan))

    grant = tipo_de_autenticacion()
    campos = {"grant_type": grant}
    if grant == "password":
        campos["username"] = USUARIO
        campos["password"] = CLAVE
    if SCOPE:
        campos["scope"] = SCOPE
    if ENTERPRISE_ID:
        campos["enterpriseId"] = ENTERPRISE_ID

    basica = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    cabeceras = {
        "Content-Type": "application/x-www-form-urlencoded",
        "x-app-key": APP_KEY,
        "Authorization": f"Basic {basica}",
    }
    if ENTERPRISE_ID:
        cabeceras["x-enterpriseId"] = ENTERPRISE_ID

    req = urllib.request.Request(
        BASE_URL + RUTA_TOKEN, data=urllib.parse.urlencode(campos).encode(),
        method="POST", headers=cabeceras)
    respuesta = _pedir(req)
    token = respuesta.get("access_token")
    if not token:
        raise OperaError(f"La respuesta no trae access_token: {respuesta}")
    # Se respeta la duración que informa Oracle en vez de suponerla: si algún día
    # la cambian, el conector se adapta solo.
    try:
        dura = int(respuesta.get("expires_in") or 3600)
    except (TypeError, ValueError):
        dura = 3600
    return token, dura


def obtener_token(forzar=False):
    """Devuelve un token válido, reutilizando el anterior mientras no venza."""
    with _token_lock:
        ahora = time.time()
        if not forzar and _token["valor"] and ahora < _token["expira_en"]:
            return _token["valor"]
        valor, dura = _autenticar()
        _token["valor"] = valor
        _token["expira_en"] = ahora + max(dura - MARGEN_RENOVACION, 30)
        return valor


def _con_reintento(hacer_peticion):
    """Ejecuta la petición y, si Opera responde 401, renueva el token y reintenta.

    Hace falta porque el token puede quedar invalidado del lado de Oracle antes de
    su vencimiento (cambio de contraseña, sesión revocada, mantenimiento). Sin esto,
    la sincronización se quedaría fallando hasta el siguiente reinicio.
    """
    token = obtener_token()
    try:
        return hacer_peticion(token)
    except OperaError as e:
        if "HTTP 401" not in str(e):
            raise
        return hacer_peticion(obtener_token(forzar=True))


def _cabeceras(token):
    return {
        "Authorization": f"Bearer {token}",
        "x-app-key": APP_KEY,
        "x-hotelid": HOTEL_ID,
        "Accept": "application/json",
    }


def traer_reservas(desde, hasta, limite=200, fetch=None):
    """Reservas cuya llegada cae en el rango (fechas en formato AAAA-MM-DD).

    Gestiona el token por su cuenta: reutiliza el vigente y lo renueva si hace falta.
    """
    params = urllib.parse.urlencode({
        "arrivalStartDate": desde,
        "arrivalEndDate": hasta,
        "limit": limite,
        "fetchInstructions": ",".join(fetch or FETCH_INSTRUCTIONS),
    })
    url = f"{BASE_URL}{RUTA_RESERVAS.format(hotel=HOTEL_ID)}?{params}"

    def peticion(token):
        return _pedir(urllib.request.Request(url, headers=_cabeceras(token)))

    return _con_reintento(peticion)


# ---------------------------------------------------------------------------
# Descubrimiento: qué campos llegan, sin exponer datos de huéspedes
# ---------------------------------------------------------------------------

def _tipo(v):
    if isinstance(v, bool):
        return "booleano"
    if isinstance(v, (int, float)):
        return "numero"
    if isinstance(v, str):
        return "texto"
    if v is None:
        return "vacio"
    return type(v).__name__


def mapa_de_campos(dato, prefijo="", salida=None, profundidad=0):
    """Recorre la respuesta y arma la lista de campos con su tipo.

    Devuelve SOLO los nombres y tipos: ningún nombre de huésped ni dato personal,
    para poder compartir la estructura sin exponer información de nadie.
    """
    salida = {} if salida is None else salida
    if profundidad > 8:
        return salida
    if isinstance(dato, dict):
        for k, v in dato.items():
            camino = f"{prefijo}.{k}" if prefijo else k
            if isinstance(v, (dict, list)):
                mapa_de_campos(v, camino, salida, profundidad + 1)
            else:
                salida.setdefault(camino, _tipo(v))
    elif isinstance(dato, list):
        for item in dato[:3]:   # basta con mirar los primeros
            mapa_de_campos(item, f"{prefijo}[]", salida, profundidad + 1)
    return salida


def descubrir(desde, hasta):
    os.makedirs(DIR_MUESTRAS, exist_ok=True)
    print(f"Autenticando contra {BASE_URL} …")
    obtener_token()
    minutos = max(int((_token["expira_en"] - time.time()) / 60), 0)
    print(f"  Token obtenido (se reutiliza durante ~{minutos} minutos).\n")

    # Se prueba cada bloque por separado: si uno no está contratado o cambió de
    # nombre, Oracle rechaza la petición entera. Así se sabe cuáles sirven en vez
    # de quedarse sin nada por culpa de uno solo.
    print("Probando que bloques de datos responde Opera …")
    aceptados = []
    for instruccion in FETCH_INSTRUCTIONS:
        try:
            traer_reservas(desde, hasta, limite=1, fetch=["Reservation", instruccion])
            aceptados.append(instruccion)
            print(f"   OK      {instruccion}")
        except OperaError as e:
            primera = str(e).splitlines()[0]
            print(f"   RECHAZA {instruccion}  ({primera})")
    print()

    if not aceptados:
        raise OperaError("Opera no acepto ningun bloque de datos. Revisa el hotel y los permisos.")

    print(f"Trayendo reservas con llegada entre {desde} y {hasta} …")
    datos = traer_reservas(desde, hasta, fetch=aceptados)

    crudo = os.path.join(DIR_MUESTRAS, f"reservas_{desde}_{hasta}.json")
    with open(crudo, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print(f"  Respuesta completa guardada en:\n  {crudo}")
    print("  (contiene datos de huespedes: NO se sube al repositorio)\n")

    campos = mapa_de_campos(datos)
    estructura = os.path.join(DIR_MUESTRAS, f"estructura_{desde}_{hasta}.txt")
    with open(estructura, "w", encoding="utf-8") as f:
        f.write(f"Campos devueltos por Opera Cloud ({len(campos)} en total)\n")
        f.write("Solo nombres y tipos, sin ningun dato de huespedes.\n\n")
        f.write("Bloques aceptados por esta propiedad:\n")
        for i in aceptados:
            f.write(f"  - {i}\n")
        rechazados = [i for i in FETCH_INSTRUCTIONS if i not in aceptados]
        if rechazados:
            f.write("\nBloques NO disponibles:\n")
            for i in rechazados:
                f.write(f"  - {i}\n")
        f.write("\n")
        for camino in sorted(campos):
            f.write(f"{camino}  ->  {campos[camino]}\n")
    print(f"Estructura (sin datos personales) guardada en:\n  {estructura}")
    print(f"\n{len(campos)} campos distintos encontrados.")
    print("Ese segundo archivo es el que se puede compartir para armar el mapeo.")


def probar():
    grant = tipo_de_autenticacion()
    print(f"Gateway:              {BASE_URL or '(sin definir)'}")
    print(f"Hotel:                {HOTEL_ID or '(sin definir)'}")
    print(f"Esquema (grant_type): {grant}")
    print(f"Scope:                {'definido' if SCOPE else 'no se envia'}")
    print(f"Enterprise ID:        {'definido' if ENTERPRISE_ID else 'no se envia'}")
    print()

    faltan = _faltantes()
    if faltan:
        print("Faltan variables de entorno:")
        for v in faltan:
            print(f"  - {v}")
        return 1
    try:
        obtener_token()
    except OperaError as e:
        print("FALLO la autenticacion:\n")
        print(e)
        print()
        print("Si el error menciona el grant_type o el scope, prueba el otro esquema:")
        otro = "password" if grant == "client_credentials" else "client_credentials"
        print(f'  $env:OPERA_GRANT_TYPE = "{otro}"')
        if otro == "password":
            print("  (ese esquema necesita ademas OPERA_USER y OPERA_PASSWORD)")
        return 1
    minutos = max(int((_token["expira_en"] - time.time()) / 60), 0)
    print(f"Conexion correcta. Token valido por ~{minutos} minutos.")
    return 0


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "probar"
    try:
        if accion == "probar":
            sys.exit(probar())
        elif accion == "descubrir":
            if len(sys.argv) < 4:
                print("Uso: python opera_cloud.py descubrir AAAA-MM-DD AAAA-MM-DD")
                sys.exit(1)
            descubrir(sys.argv[2], sys.argv[3])
        else:
            print(__doc__)
            sys.exit(1)
    except OperaError as e:
        print("ERROR:\n")
        print(e)
        sys.exit(1)
