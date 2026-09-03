"""
Traduce una reserva de Opera Cloud al formato que ya usa el sistema.

El objetivo es que a partir de aquí nada distinga una reserva que vino de Opera de
una que vino del PDF: se produce EXACTAMENTE el mismo diccionario que arma
pdf_parser, y desde ahí siguen el mismo camino (importer -> loader). Así las reglas
del lodge —tours, grupos, entradas del SINAC, amenidades— se aplican una sola vez y
valen para las dos fuentes.

Sobre las rutas de campos
-------------------------
Todos los nombres de campo de Opera están arriba, en constantes, y cada dato admite
VARIAS rutas alternativas. OHIP no devuelve la misma forma en todas las propiedades:
depende de la versión y de los módulos contratados. Poner las rutas en un solo lugar
permite corregirlas contra la respuesta real sin tocar la lógica.

Para ver la forma real de su Opera:

    python opera_cloud.py descubrir 2026-08-10 2026-08-12

Eso deja un archivo estructura_….txt con los nombres de campo (sin datos de
huéspedes). Con ese archivo se ajustan las rutas de abajo.
"""
import datetime
import re

# ---------------------------------------------------------------------------
# Rutas de campos. "a.b[].c" baja por diccionarios y recorre listas.
# Se prueban en orden: gana la primera que traiga algo.
# ---------------------------------------------------------------------------

RUTAS = {
    "conf_no": [
        "reservationIdList[].id",
        "reservationIdList[].idValue",
        "confirmationNumber",
        "reservationId.id",
        "id",
    ],
    "room_no": [
        "roomStay.roomId",
        "roomStay.roomNumber",
        "roomStay.room",
        "roomId",
    ],
    "arr_date": [
        "roomStay.arrivalDate",
        "roomStay.expectedArrivalDate",
        "arrivalDate",
    ],
    "dep_date": [
        "roomStay.departureDate",
        "roomStay.expectedDepartureDate",
        "departureDate",
    ],
    "arr_time": [
        "roomStay.expectedTimes.reservationExpectedArrivalTime",
        "roomStay.expectedArrivalTime",
    ],
    "room_type": [
        "roomStay.roomType",
        "roomStay.roomTypeCharged",
        "roomType",
    ],
    "adl": [
        "roomStay.guestCounts.adults",
        "roomStay.adultCount",
        "guestCounts.adults",
    ],
    "chl": [
        "roomStay.guestCounts.children",
        "roomStay.childCount",
        "guestCounts.children",
    ],
    "rooms": [
        "roomStay.numberOfRooms",
        "roomStay.roomCount",
    ],
    "estado": [
        "reservationStatus",
        "roomStay.reservationStatus",
        "status",
    ],
    "mkt_code": [
        "roomStay.marketCode",
        "marketCode",
    ],
    "src_code": [
        "roomStay.sourceCode",
        "sourceCode",
    ],
    "company": [
        "reservationProfiles[].profile.company.companyName",
        "reservationProfiles[].profile.customer.companyName",
        "travelAgent.name",
        "company.name",
    ],
    "block_code": [
        "roomStay.blockCode",
        "blockCode",
    ],
}

# El nombre del titular. Se busca aparte porque en Opera viene partido en piezas y
# hay que recomponerlo respetando el orden.
RUTAS_NOMBRE_APELLIDO = [
    "reservationGuests[].profileInfo.profile.customer.personName[].surname",
    "reservationProfiles[].profile.customer.personName[].surname",
    "guest.personName[].surname",
    "profile.customer.personName[].surname",
]
RUTAS_NOMBRE_PILA = [
    "reservationGuests[].profileInfo.profile.customer.personName[].givenName",
    "reservationProfiles[].profile.customer.personName[].givenName",
    "guest.personName[].givenName",
    "profile.customer.personName[].givenName",
]

# Texto libre. TODO lo que sea texto para leer va aquí: de este conjunto salen las
# amenidades, el régimen de comidas y las notas de recepción. Es preferible traer de
# más y que los detectores filtren, a perderse una instrucción del huésped.
RUTAS_TEXTOS = [
    "comments[].comment",
    "comments[].text",
    "reservationComments[].comment",
    "guestComments[].comment",
    "reservationPreferences[].preference[].description",
    "preferences[].description",
    "reservationTraces[].trace[].text",
    "traces[].text",
    "reservationAlerts[].alert[].comment",
    "alerts[].comment",
    "specialRequests[].description",
    "reservationMemberships[].membership[].membershipType",
]

# Paquetes y adicionales: de aquí salen los tours.
RUTAS_PAQUETES_NOMBRE = [
    "reservationPackages[].packageCode",
    "reservationPackages[].packageHeaderDescription",
    "packages[].packageCode",
    "packages[].description",
    "roomStay.packages[].packageCode",
]
RUTAS_PAQUETES_FECHA = [
    "reservationPackages[].startDate",
    "reservationPackages[].consumptionDate",
    "packages[].startDate",
]

# Acompañantes.
RUTAS_ACOMPANANTES = [
    "reservationGuestList[].profileInfo.profile.customer.personName[]",
    "reservationGuests[].profileInfo.profile.customer.personName[]",
    "sharedGuests[].personName[]",
]

# Transporte: llegada y salida. De aquí sale el punto de embarque (Sierpe o Drake) y la
# hora del vuelo.
#
# OJO CON LA FORMA: en OHIP 'arrivalTransportation' es un OBJETO, no un texto —trae tipo,
# descripción, hora y transportista—. Las rutas apuntan al objeto a propósito y el texto
# se saca con _texto_de(), que junta lo que haya dentro. Apuntar a un nombre de campo
# concreto sería adivinar: ese nombre cambia entre instalaciones, y equivocarse aquí no
# da error, da un punto de embarque vacío para siempre.
RUTAS_TRANSPORTE_LLEGADA = [
    "reservationTransportation.arrivalTransportation",
    "reservationTransportation[].arrivalTransportation",
    "transportation.arrival",
    "reservationTransportation[].arrival",
    "roomStay.transportation.arrival",
]
RUTAS_TRANSPORTE_SALIDA = [
    "reservationTransportation.departureTransportation",
    "reservationTransportation[].departureTransportation",
    "transportation.departure",
    "reservationTransportation[].departure",
    "roomStay.transportation.departure",
]

# Cómo se traducen los estados de Opera a los del lodge.
ESTADOS = {
    "RESERVED": "POR INGRESAR",
    "CONFIRMED": "POR INGRESAR",
    "DUEIN": "POR INGRESAR",
    "DUE IN": "POR INGRESAR",
    "PROSPECT": "POR INGRESAR",
    "WAITLIST": "POR INGRESAR",
    "INHOUSE": "EN CASA",
    "IN HOUSE": "EN CASA",
    "CHECKEDIN": "CKIN",
    "CHECKED IN": "CKIN",
    "ARRIVED": "CKIN",
    "DUEOUT": "EN CASA",
    "DUE OUT": "EN CASA",
    "CHECKEDOUT": "SALIO",
    "CHECKED OUT": "SALIO",
    "DEPARTED": "SALIO",
    "CANCELED": "CANCELADA",
    "CANCELLED": "CANCELADA",
    "NOSHOW": "CANCELADA",
    "NO SHOW": "CANCELADA",
}

# Palabras que identifican el punto de embarque. El lodge solo opera por Sierpe y
# Drake; cualquier otra cosa queda "sin confirmar" para que recepción la resuelva.
PUNTOS = {"SIERPE": "SIERPE", "DRAKE": "DRAKE", "AGUJITAS": "DRAKE", "BAHIA": "DRAKE"}


# ---------------------------------------------------------------------------
# Lectura de rutas
# ---------------------------------------------------------------------------

def leer(dato, ruta):
    """Todos los valores que hay en esa ruta. Devuelve siempre una lista."""
    nodo = [dato]
    for paso in ruta.split("."):
        lista = paso.endswith("[]")
        clave = paso[:-2] if lista else paso
        siguiente = []
        for n in nodo:
            if not isinstance(n, dict):
                continue
            v = n.get(clave)
            if v is None:
                continue
            if isinstance(v, list):
                siguiente.extend(v)
            else:
                siguiente.append(v)
        nodo = siguiente
        if not nodo:
            return []
    return [n for n in nodo if n is not None and n != ""]


def primero(dato, rutas, por_defecto=None):
    """El primer valor que aparezca, probando las rutas en orden."""
    for ruta in rutas:
        valores = leer(dato, ruta)
        if valores:
            v = valores[0]
            if isinstance(v, (dict, list)):
                continue
            return v
    return por_defecto


def todos(dato, rutas):
    """Todos los valores de todas las rutas, sin repetir y conservando el orden."""
    salida = []
    for ruta in rutas:
        for v in leer(dato, ruta):
            if isinstance(v, (dict, list)):
                continue
            v = str(v).strip()
            if v and v not in salida:
                salida.append(v)
    return salida


def campo(dato, nombre, por_defecto=None):
    return primero(dato, RUTAS.get(nombre, []), por_defecto)


def _texto_de(valor, profundidad=0):
    """Todo el texto que haya dentro de un valor, sea texto, lista u objeto.

    POR QUÉ HACE FALTA: 'primero()' descarta objetos y listas a propósito —un campo que
    debería ser un dato suelto y llega como objeto es señal de ruta equivocada—. Pero el
    bloque de transporte de OHIP ES un objeto, con el tipo, la descripción, la hora y el
    transportista repartidos en campos cuyo nombre cambia entre instalaciones.

    Antes de esto, las rutas de transporte apuntaban a ese objeto y 'primero()' lo
    descartaba, así que el punto de embarque quedaba vacío SIEMPRE y nadie se enteraba:
    no da error, da una reserva sin punto, que recepción tiene que confirmar a mano una
    por una. Juntando el texto de dentro, el detector encuentra "Sierpe" o "Drake" esté
    en el campo que esté.
    """
    if valor is None or profundidad > 4:
        return ""
    if isinstance(valor, dict):
        return " ".join(t for t in (_texto_de(v, profundidad + 1)
                                    for v in valor.values()) if t)
    if isinstance(valor, (list, tuple)):
        return " ".join(t for t in (_texto_de(v, profundidad + 1)
                                    for v in valor) if t)
    if isinstance(valor, bool):
        return ""          # un true/false no es texto que nombre un lugar
    return str(valor).strip()


def texto_por_rutas(dato, rutas):
    """El texto de la primera ruta que traiga algo, aplanando objetos y listas."""
    for ruta in rutas:
        valores = leer(dato, ruta)
        if not valores:
            continue
        texto = _texto_de(valores).strip()
        if texto:
            return texto
    return None


def numero_de_confirmacion(reserva):
    """El identificador de la reserva. Lo usa opera_cloud para no repetir páginas."""
    v = campo(reserva, "conf_no")
    return str(v).strip() if v else None


# ---------------------------------------------------------------------------
# Conversiones
# ---------------------------------------------------------------------------

def fecha_lodge(iso):
    """'2026-08-10' -> '10-08-26', que es como guarda las fechas el sistema."""
    if not iso:
        return None
    texto = str(iso)[:10]
    try:
        d = datetime.date.fromisoformat(texto)
    except ValueError:
        return None
    return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"


def estado_lodge(estado_opera):
    if not estado_opera:
        return "POR INGRESAR"
    clave = re.sub(r"[^A-Z ]", "", str(estado_opera).upper()).strip()
    return ESTADOS.get(clave, ESTADOS.get(clave.replace(" ", ""), "POR INGRESAR"))


def _entero(v, por_defecto=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return por_defecto


def _punto_de_embarque(texto):
    """(punto_confirmado, texto_sin_confirmar) a partir de texto libre.

    Solo se da por bueno lo que nombra un punto conocido. Todo lo demás entra como
    "sin confirmar" y genera una tarea para recepción, igual que con el PDF: enviar
    un bote al lugar equivocado es un error caro y no se decide por adivinanza.
    """
    if not texto:
        return None, None
    sin_acentos = (str(texto).upper()
                   .replace("Í", "I").replace("Á", "A").replace("É", "E")
                   .replace("Ó", "O").replace("Ú", "U"))
    for palabra, punto in PUNTOS.items():
        if palabra in sin_acentos:
            return punto, None
    return None, str(texto).strip()[:200]


def _hora(texto):
    """Extrae 'HH:MM' de un texto o de una fecha-hora ISO."""
    if not texto:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", str(texto))
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


# Cómo se junta apellido y nombre. Es 'APELLIDO/NOMBRE' porque es EXACTAMENTE lo que
# produce el PDF del PMS: comprobado, 783 de 783 reservas de la base real usan esa forma.
#
# Antes aquí se armaba 'APELLIDO, NOMBRE'. No daba error, y por eso era peor: en cuanto
# se encendiera Opera, la base habría quedado con dos estilos de nombre a la vez, y los
# reportes y las hojas del día se verían a medias de una forma y a medias de la otra.
# Todo este módulo existe para producir el mismo diccionario que el PDF; el nombre es
# parte de eso.
def _unir_nombre(apellido, pila):
    return "/".join(p for p in ((apellido or "").strip(), (pila or "").strip()) if p)


def _nombre_titular(reserva):
    apellido = primero(reserva, RUTAS_NOMBRE_APELLIDO, "") or ""
    pila = primero(reserva, RUTAS_NOMBRE_PILA, "") or ""
    return _unir_nombre(apellido, pila) or None


def _acompanantes(reserva):
    gente = []
    for ruta in RUTAS_ACOMPANANTES:
        for p in leer(reserva, ruta):
            if not isinstance(p, dict):
                continue
            nombre = _unir_nombre(p.get("surname"), p.get("givenName"))
            if nombre and nombre not in [g["nombre"] for g in gente]:
                gente.append({"nombre": nombre, "pasaporte": None})
    return gente


def _operacion(reserva, arr_date_iso):
    """Los tours con su día, en la forma que espera el importador.

    El importador convierte el día del mes a fecha usando la llegada como referencia,
    igual que con el PDF. Si el paquete no trae fecha, se le asigna el día de llegada:
    aparece en la agenda para que recepción lo ubique, en vez de perderse.
    """
    nombres = leer_pares(reserva, RUTAS_PAQUETES_NOMBRE, RUTAS_PAQUETES_FECHA)
    operacion = []
    for nombre, fecha in nombres:
        dia = None
        if fecha:
            try:
                dia = datetime.date.fromisoformat(str(fecha)[:10]).day
            except ValueError:
                dia = None
        if dia is None and arr_date_iso:
            try:
                dia = datetime.date.fromisoformat(arr_date_iso[:10]).day
            except ValueError:
                dia = None
        if dia is None:
            continue
        operacion.append({"dia": str(dia), "tour": str(nombre).strip().upper(),
                          "conf_entrada": None})
    return operacion


def leer_pares(reserva, rutas_nombre, rutas_fecha):
    """Empareja cada paquete con su fecha por posición.

    Van emparejados porque Opera devuelve ambos como listas paralelas dentro del
    mismo bloque. Si vienen de largos distintos, el nombre manda y la fecha se deja
    vacía: perder la fecha de un tour es recuperable, perder el tour no.
    """
    nombres = todos(reserva, rutas_nombre)
    fechas = todos(reserva, rutas_fecha)
    pares = []
    for i, nombre in enumerate(nombres):
        pares.append((nombre, fechas[i] if i < len(fechas) else None))
    return pares


# ---------------------------------------------------------------------------
# Mapeo
# ---------------------------------------------------------------------------

def mapear(cruda):
    """Una reserva de Opera al formato del sistema. None si no es utilizable.

    Se descarta la que no tenga número de confirmación o fecha de llegada: son la
    llave y el eje de todo lo demás. Cargarla a medias ensuciaría la base con una
    reserva que ninguna pantalla podría mostrar bien.
    """
    conf_no = numero_de_confirmacion(cruda)
    arr_iso = campo(cruda, "arr_date")
    arr = fecha_lodge(arr_iso)
    if not conf_no or not arr:
        return None

    textos = todos(cruda, RUTAS_TEXTOS)
    notas = " ".join(textos)
    paquetes = [n for n, _ in leer_pares(cruda, RUTAS_PAQUETES_NOMBRE, RUTAS_PAQUETES_FECHA)]
    adicionales = ", ".join(paquetes)

    llegada = texto_por_rutas(cruda, RUTAS_TRANSPORTE_LLEGADA)
    salida = texto_por_rutas(cruda, RUTAS_TRANSPORTE_SALIDA)
    p_ent, p_ent_dudoso = _punto_de_embarque(llegada)
    p_sal, p_sal_dudoso = _punto_de_embarque(salida)

    return {
        "conf_no": conf_no,
        "room_no": str(campo(cruda, "room_no") or "").strip() or None,
        "nombre_principal": _nombre_titular(cruda) or "(sin nombre en Opera)",
        "company_travel_agent": campo(cruda, "company"),
        "arr_date": arr,
        "dep_date": fecha_lodge(campo(cruda, "dep_date")),
        "arr_time": _hora(campo(cruda, "arr_time")),
        "room_type": campo(cruda, "room_type"),
        "adl": _entero(campo(cruda, "adl"), 0),
        "chl": _entero(campo(cruda, "chl"), 0),
        "rooms": _entero(campo(cruda, "rooms"), 1),
        "mkt_code": campo(cruda, "mkt_code"),
        "src_code": campo(cruda, "src_code"),
        "res_status": estado_lodge(campo(cruda, "estado")),
        "block_code": campo(cruda, "block_code"),

        "adicionales_raw": adicionales,
        "notas": notas,
        # texto_completo es de donde salen amenidades y régimen de comidas. Se juntan
        # los paquetes con las notas para que los detectores vean lo mismo que veían
        # en el PDF, donde ambas cosas estaban en la misma hoja.
        "texto_completo": f"{adicionales} {notas}".strip(),
        "operacion": _operacion(cruda, arr_iso),
        "rooming": _acompanantes(cruda),

        "punto_entrada": p_ent,
        "punto_salida": p_sal,
        "punto_entrada_sin_confirmar": p_ent_dudoso,
        "punto_salida_sin_confirmar": p_sal_dudoso,
        "hora_vuelo_entrada": _hora(llegada),
        "hora_vuelo_salida": _hora(salida),
        "vuelo_entrada": None,
        "vuelo_salida": None,

        # Opera no marca "guía sugerido" ni vínculos de grupo como tales; si están,
        # están escritos en las notas y los detectores del importador los encuentran.
        "guia_sugerido": None,
        "vinculo_texto": notas or None,
    }


def mapear_lote(crudas):
    """(reservas utilizables, cuántas se descartaron)."""
    reservas, descartadas = [], 0
    for cruda in crudas:
        try:
            r = mapear(cruda)
        except Exception:
            r = None
        if r:
            reservas.append(r)
        else:
            descartadas += 1
    return reservas, descartadas


def diagnostico(crudas):
    """Resumen para revisar el mapeo antes de cargar nada.

    Dice qué campos se están quedando vacíos, que es la forma de darse cuenta de que
    una ruta no coincide con esta instalación de Opera. Un campo vacío en TODAS las
    reservas casi siempre significa ruta equivocada, no dato ausente.
    """
    reservas, descartadas = mapear_lote(crudas)
    interesan = ["room_no", "nombre_principal", "dep_date", "adl", "room_type",
                 "adicionales_raw", "notas", "punto_entrada", "operacion", "rooming"]
    vacios = {c: 0 for c in interesan}
    for r in reservas:
        for c in interesan:
            v = r.get(c)
            if v in (None, "", 0, [], {}):
                vacios[c] += 1

    lineas = [f"Recibidas de Opera: {len(crudas)}",
              f"Mapeadas: {len(reservas)}    Descartadas: {descartadas}", ""]
    if reservas:
        lineas.append("Campos vacios (de %d reservas):" % len(reservas))
        for c in interesan:
            n = vacios[c]
            marca = "  <-- REVISAR RUTA" if n == len(reservas) else ""
            lineas.append(f"  {c:<24} {n}{marca}")
        lineas.append("")
        r = reservas[0]
        lineas.append("Primera reserva mapeada (para comprobar la forma):")
        for c in ["conf_no", "room_no", "arr_date", "dep_date", "adl", "chl", "res_status"]:
            lineas.append(f"  {c:<24} {r.get(c)!r}")
        lineas.append(f"  {'tours':<24} {[o['tour'] for o in r['operacion']]!r}")
    return "\n".join(lineas)
