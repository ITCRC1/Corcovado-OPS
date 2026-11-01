"""
Qué es cada paquete de Opera: un tour, una comida, una amenidad o nada de eso.

DE DÓNDE SALE ESTO. La búsqueda de reservas de Opera no entrega los paquetes —Oracle
rechaza ese bloque—, pero **entrar a UNA reserva sí los devuelve, y con su fecha**:

    reservationPackages[].packageCode                      'CIS30'
    reservationPackages[].…primaryDetails.description       'Caño Island Snorkeling 30%'
    reservationPackages[].scheduleList[].consumptionDate    '2026-11-04'
    reservationPackages[].scheduleList[].totalQuantity      2

Ahí está la distribución de tours por día, que es lo que hasta ahora solo venía en el
PDF. Medido sobre 80 reservas reales: 69 códigos distintos y **ninguno sin fecha**.

CÓMO SE IDENTIFICA UN PAQUETE, Y POR QUÉ EN ESE ORDEN. El sufijo de los códigos es el
descuento comercial (`CIS20`, `CIS25`, `CIS30`, `CIS3027`, `CISWEB`…), así que la
tentación es quitarle los números y quedarse con la raíz. Pero eso solo es seguro
DESPUÉS de descartar los códigos exactos, por un caso real que lo rompe:

    DINP    = 'Cena para paquetes web o reservaciones'   -> es una COMIDA
    DINP30  = 'Cena Privada (setting especial y menú)'   -> es una AMENIDAD

Quitando el sufijo, `DINP30` se convertiría en `DINP` y una cena privada entraría como
una cena normal. No daría ningún error: la cocina simplemente no montaría la cena
privada, y nadie sabría por qué. De ahí el orden: primero el código exacto, después la
raíz.

Y LO QUE NO SE RECONOCE NO SE ADIVINA. Un código que no está en estas tablas se
devuelve como DESCONOCIDO para que quien llama genere un aviso. Es preferible que
recepción vea "llegó un paquete que no sé qué es" a que el sistema decida por su cuenta
y ponga el tour equivocado en la hoja del día.
"""
import re

# ---------------------------------------------------------------------------
# Tours
# ---------------------------------------------------------------------------
# Las equivalencias las confirmó la operación del lodge; no son deducciones. Cambiar
# una aquí la cambia en todo el sistema.
TOURS_POR_RAIZ = {
    # Caño Island Snorkeling -> SNORKEL (no ISLA: lo definió la operación)
    "CIS": "SNORKEL",
    "SCI": "SNORKEL",
    # San Pedrillo y Corcovado -> PNC. 'Hiking To Corcovado National Park' es la misma
    # estación de San Pedrillo con otro nombre comercial.
    "PNWALK": "PNC",
    "TSP": "PNC",
    "HCN": "PNC",
    "HCNP": "PNC",
    "CNP": "PNC",
    # La estación Sirena es otra cosa y tiene su propio código.
    "TSMC": "SIRENA",
    "CBE": "CLARO",
    "GTE": "CLARO",
    "NWP": "NW",
    # 'Early bird tour' es el avistamiento de aves de las 6 de la mañana.
    "CEBT": "PAJAREO",
    "EBTP": "PAJAREO",
    "SDPS": "BUCEO",
    # Estos dos aparecieron al medir 223 reservas: el aviso de "paquete sin reconocer"
    # los sacó a la luz en vez de dejarlos pasar en silencio. Es exactamente para lo
    # que existe ese aviso.
    "CNW": "NW",            # Complementary Night Walk
    "WWE": "BALLENAS",      # Whale Watching Experience
    # Y estos dos aparecieron el 11 de octubre, por la misma vía: el aviso los sacó a
    # la luz al sincronizar 264 reservas. Opera manda el nombre completo con el código,
    # y en los dos el nombre no deja lugar a dudas.
    "NQ":  "NW",            # 'Night Walk' — el mismo tour que NW y CNW
    "SPS": "SIRENA",        # 'Sirena Park Station (Private Tour)' — ver SIEMPRE_PRIVADOS
}

# ---------------------------------------------------------------------------
# El catálogo de abreviaturas 2027
# ---------------------------------------------------------------------------
# 23 códigos base, con el nombre estandarizado que fijó el lodge. Sirven para dos cosas:
# traducir el código al tour que el sistema ya opera, y darle a cada uno un nombre
# legible en pantalla en vez de tres letras.
#
# La columna del medio es la EQUIVALENCIA con el catálogo actual, y está puesta solo
# donde el propio documento la deja sin ambigüedad —dice el nombre completo del tour en
# español y en inglés—. Donde no hay equivalente, va None y el código entra al catálogo
# como un tour nuevo: es mejor un tour nuevo sin horario, que recepción completa, que
# meterlo dentro de otro y que la hoja del día mande el bote equivocado.
#
# (código, equivalente en el catálogo actual, nombre ES, nombre EN)
CATALOGO_2027 = [
    ("PNC", "PNC",       "Caminata al Parque Nacional Corcovado · San Pedrillo",
                          "Hiking to Corcovado National Park · San Pedrillo Station"),
    ("SIR", "SIRENA",    "Caminata al Parque Nacional Corcovado · Sirena",
                          "Hiking to Corcovado National Park · Sirena Station"),
    ("EBT", "PAJAREO",   "Tour de avistamiento de aves en los jardines",
                          "Early Bird Tour Around the Gardens"),
    ("HBR", "CABALGATA", "Excursión a caballo", "Horseback Riding"),
    ("CIS", "SNORKEL",   "Snorkeling en la Reserva Biológica Isla del Caño",
                          "Caño Island Snorkeling"),
    ("CID", "BUCEO",     "Buceo en la Reserva Biológica Isla del Caño",
                          "Caño Island Scuba Diving"),
    ("MGS", "MANGLAR",   "Tour al manglar de Sierpe", "Sierpe Mangrove Tour"),
    ("WDM", "BALLENAS",  "Experiencia de monitoreo de ballenas y delfines",
                          "Whale and Dolphin Monitoring Experience"),
    ("CBE", "CLARO",     "Expedición a Claro del Bosque", "Claro del Bosque Expedition"),
    ("TNE", "TREENET",   "Experiencia Tree Net", "Tree Net Experience"),
    ("NW",  "NW",        "Caminata nocturna", "Night Walk"),
    ("GTT", "GTT",       "Experiencia Garden to Table", "Garden to Table Experience"),
    ("SFH", "PESCA",     "Pesca deportiva · medio día", "Sportfishing · Half Day"),

    # KSJ es el San Josecito que el lodge YA hace: mismo destino y mismo tour, con el
    # nombre nuevo. Entró un día como tour aparte y eso lo partía en dos —una salida
    # «KSJ» sin ficha de itinerario junto a la de siempre—, que es justo lo que la tabla
    # de equivalencias existe para evitar.
    ("KSJ", "SAN JOSECITO", "Kayak a San Josecito", "Kayak to San Josecito"),

    # Sin equivalente en el catálogo actual: entran como tours nuevos.
    # El documento lo dice expresamente: «Actividad distinta de CID; no requiere usar el
    # mismo código». Por eso NO se mapea a BUCEO.
    ("DSD", None, "Discovery Scuba Diving", "Discovery Scuba Diving"),
    ("SFF", None, "Pesca deportiva · día completo", "Sportfishing · Full Day"),
    ("CLW", None, "Pared de escalada", "Climbing Wall"),
    ("HDA", None, "Media jornada de aventura", "Half-Day Adventure"),
    ("NGW", None, "Caminata en los senderos del hotel", "Naturalist Garden Walk"),
]

# Servicios que SOLO se venden en privado. El comunicado lo dice expresamente de la pesca
# deportiva: «se comercializan únicamente en modalidad privada. Por lo tanto, no es
# necesario que lleven el prefijo de PRV».
#
# Hay que tenerlo en cuenta al LEER: sin esto, una reserva que dice «SFF» a secas queda
# registrada como servicio compartido, y en la hoja del día se ve una salida abierta
# donde hay un charter de una sola familia. Si además trae el prefijo PRV, no cambia
# nada: ya lo era.
# SPS se suma por su propio nombre: Opera lo manda como «Sirena Park Station (Private
# Tour)». Sin esto, la caminata a Sirena de una familia saldría en la hoja del día como
# una salida abierta y recepción podría sentar a otros huéspedes en ese bote.
#
# Marcarlo privado NO lo convierte en otro tour: la modalidad se guarda aparte, por lo
# que dice el comentario de descomponer() —si fuera otro tour, la hoja del día mostraría
# dos salidas donde hay una—. Por eso no hace falta un «SIRENA PRIVADO» en el catálogo.
SIEMPRE_PRIVADOS = {"SFH", "SFF", "SPS"}

# Códigos del catálogo que NO son un tour de la agenda.
#
# MGX es el caso que el documento subraya: «Incluido en traslado; no tarifado como tour
# separado», y «no usar MGS y MGX como sinónimos». Tratarlo como tour pondría una salida
# de manglar en la hoja del día que no existe, con su guía y su bote apartados.
TRASLADOS_2027 = {
    "MGX": "Experiencia de manglar durante el traslado Sierpe-CWL",
    "TT":  "Transporte terrestre",
    "BT":  "Transporte en bote",
    "TRB": "Trasbordo en bote",
}

# Nombre legible de cada código base, para las pantallas.
NOMBRES_2027 = {c: es for c, _, es, _ in CATALOGO_2027}
NOMBRES_2027.update(TRASLADOS_2027)
NOMBRES_EN_2027 = {c: en for c, _, _, en in CATALOGO_2027}

# Las tablas se completan más abajo, cuando SIN_OPERACION_POR_RAIZ ya existe.

# ---------------------------------------------------------------------------
# Comidas -> de aquí sale el régimen
# ---------------------------------------------------------------------------
COMIDAS_POR_RAIZ = {
    "BRF": "desayuno", "BKF": "desayuno", "BRFP": "desayuno",
    "LUN": "almuerzo", "LUNP": "almuerzo",
    "DIN": "cena", "DINP": "cena",
}

# ---------------------------------------------------------------------------
# Amenidades. El nombre tiene que coincidir EXACTO con amenidad_catalogo, porque de
# ese nombre salen la tarea automática y el departamento responsable.
# ---------------------------------------------------------------------------
AMENIDADES_EXACTAS = {
    "DINP30": "Cena privada",
    # 'Welcome Gift' no tiene un equivalente literal en el catálogo. Se usa la
    # 'Tarjeta de bienvenida', que es la que va a Recepción antes del check-in. Si en
    # el lodge el welcome gift es otra cosa —el vino o las frutas—, se cambia AQUÍ y
    # queda cambiado en todo el sistema.
    "WELG30": "Tarjeta de bienvenida",
}

# ---------------------------------------------------------------------------
# Lo que no es operación: tarifas, impuestos, traslados y cortesías de facturación.
# Se reconocen a propósito para NO tratarlos como desconocidos y no llenar de avisos.
# ---------------------------------------------------------------------------
SIN_OPERACION_POR_RAIZ = {
    # Impuesto de sostenibilidad
    "SF": "tarifa", "SFAG": "tarifa", "SFP": "tarifa", "SFFNP": "tarifa",
    # Traslados. Traen el DÍA del bote, no el punto (Sierpe o Drake), así que no
    # alcanzan para deducir el punto de embarque: eso sigue viniendo del PDF.
    "TRFS": "traslado", "TFS": "traslado", "TRA": "traslado", "TRAP": "traslado",
    "TRFSFREE": "traslado",
    # Cortesías de facturación
    "RFREE": "cortesia", "F&BFREE": "cortesia",
    # Experiencia gastronómica: no es tour ni amenidad del catálogo
    "CEX": "gastronomia",
}

# Códigos que sí son un servicio pero cuya equivalencia NO está definida. Se listan
# para que el aviso diga algo útil en vez de "código raro".
POR_DEFINIR = {
    "RFDP": "RainForest Delight PKG — paquete que agrupa varios servicios",
    "TOURFREE": "Tour Complementario — no dice cuál",
}

TIPOS = ("tour", "comida", "amenidad", "traslado", "tarifa", "cortesia",
         "gastronomia", "desconocido")

# Se suma el catálogo 2027 a las tablas de siempre, ahora que todas existen.
#
# Los que tienen equivalente apuntan al tour que el sistema ya opera. Los que no, se
# mapean a sí mismos: el tour existe con ese código y entra al catálogo en init_db. Sin
# esto saldrían como desconocidos y esas reservas no generarían su salida.
TOURS_POR_RAIZ.update({c: (eq or c) for c, eq, _, _ in CATALOGO_2027})
SIN_OPERACION_POR_RAIZ.update({c: "traslado" for c in TRASLADOS_2027})


# Sufijos de TARIFA: dicen a qué precio se vende, no qué se vende.
#
#   KID   tarifa de niño       'BRF3027KID' = Breakfast Included NIÑO 30%
#   AGY   tarifa de agencia    'CIS3027KID' = Cano Island Snorkeling tour 30% agencia
#
# Aparecieron al reabrir la temporada, el 1 de noviembre. OJO: salen del plan tarifario de
# la reserva, no de que haya un niño alojado — se midieron las 10 reservas que los traen y
# las 10 dicen childCount 0 en Opera. Así que no sirven para contar gente; solo dicen qué
# está incluido.
#
# Y eso es justamente lo que se perdía mientras no se entendían. En esas 10 reservas las
# TRES comidas venían con el sufijo, así que ninguna se reconocía y el régimen quedaba en
# blanco: la pantalla no sabía que era pensión completa. Lo mismo con 'CIS3027KID' y
# 'TSP30KID' —el snorkel de Isla del Caño y la caminata a San Pedrillo—, que no llegaban a
# la lista de tours vendidos.
#
# Van en su propia tabla y se quitan ANTES que el descuento, porque en el código van
# después: 'BRF3027KID' es BRF + 3027 + KID.
_MODIFICADORES = re.compile(r"(?:KID|AGY)$")
_DESCUENTO = re.compile(r"(?:WEB|\d{2,4})$")


def raiz(codigo):
    """'CIS30' -> 'CIS', 'BRF3027KID' -> 'BRF'. Le quita lo que no cambia el servicio.

    Dos capas, cada una de UNA pasada, y ninguna deja la raíz vacía:

      1. El modificador de tarifa del final: KID (niño) o AGY (agencia).
      2. El descuento: 20, 25, 30, 35, 2527, 3027 y WEB.

    Ni el precio ni para quién es cambian QUÉ es: el desayuno de un niño sigue siendo
    desayuno y su snorkel sigue ocupando un asiento en el bote.
    """
    limpio = (codigo or "").strip().upper()
    sin_modificador = _MODIFICADORES.sub("", limpio) or limpio
    sin_descuento = _DESCUENTO.sub("", sin_modificador) or sin_modificador
    return sin_descuento or limpio


# ---------------------------------------------------------------------------
# La nomenclatura nueva: prefijos de modalidad
# ---------------------------------------------------------------------------
# El catálogo de abreviaturas 2027 del lodge define cuatro formas para cada tour:
#
#     PNC              regular / compartido
#     C-PNC            cortesía (Complementary) compartida
#     PRV-PNC          privado, con cargo
#     PRV|CPL-PNC      privado y además cortesía
#
# YA SE ESTÁN USANDO. En las reservas de Opera de hoy aparece
# «PAQUETE 4D/3N+PENSION COMPLETA CPL C-BT+C-CIS+C-NGW»: tres códigos con prefijo. Sin
# entenderlos, el sistema los daba por DESCONOCIDOS —lo que es correcto, mejor avisar
# que adivinar— pero esas reservas se quedaban sin sus tours en la hoja del día.
#
# El documento escribe el cuarto caso de dos maneras: 'PRV|CPL-PNC' en la tabla de
# reglas y 'PRV|CPLPNC' en la tabla maestra. Se aceptan las dos, y también 'PRV|C-'.
# Discutir cuál es la buena no le sirve a nadie; lo que sirve es que ninguna se pierda.
_PREFIJOS = re.compile(
    r"^(?:(?P<prv>PRV)\s*\|\s*(?P<cpl1>CPL|C)-?|"       # PRV|CPL-  PRV|C-  PRV|CPL
    r"(?P<prv2>PRV)-|"                                   # PRV-
    r"(?P<cpl2>CPL|C)-)",                                # C-  CPL-
    re.IGNORECASE)


def descomponer(codigo):
    """'PRV|CPL-PNC' -> ('PNC', privado=True, cortesia=True).

    Devuelve (base, privado, cortesia). La base sale con el sufijo de descuento ya
    quitado, para que entre en las mismas tablas que el resto.

    El prefijo no cambia QUÉ tour es: un PNC privado sigue siendo la caminata a San
    Pedrillo, con su horario, su bote y su entrada del SINAC. Cambia cómo se opera y
    cómo se cobra, y eso se guarda aparte en vez de convertirlo en otro tour — si fuera
    otro tour, la hoja del día mostraría dos salidas donde hay una.
    """
    limpio = (codigo or "").strip().upper()
    m = _PREFIJOS.match(limpio)
    if not m:
        base = raiz(limpio)
        return base, base in SIEMPRE_PRIVADOS, False
    privado = bool(m.group("prv") or m.group("prv2"))
    cortesia = bool(m.group("cpl1") or m.group("cpl2"))
    resto = limpio[m.end():].strip("-| ")
    if not resto:                      # era solo el prefijo: no se inventa una base
        return raiz(limpio), False, False
    base = raiz(resto)
    # La pesca deportiva es privada aunque nadie escriba PRV. Ver SIEMPRE_PRIVADOS.
    return base, privado or base in SIEMPRE_PRIVADOS, cortesia


def clasificar(codigo, descripcion=""):
    """Qué es este paquete.

    Devuelve {'tipo', 'valor', 'codigo', 'descripcion'}:
      tipo 'tour'     -> valor = código del tour del catálogo del lodge
      tipo 'comida'   -> valor = 'desayuno' | 'almuerzo' | 'cena'
      tipo 'amenidad' -> valor = nombre exacto de amenidad_catalogo
      tipo 'traslado' | 'tarifa' | 'cortesia' | 'gastronomia' -> valor = None
      tipo 'desconocido' -> valor = None, y quien llama debe avisar

    El orden importa: primero el código EXACTO (por DINP vs DINP30), después la raíz.
    """
    limpio = (codigo or "").strip().upper()
    # La modalidad va SIEMPRE en la respuesta, sea cual sea el tipo: un traslado también
    # puede venir como C-BT, y quien factura necesita saber que es cortesía.
    r, privado, cortesia = descomponer(limpio)
    base = {"codigo": limpio, "descripcion": (descripcion or "").strip(),
            "base": r, "privado": privado, "cortesia": cortesia}

    if limpio in AMENIDADES_EXACTAS:
        return {**base, "tipo": "amenidad", "valor": AMENIDADES_EXACTAS[limpio]}

    if r in TOURS_POR_RAIZ:
        return {**base, "tipo": "tour", "valor": TOURS_POR_RAIZ[r]}
    if r in COMIDAS_POR_RAIZ:
        return {**base, "tipo": "comida", "valor": COMIDAS_POR_RAIZ[r]}
    if r in SIN_OPERACION_POR_RAIZ:
        return {**base, "tipo": SIN_OPERACION_POR_RAIZ[r], "valor": None}

    return {**base, "tipo": "desconocido", "valor": None,
            "nota": POR_DEFINIR.get(limpio) or POR_DEFINIR.get(r) or ""}


def nombre_de(codigo, idioma="es"):
    """El nombre legible de un código, con su modalidad. '' si no se reconoce.

    'C-PNC' -> 'Caminata al Parque Nacional Corcovado · San Pedrillo (cortesía)'
    """
    r, privado, cortesia = descomponer(codigo)
    tabla = NOMBRES_EN_2027 if str(idioma).lower().startswith("en") else NOMBRES_2027
    nombre = tabla.get(r) or NOMBRES_2027.get(r) or ""
    if not nombre:
        return ""
    marcas = []
    if privado:
        marcas.append("privado" if tabla is NOMBRES_2027 else "private")
    if cortesia:
        marcas.append("cortesía" if tabla is NOMBRES_2027 else "complimentary")
    return f"{nombre} ({' · '.join(marcas)})" if marcas else nombre


def regimen_de(comidas):
    """El régimen del lodge a partir de las comidas que trae la reserva.

    'comidas' es un conjunto con 'desayuno', 'almuerzo' y/o 'cena'.

    Devuelve None cuando no hay ninguna, que NO significa "no tiene comidas": significa
    que la reserva no las trae como paquete. Igual que con el PDF, es mejor no saberlo
    que afirmar algo falso.
    """
    tiene = set(comidas or ())
    if {"desayuno", "almuerzo", "cena"} <= tiene:
        return "PENSION_COMPLETA"
    if {"desayuno", "cena"} <= tiene:
        return "DESAYUNO_CENA"
    if "desayuno" in tiene:
        return "SOLO_DESAYUNO"
    return None


def leer_paquetes(reserva):
    """Los paquetes de una reserva de Opera, ya clasificados y con su fecha.

    Espera el nodo de UNA reserva (el que devuelve
    GET /rsv/v1/hotels/{hotel}/reservations/{id}).

    Devuelve {'tours', 'comidas', 'amenidades', 'traslados', 'desconocidos'}:
      tours       -> [{'tour', 'fecha', 'pax', 'codigo'}]

    OJO CON LA FECHA DE LOS TOURS: es la `consumptionDate` del paquete, que es la
    fecha de FACTURACIÓN y NO la del tour. Medido en 15 reservas con itinerario
    escrito: no coincidió ninguna —el paquete cae el día de llegada o el último de la
    estadía—. Quien llama NO debe usarla para agendar; el día real está en el
    itinerario de las Reservation Notes. Aquí se devuelve porque sirve para saber qué
    tours están vendidos y para el régimen de comidas.
      comidas     -> {'desayuno', 'cena', …}
      amenidades  -> [{'amenidad', 'fecha', 'codigo'}]
      traslados   -> [fechas] (el día del bote; el punto no viene)
      desconocidos-> [{'codigo', 'descripcion', 'nota'}]
    """
    paquetes = (reserva or {}).get("reservationPackages") or []
    tours, amenidades, traslados, desconocidos = [], [], [], []
    comidas = set()
    vistos_desconocidos = set()

    for p in paquetes:
        if not isinstance(p, dict):
            continue
        codigo = p.get("packageCode")
        cabecera = p.get("packageHeaderType") or {}
        descripcion = ((cabecera.get("primaryDetails") or {}).get("description") or "")
        que_es = clasificar(codigo, descripcion)

        # Cada fecha del calendario del paquete es una ocurrencia distinta: un tour
        # dos días son dos tours, y una comida cada noche es la misma comida.
        horario = p.get("scheduleList") or []
        fechas = []
        for h in horario:
            if not isinstance(h, dict):
                continue
            fecha = h.get("consumptionDate") or h.get("reservationDate")
            if fecha:
                fechas.append((str(fecha)[:10], h.get("totalQuantity")))

        if que_es["tipo"] == "tour":
            for fecha, cantidad in fechas:
                tours.append({"tour": que_es["valor"], "fecha": fecha,
                              "pax": cantidad, "codigo": que_es["codigo"]})
        elif que_es["tipo"] == "comida":
            comidas.add(que_es["valor"])
        elif que_es["tipo"] == "amenidad":
            # De la amenidad interesa UNA fecha, no una por noche.
            fecha = fechas[0][0] if fechas else None
            amenidades.append({"amenidad": que_es["valor"], "fecha": fecha,
                               "codigo": que_es["codigo"]})
        elif que_es["tipo"] == "traslado":
            traslados.extend(f for f, _ in fechas)
        elif que_es["tipo"] == "desconocido":
            if que_es["codigo"] not in vistos_desconocidos:
                vistos_desconocidos.add(que_es["codigo"])
                desconocidos.append({"codigo": que_es["codigo"],
                                     "descripcion": que_es["descripcion"],
                                     "nota": que_es.get("nota") or ""})

    return {"tours": tours, "comidas": comidas, "amenidades": amenidades,
            "traslados": sorted(set(traslados)), "desconocidos": desconocidos}
