"""
Toma las reservas parseadas del PDF y las prepara para el panel de revisión:
- Cruza tours contra el catálogo
- Detecta vínculos de grupo (alta/media confianza)
- Deduplica entradas SINAC compartidas
- Detecta contradicciones (ej. tour opcional con entrada ya comprada)
"""
import re
from datetime import date
from pdf_parser import parse_reservations, cross_reference_tours

# Tours que requieren comprar entrada al SINAC con anticipación (incluye sus
# versiones privadas). Debe coincidir con requiere_entrada_sinac del catálogo.
TOURS_CON_ENTRADA_SINAC = {"PNC", "SIRENA", "ISLA", "SNORKEL", "BUCEO"}

CONTRADICTION_KEYWORDS = [
    "deciden en el hotel", "si desean agregar", "por confirmar",
    "en caso de que lo confirmen", "pendiente de confirmar",
]

INGRESO_KEYWORDS = ["entrada", "llegada", "check in", "check-in", "arribo", "recibir", "pre-registr"]
SALIDA_KEYWORDS = ["salida", "checkout", "check out", "check-out", "vuelo", "sansa", "traslado de salida", "despedir"]

# Cada amenidad del catálogo se detecta con varios patrones, porque el PDF la escribe
# de formas distintas ("AGREGAR SOFA CAMA", "COLOCAR SOFÁ CAMA EN LA HABITACIÓN",
# "5th wedding anniversary", "VIP experience package", etc.). Se usan expresiones
# regulares para tolerar acentos, plurales y palabras intermedias.
#
# CADA AMENIDAD SE BUSCA EN LOS DOS IDIOMAS. Con el PDF bastaba el español para casi
# todo, pero la conexión con Opera Cloud trae las notas tal como las escribe el PMS, y
# ahí vienen en inglés. Una amenidad que no se detecta no genera tarea: nadie pone el
# sofá cama y se descubre cuando el huésped llega. Medido sobre las 589 reservas con
# texto de la base real: agregar el inglés no cambia NINGUNA detección existente —solo
# caza lo que hoy se perdería.
AMENIDADES_PATRONES = [
    ("Sofá cama extra", r"sof[áa]\s*cama|sofa[\s-]*bed|extra\s+bed|rollaway|roll-away"),
    # Nota: se busca "cliente VIP" y no solo "VIP", porque varios paquetes comerciales
    # se llaman "VIP Experience Package" y eso no implica una amenidad que preparar.
    ("Luna de miel / cliente VIP", r"luna\s+de\s+miel|honeymoon|aniversario|anniversary|cliente\s+vip|hu[ée]sped\s+vip"),
    ("Decoración por cumpleaños", r"cumplea[ñn]os|birthday|decoraci[óo]n|decorat"),
    # La cena privada se escribe de muchas formas y con palabras en medio ("cena
    # romántica privada", "cena privada en la playa", "private candlelight dinner").
    # Importa detectarla bien porque no es solo una tarea de cocina: fija la mesa en
    # Bar el Bosque y ocupa uno de sus lugares, así que afecta el reparto del restaurante.
    ("Cena privada", (
        r"cena\s+(?:\w+\s+){0,2}privada|cena\s+rom[áa]ntica|"
        r"private\s+(?:\w+\s+){0,2}dinner|romantic\s+dinner"
    )),
    ("Botella de vino cortesía", r"botella\s+de\s+vino|vino\s+de\s+cortes[íi]a|champ[áa]n|champagne|"
                                 r"bottle\s+of\s+wine|wine\s+bottle|complimentary\s+wine"),
    ("Frutas con chocolate cortesía", r"frutas?\s+con\s+chocolate|chocolate\s+covered"),
    ("Frutas de cortesía", r"frutas?\s+(?:de\s+)?cortes[íi]a|canasta\s+de\s+frutas|"
                           r"fruit\s+basket|basket\s+of\s+fruit|complimentary\s+fruit"),
    ("Tarjeta de bienvenida", r"tarjeta\s+de\s+bienvenida|regalo\s+de\s+bienvenida|welcome\s+(?:card|gift)"),
    # Restricciones alimentarias y de salud: información crítica para cocina, que el
    # PDF suele escribir en inglés ("Dietary Restrictions: No seafood") o en español.
    ("Restricción alimentaria / alergia", (
        r"dietary\s+restriction|restricci[óo]n(?:es)?\s+aliment|alerg|allerg|intoleran|"
        r"celiac|cel[íi]ac|gluten|sin\s+lactosa|lactose\s+free|"
        r"vegetarian|vegan|vegetarian[oa]|no\s+pork|no\s+seafood|no\s+meat|"
        r"no\s+come\s+|no\s+consume\s+|diab[ée]tic"
    )),
    ("Requerimiento de movilidad / accesibilidad", r"silla\s+de\s+rueda|wheelchair|movilidad\s+reducida|accesibilidad"),
    ("Cuna / bebé", r"\bcuna\b|\bcrib\b|beb[ée]\s+de\s+|pack\s?n\s?play"),
]

# LAS BEBIDAS Y LA CORTESÍA NO SON AMENIDADES: son parte de lo que trae pagado la
# reserva, igual que el régimen. Van en su propia columna y se muestran junto al
# régimen en la hoja de restaurantes, que es donde el salonero mira antes de servir.
#
# Estuvieron un día como amenidad y estaba mal puesto: una amenidad es algo que hay que
# PREPARAR —la cuna, la decoración, la canasta de frutas— y esto no se prepara, se sabe.
# Mezcladas, aparecían en la lista de tareas pendientes de cocina sin que hubiera nada
# que hacer, y eso enseña a ignorar esa lista.
#
# Los patrones salieron de LEER las reservas reales de Opera, no de imaginar cómo se
# escribiría. Las tres formas que aparecen hoy en el PMS:
#
#   · «Paquete 2N/3D+Pensión completa, incluyendo jugo del día o gaseosa»
#   · «PAQUETE 4D/3N+FULL BOARD+JUGO NATURAL DEL DIA»
#   · «Paquete 3N/4D + Pensión completa + Bebida natural + PNC»
#
# La tercera es la que enseña algo: «Bebida natural» no dice «incluida» en ninguna
# parte. Un patrón que exigiera la palabra «incluye» la perdía.
BEBIDAS_PATRON = (
    r"refresco|gaseosa|"
    # «jugo natural», «bebida natural», «jugo del día», y sus plurales
    r"(?:jugo|bebida)s?\s+natural(?:es)?|"
    r"(?:jugo|bebida)s?\s+del\s+d[íi]a|"
    r"natural\s+juice|juice\s+of\s+the\s+day|"
    # «incluyendo jugo…», «incluye bebida…», «… incluido» hasta tres palabras de por
    # medio, que es como el PMS separa el paquete de lo que trae.
    r"inclu\w*\s+(?:\w+\s+){0,3}(?:jugo|bebida|gaseosa|refresco|soda)|"
    r"(?:jugo|bebida|gaseosa|refresco|soda)s?\s+(?:\w+\s+){0,2}inclu\w*|"
    r"soft\s*drinks?|"
    r"beverages?\s+included|includes?\s+beverages?|juice\s+included|"
    r"barra\s+libre|open\s+bar|todo\s+incluido|all\s+inclusive"
)

# CORTESÍA (CPL / Complementary). Reservas que el hotel no cobra, en todo o en parte.
# El salonero tiene que saberlo antes de pasar una cuenta.
#
# Formas reales en Opera: «CPL EN HOSPEDAJE+FULL BOARD», «RESERVA CPL SOLICITDA POR
# ANA ARTAVIA», «CPL para Costa Rica Focus», «COMPLEMENTARY PNC+SNK CPL BOAT TRANSFER».
#
# 'CPL' va con límite de palabra: sin eso cazaría cualquier palabra que lo contenga.
CORTESIA_PATRON = r"\bCPL\b|\bCOMPLEMENTARY\b|\bCOMPLIMENTARY\b|\bcortes[íi]a\b"

# Se mantiene la lista simple por compatibilidad con código existente
AMENIDADES_CATALOGO = [nombre for nombre, _ in AMENIDADES_PATRONES]


# ---------------------------------------------------------------------------
# Régimen de comidas
# ---------------------------------------------------------------------------
# El PDF dice qué comidas trae pagadas cada reserva, pero lo escribe en texto libre y
# de muchas formas. Los patrones de abajo salieron de leer reportes reales del PMS.
#
# Importa por comida, no como un sí/no: "Breakfast & Dinner" trae la cena pero NO el
# almuerzo, así que ese huésped tiene que aparecer en la cena y no en el almuerzo.
#
# El orden importa: se evalúa de lo más específico a lo más general, porque una misma
# reserva puede decir "Paquete 3N/4D+ Breakfast & Dinner" y también "Total $...".
REGIMENES = [
    # Personal de mantenimiento y proveedores: duermen en el lodge pero comen aparte.
    ("COMEDOR_TRABAJADORES", r"comen\s+en\s+el\s+comedor\s+de\s+trabajador"),
    # Desayuno y cena, sin almuerzo.
    ("DESAYUNO_CENA", r"breakfast\s*&\s*dinner|breakfast\s+and\s+dinner|desayuno\s+y\s+cena"),
    # Solo desayuno.
    ("SOLO_DESAYUNO", r"only\s+breakfast|breakfast\s+only|solo\s+desayuno|"
                      r"[uú]nicamente\s+desayuno"),
    # Todas las comidas. 'FULL BOARDBENEFICIO' aparece pegado en el PDF, sin espacio,
    # así que no se exige un límite de palabra al final de 'board'.
    ("PENSION_COMPLETA", r"full\s*board|pensi[oó]n\s+completa|pension\s+completa|"
                         r"\bFB\b|alimentaci[oó]n\s+y\s+tours|"
                         r"hospedaje,?\s+transporte,?\s+alimentaci[oó]n"),
]

# Qué come cada régimen en los restaurantes del lodge.
COMIDAS_DE_REGIMEN = {
    "PENSION_COMPLETA":     {"almuerzo": True,  "cena": True},
    "DESAYUNO_CENA":        {"almuerzo": False, "cena": True},
    "SOLO_DESAYUNO":        {"almuerzo": False, "cena": False},
    "COMEDOR_TRABAJADORES": {"almuerzo": False, "cena": False},
}


def detectar_regimen(reserva):
    """Qué comidas trae pagadas la reserva, según lo que diga el PDF.

    Devuelve None cuando el PDF no lo menciona: son muchas las reservas que no lo
    escriben, y suponer que no tienen comidas sería peor que no saberlo.
    """
    texto = reserva.get("texto_completo") or \
        f"{reserva.get('adicionales_raw','')} {reserva.get('notas','')}"
    for nombre, patron in REGIMENES:
        if re.search(patron, texto, re.IGNORECASE):
            return nombre
    return None


def clasificar_notas(notas_libres):
    """Clasifica cada oración de las notas en ingreso / en_casa / salida (heurística por palabras clave)."""
    oraciones = re.split(r"(?<=[.!?])\s+", (notas_libres or "").strip())
    resultado = {"ingreso": [], "en_casa": [], "salida": []}
    for oracion in oraciones:
        if not oracion.strip():
            continue
        o_lower = oracion.lower()
        if any(kw in o_lower for kw in SALIDA_KEYWORDS):
            resultado["salida"].append(oracion.strip())
        elif any(kw in o_lower for kw in INGRESO_KEYWORDS):
            resultado["ingreso"].append(oracion.strip())
        else:
            resultado["en_casa"].append(oracion.strip())
    return {
        "nota_ingreso": " ".join(resultado["ingreso"]) or None,
        "nota_en_casa": " ".join(resultado["en_casa"]) or None,
        "nota_salida": " ".join(resultado["salida"]) or None,
    }


def _texto_de(reserva):
    return (reserva.get("texto_completo")
            or f"{reserva.get('adicionales_raw','')} {reserva.get('notas','')}")


_NEGACION = re.compile(r"\b(?:no|sin|not|without)\b", re.IGNORECASE)


def _sin_negar(patron, texto):
    """La primera coincidencia que NO esté negada, o None.

    Real, encontrada en Opera: «FULLBOARD ( bebidas no incluidas)». Dar esa reserva por
    "con bebidas incluidas" es PEOR que no detectar nada: el salonero regalaría bebidas,
    o le diría al huésped que trae algo que no trae.

    Se mira dentro de lo que coincidió y un poco antes: «bebidas no incluidas» trae el
    «no» dentro, y «sin bebidas» justo delante. Si hay otra mención más adelante que no
    esté negada, esa vale — una reserva puede decir las dos cosas.

    NO se usa para las amenidades: en la restricción alimentaria el «no» es parte de la
    señal —«no seafood», «no pork»— y descartarla ahí perdería justamente las alergias,
    que es lo más grave que se puede perder.
    """
    for m in re.finditer(patron, texto, re.IGNORECASE):
        antes = texto[max(0, m.start() - 12):m.start()]
        if _NEGACION.search(m.group(0)) or _NEGACION.search(antes):
            continue
        return m
    return None


def _fragmento(texto, m, contexto=None, maximo=None):
    """El trozo de texto alrededor de lo que se reconoció, recortado por palabras.

    El corte se marca con «…» del lado donde quedó texto afuera. No es adorno: sin la
    marca, «RESERVA CPL SOLICITADA POR… + FULLBOARD ( bebidas no» se lee como una frase
    terminada y dice lo contrario de lo que dice la reserva completa —«bebidas no
    incluidas»—. Quien pasa la cuenta tiene que poder ver que hay más antes de decidir.
    """
    contexto = DETALLE_CONTEXTO if contexto is None else contexto
    maximo = DETALLE_MAXIMO if maximo is None else maximo
    desde, hasta = max(0, m.start() - contexto), min(len(texto), m.end() + contexto)
    trozo = " ".join(texto[desde:hasta].split())
    if desde > 0 and " " in trozo:
        trozo = trozo.split(" ", 1)[1]
    if hasta < len(texto) and " " in trozo:
        trozo = trozo.rsplit(" ", 1)[0]
    trozo = trozo.strip(" ·-,;:")
    if not trozo:
        return trozo
    # Las marcas cuentan dentro del máximo: el largo es lo que tiene que caber en la
    # celda de la hoja, y da igual si lo que la llena es texto o puntos suspensivos.
    inicio = "…" if desde > 0 else ""
    falta_al_final = hasta < len(texto) or len(inicio) + len(trozo) + 1 > maximo
    fin = "…" if falta_al_final else ""
    cabe = maximo - len(inicio) - len(fin)
    return inicio + trozo[:cabe].strip(" ·-,;:") + fin


def detectar_bebidas(reserva):
    """Qué bebidas trae incluida la tarifa, o None. Devuelve el texto de la reserva."""
    texto = _texto_de(reserva)
    m = _sin_negar(BEBIDAS_PATRON, texto) if texto.strip() else None
    return _fragmento(texto, m) if m else None


def detectar_cortesia(reserva):
    """Si la reserva es de cortesía (CPL), y con qué texto lo dice. None si no lo es.

    No se intenta averiguar QUÉ es cortesía —a veces el hospedaje, a veces un tour, a
    veces el bote— porque el texto no lo dice de forma regular. Se devuelve el fragmento
    para que quien pase la cuenta lo lea y decida, que es lo que hace hoy.
    """
    texto = _texto_de(reserva)
    if not texto.strip():
        return None
    m = re.search(CORTESIA_PATRON, texto, re.IGNORECASE)
    return _fragmento(texto, m) if m else None


def _coincidencia(nombre, patron, texto):
    """La primera coincidencia de una amenidad. Las amenidades no llevan guardia de
    negación: ahí el «no» suele ser parte de la señal."""
    return re.search(patron, texto, re.IGNORECASE)


def detectar_amenidades(reserva):
    """Devuelve los nombres exactos del catálogo de amenidades mencionadas en la reserva.
    Busca en 'Adicionales' y en las notas libres, tolerando variantes de escritura."""
    texto = _texto_de(reserva)
    encontradas = []
    for nombre_catalogo, patron in AMENIDADES_PATRONES:
        if (_coincidencia(nombre_catalogo, patron, texto)
                and nombre_catalogo not in encontradas):
            encontradas.append(nombre_catalogo)
    return encontradas


# Cuánto texto se guarda alrededor de lo que se reconoció. Suficiente para entender de
# qué se trata, corto para que quepa en una fila de la hoja del día.
DETALLE_CONTEXTO = 60
DETALLE_MAXIMO = 160


def detallar_amenidades(reserva):
    """{nombre de amenidad: el trozo de texto por el que se reconoció}.

    POR QUÉ HACE FALTA. Hasta ahora una amenidad detectada se guardaba con el detalle
    VACÍO, así que a cocina le llegaba «Restricción alimentaria / alergia» sin decir de
    qué era la alergia. El dato estaba en el reporte y se perdía en el camino: solo
    aparecía si recepción lo volvía a escribir a mano. Con lo mismo pasaba con todo el
    resto — «Cuna / bebé» sin decir para qué edad, «Cena privada» sin decir qué noche.

    Se guarda el fragmento y no el texto entero de la reserva: entero no cabe en la hoja
    del día y ahí dentro va también información de otras cosas. Se recorta por palabras
    completas, porque un detalle cortado a la mitad de una palabra se lee peor que uno
    corto.

    El detalle que haya escrito recepción SIEMPRE manda sobre esto: ver loader.py.
    """
    texto = _texto_de(reserva)
    if not texto.strip():
        return {}
    salida = {}
    for nombre_catalogo, patron in AMENIDADES_PATRONES:
        m = _coincidencia(nombre_catalogo, patron, texto)
        if not m or nombre_catalogo in salida:
            continue
        trozo = _fragmento(texto, m)
        if trozo:
            salida[nombre_catalogo] = trozo
    return salida


def to_iso_date(arr_date_ddmmyy, dia_num):
    """El día del itinerario ('11') convertido a fecha, usando la llegada de referencia.

    Devuelve None si no se puede formar una fecha, y eso NO es un caso raro: el
    itinerario lo escribe recepción a mano, así que aparecen días que no existen en ese
    mes —llega el 30 de septiembre y el itinerario dice 31—, números de más y erratas.

    POR QUÉ DEVUELVE None Y NO LEVANTA: antes hacía `date(...)` a pelo. Una sola nota
    con un día imposible reventaba la conversión, la excepción subía por el importador
    y se llevaba puesto el ciclo de sincronización COMPLETO. El hotel lo veía como
    "no se pudo sincronizar" —aunque las reservas ya se hubieran guardado—, sin ninguna
    pista de que la causa era el día 31 de una nota. Una nota mal escrita puede costar
    ese tour; no puede costar la sincronización de todo el hotel.
    """
    try:
        dd, mm, yy = str(arr_date_ddmmyy).split("-")
        year, month, arr_day, dia_num = 2000 + int(yy), int(mm), int(dd), int(dia_num)
    except (ValueError, AttributeError, TypeError):
        return None
    # Si el día de "Operacion" es menor que el día de llegada, la estadía cruzó de mes
    # (ej. llega el 29 de julio, día "1" de Operacion es en realidad 1 de agosto).
    if dia_num < arr_day:
        month += 1
        if month > 12:
            month = 1
            year += 1
    try:
        return date(year, month, dia_num).isoformat()
    except ValueError:
        return None


def detect_group_link(reserva):
    texto = reserva.get("vinculo_texto") or ""
    m_alta = re.search(r"rsvs?\.?\s*(?:de\s+)?([\d\s,y&\-]+)", texto, re.IGNORECASE)
    if m_alta:
        referencias = re.findall(r"\d{6,}", m_alta.group(1))
        if referencias:
            return {"tipo": "ALTA", "referencias_conf_no": referencias, "texto": texto}
    if texto:
        return {"tipo": "MEDIA", "referencias_conf_no": [], "texto": texto}
    return None


def detect_contradiction(reserva, tour_code):
    notas = (reserva.get("notas") or "").lower()
    tour_nombre = tour_code.lower()
    for kw in CONTRADICTION_KEYWORDS:
        if kw in notas and tour_nombre in notas:
            return True
    return False


def build_group_sets(reservas):
    """Une reservas en un mismo grupo solo cuando el vínculo es de ALTA confianza
    (referencia explícita a un Conf. No.). Los vínculos de MEDIA confianza no se
    fusionan automáticamente porque requieren confirmación de recepción."""
    parent = {r["conf_no"]: r["conf_no"] for r in reservas}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for r in reservas:
        link = r.get("grupo_link")
        if link and link["tipo"] == "ALTA":
            for ref in link["referencias_conf_no"]:
                if ref in parent and ref != r["conf_no"]:
                    union(r["conf_no"], ref)

    return {conf_no: find(conf_no) for conf_no in parent}


def build_review_batch(pdf_path):
    """Lote de revisión a partir del PDF del PMS."""
    return build_review_batch_desde_reservas(parse_reservations(pdf_path))


def build_review_batch_desde_reservas(reservas):
    """Aplica las reglas del lodge a una lista de reservas ya extraídas.

    Está separado de build_review_batch para que Opera Cloud entre por el mismo
    camino que el PDF. Lo que cambia entre una fuente y otra es de dónde salen los
    datos, no las reglas: los tours, los grupos, las entradas del SINAC y las
    amenidades se deciden igual vengan de donde vengan. Si esto estuviera duplicado,
    una corrección hecha para el PDF no llegaría a las reservas de Opera.
    """
    for r in reservas:
        r["tours_detectados"] = cross_reference_tours(r["adicionales_raw"])
        r["grupo_link"] = detect_group_link(r)
        r.update(clasificar_notas(r["notas"]))
        r["amenidades_detectadas"] = detectar_amenidades(r)
        # Con qué texto se reconoció cada una, para que el detalle no se pierda.
        r["detalles_de_amenidad"] = detallar_amenidades(r)
        r["regimen"] = detectar_regimen(r)
        # Lo que trae pagado la reserva más allá de las comidas. Va junto al régimen,
        # no como amenidad: no hay nada que preparar, hay algo que saber.
        r["bebidas_incluidas"] = detectar_bebidas(r)
        r["cortesia"] = detectar_cortesia(r)

    grupo_de = build_group_sets(reservas)

    entradas_sinac = {}  # key: (tour, fecha, conf_entrada) -> {pax_total, grupos: set, conf_nos: []}
    review_items = []

    for r in reservas:
        agenda = []
        for op in r["operacion"]:
            if "tour" not in op:
                continue
            fecha_iso = to_iso_date(r["arr_date"], op["dia"])
            if not fecha_iso:
                # El día del itinerario no forma una fecha válida (un 31 en un mes de
                # 30, una errata). No se descarta en silencio: se guarda para revisión,
                # que es lo mismo que se hace con una actividad que no está en el
                # catálogo. Recepción lo ve y lo corrige en la nota.
                r.setdefault("actividades_no_reconocidas", []).append(
                    {"dia": op["dia"], "texto": f"{op['tour']} — el día "
                     f"{op['dia']} no existe en ese mes, revisar la nota"})
                continue
            contradiccion = detect_contradiction(r, op["tour"])
            agenda.append({
                "fecha": fecha_iso,
                "tour": op["tour"],
                "conf_entrada": op.get("conf_entrada"),
                "contradiccion": contradiccion,
                # Cuánta gente va A ESTE tour, si la fuente lo sabe. Opera lo dice
                # ('totalQuantity' del paquete) y no siempre coincide con la gente de
                # la habitación: medido en una reserva real, 3 adultos con solo 2 en
                # el snorkel. Usar el pax de la habitación pediría un asiento de bote
                # y una entrada del parque de más, todos los días.
                "pax": op.get("pax_opera"),
            })
            # Se registra la necesidad de entrada SINAC para TODOS los tours que la
            # requieren, tengan o no número de confirmación. Antes solo se registraban
            # las que ya traían confirmación (o sea, las ya compradas), por lo que las
            # pendientes de comprar —justo las importantes— nunca aparecían.
            tour_base = op["tour"].replace(" PRIVADO", "").strip()
            if tour_base in TOURS_CON_ENTRADA_SINAC:
                key = (op["tour"], fecha_iso, op.get("conf_entrada"))
                if key not in entradas_sinac:
                    entradas_sinac[key] = {"pax_total": 0, "grupos": set(), "conf_nos": [], "contradiccion": False}
                # La misma cuenta que el tour: si la fuente sabe cuánta gente va, se
                # compran esas entradas y no una por cada persona de la habitación.
                pax_tour = op.get("pax_opera")
                entradas_sinac[key]["pax_total"] += (
                    pax_tour if isinstance(pax_tour, int) and pax_tour > 0
                    else r["adl"] + r["chl"])
                entradas_sinac[key]["grupos"].add(grupo_de[r["conf_no"]])
                entradas_sinac[key]["conf_nos"].append(r["conf_no"])
                entradas_sinac[key]["contradiccion"] = (
                    entradas_sinac[key]["contradiccion"] or contradiccion
                )
        r["agenda"] = agenda

        needs_review = bool(
            r["grupo_link"] or r["guia_sugerido"] or
            any(a["contradiccion"] for a in agenda) or
            r.get("punto_entrada_sin_confirmar") or r.get("punto_salida_sin_confirmar") or
            r.get("actividades_no_reconocidas")
        )
        review_items.append({"reserva": r, "needs_review": needs_review})

    entradas_resumen = []
    for (tour, fecha, conf), info in entradas_sinac.items():
        if info["contradiccion"]:
            estado = "VER_NOTA"
        elif conf:
            estado = "COMPRADA"   # el número de confirmación es la prueba de compra
        else:
            estado = "SIN_COMPRAR"
        entradas_resumen.append({
            "tour": tour,
            "fecha": fecha,
            "conf_entrada": conf,
            # +1 entrada de guía por cada salida de tour (no por grupo familiar):
            # si varias reservas van al mismo tour el mismo día, salen con un solo guía.
            # Si recepción divide la salida en grupos operativos (A/B), cada grupo lleva
            # su guía y esa entrada extra se ajusta manualmente.
            "pax_total_grupo": info["pax_total"] + 1,
            "reservas_vinculadas": list(set(info["conf_nos"])),
            "estado": estado,
        })

    return {"reservas": review_items, "entradas_sinac": entradas_resumen}


if __name__ == "__main__":
    import json
    batch = build_review_batch("/mnt/user-data/uploads/Arrivals__Detailed.PDF")
    print(f"=== {len(batch['reservas'])} reservas procesadas ===\n")
    for item in batch["reservas"]:
        r = item["reserva"]
        flag = "REVISAR" if item["needs_review"] else "auto"
        print(f"[{flag}] Room {r['room_no']} - {r['nombre_principal']} (conf {r['conf_no']})")
        if r["grupo_link"]:
            print(f"    Grupo: {r['grupo_link']}")
        if r["guia_sugerido"]:
            print(f"    Guía sugerido: {r['guia_sugerido']}")
    print(f"\n=== {len(batch['entradas_sinac'])} entradas SINAC detectadas ===\n")
    for e in batch["entradas_sinac"]:
        print(f"{e['tour']} {e['fecha']} conf={e['conf_entrada']} pax_total={e['pax_total_grupo']} "
              f"estado={e['estado']} reservas={e['reservas_vinculadas']}")
