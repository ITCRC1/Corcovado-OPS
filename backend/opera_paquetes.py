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
}

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


def raiz(codigo):
    """'CIS30' -> 'CIS'. Le quita el sufijo de descuento del final.

    Los sufijos vistos en la propiedad: 20, 25, 30, 35, 2527, 3027 y WEB. Se quita
    UNO solo desde el final, y nunca si eso dejaría la raíz vacía.
    """
    limpio = (codigo or "").strip().upper()
    sin_sufijo = re.sub(r"(?:WEB|\d{2,4})$", "", limpio)
    return sin_sufijo or limpio


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
    base = {"codigo": limpio, "descripcion": (descripcion or "").strip()}

    if limpio in AMENIDADES_EXACTAS:
        return {**base, "tipo": "amenidad", "valor": AMENIDADES_EXACTAS[limpio]}

    r = raiz(limpio)
    if r in TOURS_POR_RAIZ:
        return {**base, "tipo": "tour", "valor": TOURS_POR_RAIZ[r]}
    if r in COMIDAS_POR_RAIZ:
        return {**base, "tipo": "comida", "valor": COMIDAS_POR_RAIZ[r]}
    if r in SIN_OPERACION_POR_RAIZ:
        return {**base, "tipo": SIN_OPERACION_POR_RAIZ[r], "valor": None}

    return {**base, "tipo": "desconocido", "valor": None,
            "nota": POR_DEFINIR.get(limpio) or POR_DEFINIR.get(r) or ""}


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
