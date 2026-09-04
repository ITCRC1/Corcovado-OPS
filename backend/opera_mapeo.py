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

# NOTA SOBRE EL ORDEN: gana la primera ruta que traiga algo, así que las rutas
# COMPROBADAS contra el OHIP de Corcovado (mtcu11pr, propiedad COWLCR) van primero y las
# demás quedan como respaldo para otra instalación. Ver estructura_*.txt en
# data/opera_muestras/, que es de donde salieron.
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
    # 'adultCount' es el que trae Corcovado; 'guestCounts.adults' es de otras versiones.
    "adl": [
        "roomStay.adultCount",
        "roomStay.guestCounts.adults",
        "guestCounts.adults",
    ],
    "chl": [
        "roomStay.childCount",
        "roomStay.guestCounts.children",
        "guestCounts.children",
    ],
    "rooms": [
        "roomStay.numberOfRooms",
        "roomStay.roomCount",
    ],
    # 'computedReservationStatus' va primero: es el que Opera calcula de verdad para el
    # día (RESERVED / INHOUSE / DEPARTED), mientras 'reservationStatus' puede quedarse en
    # el estado con que se creó la reserva.
    "estado": [
        "computedReservationStatus",
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
    # La agencia o empresa. En Corcovado llega en 'attachedProfiles[].name', junto con
    # los demás perfiles pegados a la reserva; el tipo va en 'reservationProfileType'.
    # Se filtra por tipo en _empresa() y no aquí, porque 'name' es el mismo campo para
    # todos los perfiles y hay que quedarse solo con los de empresa o agencia.
    "company": [
        "reservationProfiles[].profile.company.companyName",
        "reservationProfiles[].profile.customer.companyName",
        "travelAgent.name",
        "company.name",
    ],
    "block_code": [
        "roomStay.reservationBlock.blockIdList[].id",
        "roomStay.blockCode",
        "blockCode",
    ],
    # El idioma del huésped, tal como lo tiene el PMS. Sirve para el itinerario y para
    # el formulario del spa: hoy eso se pone a mano.
    "idioma": [
        "reservationGuest.language",
        "reservationGuests[].profileInfo.profile.customer.language",
    ],
    "email": [
        "reservationGuest.email",
        "reservationGuests[].profileInfo.profile.customer.email",
    ],
    "telefono": [
        "reservationGuest.phoneNumber",
        "reservationGuests[].profileInfo.profile.customer.phoneNumber",
    ],
    # Cuándo se modificó por última vez, según Opera. Comprobado en Corcovado: llega
    # como '2026-08-26 18:16:10.0' —con hora—, y entre 62 reservas había 49 marcas
    # distintas, así que sirve para saber cuáles cambiaron de verdad.
    #
    # Importa porque Opera NO deja filtrar por fecha de modificación: se probaron
    # 'modifiedFromDate', 'modifiedStartDate' y 'lastModifiedDate' y los tres se
    # ignoran EN SILENCIO —responden 200 y devuelven reservas de 2025 ya salidas—.
    # Así que la comparación hay que hacerla de este lado.
    "modificado_en": [
        "lastModifyDateTime",
        "lastModifiedDateTime",
        "roomStay.lastModifyDateTime",
    ],
    "creado_en_opera": [
        "createDateTime",
        "createBusinessDate",
    ],
}

# Los perfiles pegados a la reserva que SÍ son una empresa o agencia, EN ORDEN DE
# PREFERENCIA. Los demás ('GUEST', 'BILLING'…) son el propio huésped o la forma de pago.
#
# El orden hace falta: medido sobre las 62 reservas reales de septiembre, Opera pega 84
# perfiles —47 'Company', 29 'Group', 8 'TravelAgent'—, así que la mayoría de reservas
# trae más de uno. Quedarse con "el primero que aparezca" haría que una misma agencia
# saliera unas veces con su nombre y otras con el del grupo, sin ningún patrón.
# La agencia es el dato que recepción usa, así que va primero; 'Group' es el nombre del
# bloque y queda de último recurso.
TIPOS_DE_EMPRESA = ["TRAVELAGENT", "COMPANY", "SOURCE", "GROUP"]

# El nombre del titular. Se busca aparte porque en Opera viene partido en piezas y
# hay que recomponerlo respetando el orden.
#
# 'reservationGuest.surname' va primero porque es la que usa Corcovado: aquí el nombre
# NO viene dentro de un perfil ni partido en una lista 'personName[]', viene plano en la
# reserva. Con solo las rutas de abajo el nombre salía vacío y la reserva entraba como
# "(sin nombre en Opera)".
RUTAS_NOMBRE_APELLIDO = [
    "reservationGuest.surname",
    "reservationGuests[].profileInfo.profile.customer.personName[].surname",
    "reservationProfiles[].profile.customer.personName[].surname",
    "guest.personName[].surname",
    "profile.customer.personName[].surname",
]
RUTAS_NOMBRE_PILA = [
    "reservationGuest.givenName",
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
    "reservationGuest.accompanyGuests[]",
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


def _empresa(reserva):
    """La agencia o empresa de la reserva.

    Se prueban primero las rutas directas de RUTAS['company']. Si no dan nada, se
    recorre 'attachedProfiles[]' —que es lo que trae Corcovado— y se toma el nombre
    del primer perfil cuyo tipo sea de empresa o agencia. Hay que filtrar por tipo
    porque en esa misma lista viene también el perfil del propio huésped: sin filtro,
    la columna de agencia quedaría con el nombre del huésped repetido.
    """
    directo = campo(reserva, "company")
    if directo:
        return directo
    por_tipo = {}
    for p in leer(reserva, "attachedProfiles[]"):
        if not isinstance(p, dict):
            continue
        tipo = str(p.get("reservationProfileType") or "").upper().replace(" ", "")
        nombre = str(p.get("name") or "").strip()
        if nombre and tipo in TIPOS_DE_EMPRESA:
            por_tipo.setdefault(tipo, nombre)
    for tipo in TIPOS_DE_EMPRESA:
        if tipo in por_tipo:
            return por_tipo[tipo]
    return None


def _acompanantes(reserva):
    """Los demás huéspedes de la reserva.

    Se aceptan los dos juegos de nombres de campo que usa Opera según el bloque:
    'surname'/'givenName' en los perfiles, y 'lastName'/'firstName' en la lista de
    acompañantes de la reserva —que es la que trae Corcovado—.
    """
    gente = []
    for ruta in RUTAS_ACOMPANANTES:
        for p in leer(reserva, ruta):
            if not isinstance(p, dict):
                continue
            apellido = p.get("surname") or p.get("lastName")
            pila = p.get("givenName") or p.get("firstName")
            nombre = _unir_nombre(apellido, pila)
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

def es_cuarto_ficticio(cruda):
    """Si la reserva es de una habitación que no existe en el hotel.

    Opera usa 'pseudo rooms' —tipo PM, "posting master"— para grupos, cargos comunes
    y facturación. No son huéspedes: no hay nadie a quien llevarle una amenidad ni
    quien salga a un tour.

    HAY QUE FILTRARLAS. Medido sobre las 62 reservas reales de septiembre: 6 vienen
    marcadas así, y una de ellas —cuarto 9000, estado Reserved— entraba a la agenda
    como una llegada normal del 5 de septiembre con 0 adultos. Recepción vería un
    cuarto que no está en el hotel, y no tendría forma de saber por qué.
    """
    rs = cruda.get("roomStay") if isinstance(cruda, dict) else None
    return bool(isinstance(rs, dict) and rs.get("pseudoRoom"))


def mapear(cruda):
    """Una reserva de Opera al formato del sistema. None si no es utilizable.

    Se descarta la que no tenga número de confirmación o fecha de llegada: son la
    llave y el eje de todo lo demás. Cargarla a medias ensuciaría la base con una
    reserva que ninguna pantalla podría mostrar bien.
    """
    if es_cuarto_ficticio(cruda):
        return None

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
        "company_travel_agent": _empresa(cruda),
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
        # Para que el ciclo automático sepa qué cambió sin repreguntar todo.
        "opera_modificado_en": campo(cruda, "modificado_en"),
        # Con qué id se le pide el detalle a Opera (los paquetes, o sea los tours).
        # No es una columna de la base: el cargador ignora las llaves que no conoce.
        "opera_id": id_de_reserva(cruda),

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


def id_de_reserva(cruda):
    """El id interno con el que Opera identifica la reserva para consultarla.

    Es el mismo valor que el número de confirmación en esta propiedad, pero se saca del
    campo de tipo 'Reservation' a propósito: si algún día dejan de coincidir, el
    detalle se pediría con el número equivocado y volvería la reserva de otro huésped.
    """
    for i in (cruda.get("reservationIdList") or []) if isinstance(cruda, dict) else []:
        if isinstance(i, dict) and str(i.get("type") or "").lower() == "reservation":
            valor = str(i.get("id") or "").strip()
            if valor:
                return valor
    return numero_de_confirmacion(cruda)


RUTAS_NOTAS = [
    # Cómo llega el texto de las Reservation Notes. Comprobado en Corcovado.
    "comments[].comment.text.value",
    "comments[].comment.text",
    "comments[].text.value",
    "comments[].text",
    "reservationComments[].comment.text.value",
    "guestComments[].comment.text.value",
]


def texto_de_las_notas(detalle):
    """El texto de las Reservation Notes de esta reserva, todo junto.

    AQUÍ ESTÁ TODO lo que el PDF imprime: el paquete y el régimen, los tours con su
    día, el punto de embarque (Sierpe o Drake) con su vuelo y hora, el rooming con
    pasaportes y las notas libres —alergias, vínculos de grupo—.

    EL NOMBRE DEL BLOQUE ES 'Comments', NO 'ReservationComments'. Ese fue el error que
    costó dar por imposible la automatización: `ReservationComments` se rechaza con
    `400 GEN01346` y parece que la propiedad no expone las notas, cuando lo que no
    existe es ese nombre. Se probaron 70 nombres para encontrarlo.

    Se descarta la nota del área CASHIER: es el total y la fuente de la venta, no
    operación, y su texto ('Total $2,830.47') solo ensuciaría los detectores.
    """
    if not isinstance(detalle, dict):
        return ""
    partes = []
    for c in (detalle.get("comments") or []):
        if not isinstance(c, dict):
            continue
        com = c.get("comment") if isinstance(c.get("comment"), dict) else c
        area = str(com.get("notificationLocation") or com.get("commentOriginatorType")
                   or c.get("notificationLocation") or "").upper()
        if "CASHIER" in area:
            continue
        texto = com.get("text")
        if isinstance(texto, dict):
            texto = texto.get("value")
        if texto and str(texto).strip():
            partes.append(str(texto))
    return "\n".join(partes)


def incorporar_detalle(reserva, detalle):
    """Le agrega a una reserva ya mapeada lo que solo trae la consulta individual.

    Dos fuentes dentro del mismo detalle, y se complementan:

      1. Las RESERVATION NOTES, que traen lo mismo que el PDF y con el mismo formato:
         se leen con el MISMO lector (`pdf_parser.leer_texto_de_reserva`). De ahí salen
         el punto de embarque, el rooming con pasaportes, las notas y el itinerario
         escrito a mano.
      2. Los PAQUETES, que traen los tours con su fecha de consumo y la cantidad real
         de gente, además del régimen de comidas.

    **MANDA LA NOTA PARA LOS TOURS Y SUS FECHAS.** Esto se midió, y el resultado fue
    lo contrario de lo que parecía razonable: en 15 reservas con las dos cosas, la
    fecha del paquete NO coincidió NUNCA con la del itinerario.

        reserva 75067234, llega el 04-11
          la nota dice:    PNC el 05,  ISLA el 06
          los paquetes:    PNC el 04,  CLARO y SNORKEL el 07

    La `consumptionDate` del paquete es la fecha de FACTURACIÓN —cae el día de llegada
    o el último de la estadía—, no el día en que se hace el tour. Y el paquete tampoco
    usa los códigos del lodge: llama SNORKEL a lo que el itinerario llama ISLA.

    Los paquetes sirven para otras dos cosas, y ahí sí son la mejor fuente: el RÉGIMEN
    de comidas y las amenidades que Opera registra como servicio (la cena privada, el
    detalle de bienvenida). Además dicen QUÉ tours están vendidos, aunque no cuándo:
    eso queda en 'tours_vendidos', porque en 11 de 15 reservas el itinerario todavía no
    estaba escrito —los tours se reparten después de que entra la reserva—.

    Devuelve la lista de códigos de paquete que no se supieron identificar, para que
    quien llama avise: un paquete sin reconocer NO se adivina.

    Es aditivo por diseño: si el detalle no trae nada, la reserva queda exactamente
    como estaba en vez de vaciarse.
    """
    import opera_paquetes as op
    import pdf_parser

    # --- 1. Las notas, por el mismo lector que el PDF ---
    texto = texto_de_las_notas(detalle)
    if texto:
        leido_nota = pdf_parser.leer_texto_de_reserva(texto)
        # Solo se copia lo que la nota SÍ trae: un campo vacío en la nota no debe
        # borrar lo que ya había.
        for clave in ("punto_entrada", "punto_salida", "punto_entrada_sin_confirmar",
                      "punto_salida_sin_confirmar", "hora_vuelo_entrada",
                      "hora_vuelo_salida", "vuelo_entrada", "vuelo_salida",
                      "guia_sugerido", "vinculo_texto", "block_code"):
            if leido_nota.get(clave):
                reserva[clave] = leido_nota[clave]
        if leido_nota.get("rooming"):
            reserva["rooming"] = leido_nota["rooming"]
        if leido_nota.get("notas", "").strip():
            reserva["notas"] = leido_nota["notas"].strip()
        if leido_nota.get("adicionales_raw"):
            reserva["adicionales_raw"] = leido_nota["adicionales_raw"]
        if leido_nota.get("notas_operacion"):
            reserva["notas_operacion"] = leido_nota["notas_operacion"]
        if leido_nota.get("actividades_no_reconocidas"):
            reserva["actividades_no_reconocidas"] = leido_nota["actividades_no_reconocidas"]
        # El itinerario de la nota ('10: PNC 123456') es LA fuente de los tours: el día
        # correcto y el número de entrada del SINAC, que el paquete no tiene.
        # ¿La nota TIENE una sección de operación? Es distinto de que esté vacía.
        #
        #   Con itinerario escrito y sin tours  -> el huésped no tiene tours: se puede
        #                                          borrar lo que hubiera.
        #   Sin sección de operación            -> todavía no se la escribieron: no se
        #                                          sabe nada y no se toca lo que haya.
        #
        # Importa porque los tours se reparten DESPUÉS de que entra la reserva: medido,
        # 11 de 15 reservas de la ventana no tenían itinerario todavía.
        reserva["itinerario_leido"] = bool(leido_nota.get("operacion"))
        tours_de_nota = [o for o in (leido_nota.get("operacion") or []) if o.get("tour")]
        if tours_de_nota:
            reserva["operacion"] = tours_de_nota
            # 'adicionales_raw' es lo que las pantallas muestran como "adicionales" y
            # de donde el importador cruza los tours. Tiene que decir lo MISMO que el
            # itinerario: si dijera lo que traen los paquetes, mostraría SNORKEL para
            # una reserva cuyo itinerario dice PNC e ISLA.
            if not leido_nota.get("adicionales_raw"):
                reserva["adicionales_raw"] = ", ".join(
                    sorted({o["tour"] for o in tours_de_nota}))
        # Todo el texto, que es de donde el importador detecta amenidades y alergias.
        reserva["texto_nota"] = texto

    # --- 2. Los paquetes ---
    leido = op.leer_paquetes(detalle or {})

    # QUÉ tours están vendidos, sin fecha. NO van a la agenda: su 'consumptionDate' es
    # la fecha de facturación y pondría el bote en el día equivocado. Sirven para saber
    # que a esta reserva le falta repartir los tours, que es justo el trabajo que se
    # hace después de que entra la reserva.
    vendidos = sorted({t["tour"] for t in leido["tours"]})
    if vendidos:
        reserva["tours_vendidos"] = vendidos
        # Si la nota todavía no tiene itinerario, al menos que las pantallas muestren
        # qué compró el huésped en vez de quedar en blanco.
        if not reserva.get("adicionales_raw"):
            reserva["adicionales_raw"] = ", ".join(vendidos)

    regimen = op.regimen_de(leido["comidas"])
    if regimen:
        reserva["regimen"] = regimen
        # Se guarda aparte porque el importador vuelve a deducir el régimen del TEXTO
        # y sobreescribe esta llave. En Opera no hay texto, así que lo dejaría en
        # blanco: quien llama lo restaura después. Misma razón que con las amenidades.
        reserva["regimen_de_opera"] = regimen

    if leido["amenidades"]:
        reserva["amenidades_de_opera"] = leido["amenidades"]

    if leido["traslados"]:
        # Solo el DÍA del bote. El punto (Sierpe o Drake) no viene en el paquete, así
        # que no se deduce: inventarlo pondría a un huésped en el bote equivocado.
        reserva["dias_de_traslado"] = leido["traslados"]

    # De aquí salen las amenidades, las alergias y el régimen: es lo que el importador
    # lee. Va el texto ENTERO de la nota, no solo la sección de notas, porque el
    # huésped puede tener la alergia escrita arriba, junto al paquete, o al lado de su
    # nombre en el rooming. Es la misma razón por la que el PDF acumula todo el bloque.
    reserva["texto_completo"] = " ".join(
        x for x in (reserva.get("adicionales_raw") or "",
                    reserva.get("texto_nota") or reserva.get("notas") or "")
        if x).strip()

    return leido["desconocidos"]


def mapear_lote(crudas):
    """(reservas utilizables, cuántas se descartaron).

    Las de habitación ficticia NO cuentan como descartadas: dejarlas fuera es lo
    correcto, no una pérdida. Contarlas juntas haría que un ciclo normal informara
    "6 descartadas" y pareciera que algo va mal. Para verlas por separado está
    contar_lote().
    """
    reservas, descartadas = [], 0
    for cruda in crudas:
        if es_cuarto_ficticio(cruda):
            continue
        try:
            r = mapear(cruda)
        except Exception:
            r = None
        if r:
            reservas.append(r)
        else:
            descartadas += 1
    return reservas, descartadas


def contar_lote(crudas):
    """Cuántas son de habitación ficticia. Para informar sin alarmar."""
    return sum(1 for c in crudas if es_cuarto_ficticio(c))


# De qué bloque de Opera depende cada campo. Sirve para no acusar a la ruta de algo
# que en realidad es un bloque que Oracle no concede: son dos problemas distintos y se
# arreglan en sitios distintos —uno en este archivo, el otro con Oracle—.
# OJO CON LOS TOURS: no dependen de ningún bloque, así que NO están en esta tabla. La
# búsqueda de reservas nunca los trae —Oracle rechaza el bloque de paquetes—, pero
# entrar a UNA reserva sí los devuelve con su fecha. Por eso el diagnóstico los evalúa
# aparte, sobre reservas a las que ya se les pidió el detalle.
DEL_DETALLE = frozenset({"operacion", "adicionales_raw"})

BLOQUE_QUE_HACE_FALTA = {
    "notas": "ReservationComments",
    "punto_entrada": "ReservationTransportation",
    "punto_salida": "ReservationTransportation",
    "hora_vuelo_entrada": "ReservationTransportation",
    "hora_vuelo_salida": "ReservationTransportation",
}


def diagnostico(crudas, bloques=None, con_detalle=None):
    """Resumen para revisar el mapeo antes de cargar nada.

    Dice qué campos se están quedando vacíos. Un campo vacío en TODAS las reservas
    significa una de dos cosas, y conviene no confundirlas:

      - el bloque que trae ese dato no está concedido -> no se arregla con código;
      - el bloque sí llega pero la ruta no coincide   -> se arregla aquí, en RUTAS.

    'bloques' es la lista de bloques que la propiedad aceptó. Pasándola, cada campo
    vacío se explica por su causa real en vez de mandar a revisar una ruta correcta.

    'con_detalle' son reservas a las que ya se les incorporó el detalle individual (de
    donde salen los tours). Se usan ESAS en vez de volver a mapear, porque los tours no
    vienen en la búsqueda: sin esto el diagnóstico diría "0 tours" aunque los haya.
    """
    if con_detalle:
        reservas, descartadas = list(con_detalle), 0
    else:
        reservas, descartadas = mapear_lote(crudas)
    interesan = ["room_no", "nombre_principal", "dep_date", "adl", "room_type",
                 "adicionales_raw", "notas", "punto_entrada", "operacion", "rooming"]
    vacios = {c: 0 for c in interesan}
    for r in reservas:
        for c in interesan:
            v = r.get(c)
            if v in (None, "", 0, [], {}):
                vacios[c] += 1

    ficticias = contar_lote(crudas)
    lineas = [f"Recibidas de Opera: {len(crudas)}",
              f"Mapeadas: {len(reservas)}    Descartadas: {descartadas}"]
    if ficticias:
        lineas.append(f"Fuera por ser habitacion ficticia (tipo PM de Opera): {ficticias}"
                      "  <-- correcto, no son huespedes")
    lineas.append("")
    if reservas:
        lineas.append("Campos vacios (de %d reservas):" % len(reservas))
        for c in interesan:
            n = vacios[c]
            marca = ""
            if n == len(reservas):
                falta = BLOQUE_QUE_HACE_FALTA.get(c)
                if c in DEL_DETALLE and not con_detalle:
                    # No es un problema: la búsqueda no trae los tours y aquí no se
                    # pidió el detalle. Mandar a revisar una ruta correcta hace perder
                    # el tiempo en el lado equivocado.
                    marca = "  <-- se leen del detalle, no de la busqueda"
                elif bloques is not None and falta and falta not in bloques:
                    marca = f"  <-- Opera no da el bloque {falta}"
                else:
                    marca = "  <-- REVISAR RUTA"
            lineas.append(f"  {c:<24} {n}{marca}")
        lineas.append("")
        if con_detalle:
            total_tours = sum(len(x.get("operacion") or []) for x in reservas)
            con_tours = sum(1 for x in reservas if x.get("operacion"))
            lineas.append(f"Tours leidos del detalle de {len(reservas)} reservas: "
                          f"{total_tours} en {con_tours} reservas")
            regimenes = sorted({str(x.get("regimen")) for x in reservas})
            lineas.append(f"Regimenes deducidos de los paquetes: {regimenes}")
            lineas.append("")
        r = reservas[0]
        lineas.append("Primera reserva mapeada (para comprobar la forma):")
        for c in ["conf_no", "room_no", "arr_date", "dep_date", "adl", "chl",
                  "res_status", "regimen"]:
            lineas.append(f"  {c:<24} {r.get(c)!r}")
        tours = [(o.get("tour"), o.get("fecha_iso") or o.get("dia"))
                 for o in (r.get("operacion") or [])]
        lineas.append(f"  {'tours':<24} {tours!r}")
    return "\n".join(lineas)
