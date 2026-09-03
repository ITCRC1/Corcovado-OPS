"""
Conexión con Opera Cloud (Oracle Hospitality) a través de OHIP.

Este módulo es la puerta de entrada: autentica, trae las reservas de un rango de
fechas y ofrece una herramienta de descubrimiento para ver con qué forma exacta
llegan los datos. La traducción al formato del lodge la hace opera_mapeo.py y el
ciclo automático lo lleva opera_sync.py.

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
import re
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

# ---------------------------------------------------------------------------
# Las credenciales, también desde un archivo
# ---------------------------------------------------------------------------
# En el servidor van en variables de entorno y ahí se quedan. Pero para PROBAR la
# conexión desde una computadora del lodge, definir siete variables de entorno en
# Windows es un trámite que no se le puede pedir a recepción, y hacerlo mal se ve igual
# que una credencial equivocada. Así que se acepta un archivo en la carpeta de datos.
#
# Las variables de entorno MANDAN: si están puestas, el archivo no se lee. Así el
# servidor sigue funcionando como antes y el archivo solo sirve donde hace falta.
#
# El archivo vive en data/, que está excluida del repositorio, y el respaldo de la base
# no lo incluye (solo copia hotel.db). Aun así: en producción, variables de entorno.
RUTA_CREDENCIALES = os.path.join(
    os.environ.get("HOTEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data"),
    "credenciales_opera.json",
)

# Qué constante de este módulo corresponde a cada variable de entorno.
_NOMBRE_INTERNO = {
    "OPERA_BASE_URL": "BASE_URL", "OPERA_APP_KEY": "APP_KEY",
    "OPERA_CLIENT_ID": "CLIENT_ID", "OPERA_CLIENT_SECRET": "CLIENT_SECRET",
    "OPERA_SCOPE": "SCOPE", "OPERA_ENTERPRISE_ID": "ENTERPRISE_ID",
    "OPERA_HOTEL_ID": "HOTEL_ID", "OPERA_USER": "USUARIO",
    "OPERA_PASSWORD": "CLAVE", "OPERA_GRANT_TYPE": "GRANT_TYPE",
}


def _leer_credenciales_de_archivo():
    """Rellena lo que no venga por variable de entorno. Nunca pisa una variable puesta."""
    if not os.path.exists(RUTA_CREDENCIALES):
        return []
    try:
        # utf-8-sig porque el Bloc de notas de Windows guarda con marca de orden de
        # bytes al principio, y con eso json.load falla sin explicar por qué.
        with open(RUTA_CREDENCIALES, encoding="utf-8-sig") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        # Un archivo mal escrito no puede tumbar el arranque: la conexión queda sin
        # configurar, que es el estado en que ya estaba.
        return []
    if not isinstance(datos, dict):
        return []

    puestas = []
    for clave, interno in _NOMBRE_INTERNO.items():
        # Se acepta con y sin el prefijo ('OPERA_APP_KEY' o 'app_key'): al copiar de la
        # ficha de OHIP es fácil escribir solo el nombre corto, y un archivo que no
        # funciona por el nombre de una llave es media hora perdida sin ninguna pista.
        valor = datos.get(clave)
        if valor is None:
            valor = datos.get(clave.replace("OPERA_", "").lower())
        if valor is None:
            continue
        valor = str(valor).strip()
        # Los huecos de la plantilla sin rellenar se ignoran.
        if not valor or valor.startswith("<"):
            continue
        if (os.environ.get(clave) or "").strip():
            continue                      # la variable de entorno manda
        globals()[interno] = valor
        puestas.append(clave)
    return puestas


DESDE_ARCHIVO = _leer_credenciales_de_archivo()
if BASE_URL:
    BASE_URL = BASE_URL.rstrip("/")


PLANTILLA_CREDENCIALES = {
    "_lea_esto": [
        "Credenciales de Opera Cloud (OHIP). Rellene los valores entre <> y guarde.",
        "Este archivo NO se sube al repositorio. No lo comparta ni lo pegue en un chat.",
        "En el servidor de produccion use variables de entorno en vez de este archivo.",
        "Si un dato no se lo dieron, deje el hueco tal como esta o borre la linea.",
    ],
    "OPERA_BASE_URL": "<Gateway URL, ej. https://xxx.hospitality.oracleindustry.com>",
    "OPERA_APP_KEY": "<App Key>",
    "OPERA_CLIENT_ID": "<Client ID>",
    "OPERA_CLIENT_SECRET": "<Client Secret>",
    "OPERA_HOTEL_ID": "<codigo del hotel en Opera, ej. CWLCR>",
    "OPERA_SCOPE": "<Scope, solo si se lo dieron>",
    "OPERA_ENTERPRISE_ID": "<Enterprise ID, solo si se lo dieron>",
    "OPERA_GRANT_TYPE": "<client_credentials o password, solo si hace falta forzarlo>",
    "OPERA_USER": "<usuario de integracion, solo con esquema password>",
    "OPERA_PASSWORD": "<contrasena de ese usuario, solo con esquema password>",
}


def crear_plantilla_credenciales():
    """Deja el archivo listo para rellenar. Nunca sobreescribe uno que ya exista."""
    if os.path.exists(RUTA_CREDENCIALES):
        return False
    os.makedirs(os.path.dirname(RUTA_CREDENCIALES), exist_ok=True)
    with open(RUTA_CREDENCIALES, "w", encoding="utf-8") as f:
        json.dump(PLANTILLA_CREDENCIALES, f, ensure_ascii=False, indent=2)
    return True

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


def normalizar_grant(valor):
    """'Client Credentials' -> 'client_credentials'.

    POR QUÉ HACE FALTA: la ficha de OHIP muestra el "Authentication Scheme" escrito para
    leer —"Client Credentials"—, y eso es lo que uno copia. Pero OAuth exige el valor
    exacto en minúsculas y con guion bajo. Enviado tal cual, Oracle responde un
    'HTTP 401 Unauthorized' pelado, idéntico al de una contraseña equivocada: se pierden
    horas revisando credenciales que estaban bien.
    """
    limpio = re.sub(r"[\s\-]+", "_", str(valor or "").strip().lower())
    conocidos = {
        "client_credentials": "client_credentials",
        "clientcredentials": "client_credentials",
        "credentials": "client_credentials",
        "password": "password",
        "user": "password",
        "usuario": "password",
        "password_credentials": "password",
    }
    # Si no es uno de los conocidos se devuelve como vino: puede ser un esquema nuevo
    # que Oracle acepte y que aquí no convenga bloquear.
    return conocidos.get(limpio, limpio)


def tipo_de_autenticacion():
    """Qué flujo de OAuth se va a usar."""
    if GRANT_TYPE:
        return normalizar_grant(GRANT_TYPE)
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


def _motivo_de(error, ancho=110):
    """Lo que Oracle dijo de verdad, sin la URL y sin el JSON en bruto.

    Los errores de OHIP vienen como un JSON con 'title', 'detail' y un 'o:errorCode'.
    Ese código es lo que sirve para reclamarle a Oracle —lo pueden buscar en su sistema—
    así que se saca a la vista en vez de dejarlo enterrado en una línea de 400 caracteres.
    """
    texto = str(error)
    lineas = []
    llave = texto.find("{")
    if llave >= 0:
        try:
            d = json.loads(texto[llave:texto.rfind("}") + 1])
            mensaje = d.get("detail") or d.get("title") or ""
            if mensaje:
                lineas.append(mensaje.strip())
            codigo = d.get("o:errorCode")
            if codigo:
                lineas.append(f"(código de Oracle: {codigo})")
            return lineas or [texto[:ancho]]
        except (ValueError, AttributeError):
            pass
    # Sin JSON: se devuelve todo menos la primera línea, que es la dirección.
    resto = [l.strip() for l in texto.splitlines()[1:] if l.strip()]
    return resto[:3] or [texto.splitlines()[0][:ancho]]


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
        # La cabecera va SIN el prefijo 'x-'. Comprobado contra el OHIP de Corcovado
        # (mtcu11pr, us-ashburn-1): con 'x-enterpriseId' —el nombre que usan los
        # ejemplos y que este conector traía— Oracle responde
        #
        #     HTTP 400  Enterprise ID is required
        #
        # aunque el dato vaya en la cabecera Y en el cuerpo. Con 'enterpriseId' pelado
        # entrega el token. Se probaron nueve variantes: solo esa funciona.
        #
        # El mensaje engaña, y por eso queda escrito: dice "falta" cuando en realidad
        # está pero con otro nombre, y uno se pone a revisar credenciales que estaban
        # bien. Si alguna otra propiedad pide 'x-enterpriseId', se agrega — mandar las
        # dos no molestó en las pruebas.
        cabeceras["enterpriseId"] = ENTERPRISE_ID

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


def traer_reservas(desde, hasta, limite=200, fetch=None, desplazamiento=0):
    """Una página de reservas cuya llegada cae en el rango (fechas AAAA-MM-DD).

    Gestiona el token por su cuenta: reutiliza el vigente y lo renueva si hace falta.
    """
    # Los bloques van cada uno en su PROPIO parámetro repetido:
    #
    #     ?fetchInstructions=Reservation&fetchInstructions=ReservationPreferences
    #
    # y NO separados por comas. Comprobado contra el OHIP de Corcovado: la forma con
    # comas se rechaza entera con
    #
    #     HTTP 400  Invalid value of: Query.  (OPERAWS-GEN01346)
    #
    # porque toma "Reservation,ReservationPackages" como un único valor que no existe.
    # Y ese error se dispara ANTES de comprobar los permisos, así que tapaba el 403 de
    # autorización y hacía creer que el problema era otro. Se perdió un rato ahí.
    campos = [
        ("arrivalStartDate", desde),
        ("arrivalEndDate", hasta),
        ("limit", limite),
    ]
    for bloque in (fetch or FETCH_INSTRUCTIONS):
        campos.append(("fetchInstructions", bloque))
    if desplazamiento:
        campos.append(("offset", desplazamiento))
    url = f"{BASE_URL}{RUTA_RESERVAS.format(hotel=HOTEL_ID)}?{urllib.parse.urlencode(campos)}"

    def peticion(token):
        return _pedir(urllib.request.Request(url, headers=_cabeceras(token)))

    return _con_reintento(peticion)


# Tope de páginas. Es un freno de seguridad, no un límite esperado: con 20 páginas de
# 200 se cubren 4.000 reservas, muy por encima de cualquier ventana normal del lodge.
# Existe para que un error de Oracle en la paginación (una página que se repite sola)
# no deje el proceso girando para siempre.
MAX_PAGINAS = 20


def _lista_de_reservas(respuesta):
    """Saca la lista de reservas de la respuesta, sea cual sea su envoltorio.

    OHIP la envuelve distinto según la versión ('reservations.reservationInfo',
    'reservationInfo', a veces una lista pelada). Se prueban las formas conocidas en
    vez de dar una por segura, porque equivocarse aquí no da error: da cero reservas,
    que es mucho peor —parecería que el hotel está vacío.
    """
    if isinstance(respuesta, list):
        return respuesta
    if not isinstance(respuesta, dict):
        return []
    for camino in (("reservations", "reservationInfo"), ("reservations", "reservation"),
                   ("reservationInfo",), ("reservation",), ("items",)):
        nodo = respuesta
        for paso in camino:
            nodo = nodo.get(paso) if isinstance(nodo, dict) else None
            if nodo is None:
                break
        if isinstance(nodo, list):
            return nodo
        if isinstance(nodo, dict):
            return [nodo]
    return []


def traer_todas_las_reservas(desde, hasta, limite=200, fetch=None):
    """Todas las reservas del rango, recorriendo las páginas.

    Devuelve (reservas, completo). El segundo valor dice si se pudo garantizar que
    la descarga trajo TODO el rango. Importa mucho: quien llama usa ese dato para
    decidir si puede cancelar las reservas que no vinieron en el lote. Con una lista
    parcial, "no vino" no significa "cancelada", significa "falta" — y cancelarlas
    borraría de la agenda a huéspedes que sí llegan.
    """
    reservas = []
    vistas = set()
    completo = False
    desplazamiento = 0

    for _ in range(MAX_PAGINAS):
        respuesta = traer_reservas(desde, hasta, limite=limite, fetch=fetch,
                                   desplazamiento=desplazamiento)
        pagina = _lista_de_reservas(respuesta)
        nuevas = 0
        for r in pagina:
            # Si Opera repite una reserva entre páginas, se queda una sola vez.
            clave = _identificador(r)
            if clave and clave in vistas:
                continue
            if clave:
                vistas.add(clave)
            reservas.append(r)
            nuevas += 1

        if len(pagina) < limite or nuevas == 0:
            completo = True
            break
        desplazamiento += len(pagina)

    return reservas, completo


def _identificador(reserva):
    """Número de confirmación, para no repetir reservas entre páginas."""
    try:
        import opera_mapeo
        return opera_mapeo.numero_de_confirmacion(reserva)
    except Exception:
        return None


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
    # Un bloque que esta instalación no expone se rechaza con
    # 'Invalid value of: Query' (OPERAWS-GEN01346), y ese error se dispara ANTES del
    # control de permisos. Así que si falta el permiso de lectura, un bloque VÁLIDO
    # responde 403 y uno inválido responde 400: se distinguen igual. Por eso el 403 se
    # cuenta como aceptado — el bloque existe, lo que falta es el permiso.
    print("Probando que bloques de datos responde Opera …")
    aceptados = []
    for instruccion in FETCH_INSTRUCTIONS:
        try:
            traer_reservas(desde, hasta, limite=1, fetch=["Reservation", instruccion])
            aceptados.append(instruccion)
            print(f"   OK      {instruccion}")
        except OperaError as e:
            if "GEN01244" in str(e) or "GEN01265" in str(e):
                aceptados.append(instruccion)
                print(f"   EXISTE  {instruccion}  (falta el permiso de lectura)")
                continue
            # Se muestra el MENSAJE de Oracle, no la primera línea —que es la URL—.
            # Costó un viaje entero descubrirlo: los bloques salían "RECHAZA" con la
            # dirección larguísima al lado y la explicación real ('User is not
            # authorized to access data for resort') quedaba cortada. El motivo es
            # justo lo único que hace falta ver aquí.
            print(f"   RECHAZA {instruccion}")
            for linea in _motivo_de(e):
                print(f"           {linea}")
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
