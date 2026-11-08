"""
Extractor del reporte PMS "Arrivals: Detailed" -> reservas estructuradas.
Implementa las reglas definidas en el Documento de Requerimientos, sección 6.
"""
import re
import pdfplumber

# --- Líneas de ruido (encabezados/pies de página que se repiten) ---
NOISE_PATTERNS = [
    r"^Filter Arrival from Date",
    r"^Room Class All",
    r"^Market Code All",
    r"^From Arrival Time",
    r"^Comment Type All",
    r"^Colors All",
    r"^Corcovado Wilderness Lodge Costa Rica",
    r"^Arrivals: Detailed$",
    r"^Room Name Company",
    r"^No\. Travel Agent Type",
    r"^Source$",
    r"^Conf No\. VIP Last",
    r"^Room # of Arrival",
    r"^Page \d+ of \d+",
    r"^\d{2}-\d{2}-\d{2}$",
    r"^\d{1,2}:\d{2}$",
    r"^Arrival Date Total",
    r"^Grand Total",
]
NOISE_RE = re.compile("|".join(NOISE_PATTERNS))

ROW_RE = re.compile(
    r"^(?P<room>\d{1,4})\s+"
    r"(?P<name>[^\d,]+?(?:,[^\d]+?)?)\s+"
    r"(?P<company>(?:[A-Za-z]-\s(?:(?!\d{2}-\d{2}-\d{2}).)*)?)\s*"
    r"(?P<arr>\d{2}-\d{2}-\d{2})\s+"
    r"(?P<dep>\d{2}-\d{2}-\d{2})\s+"
    r"(?P<roomtype>\S+)\s+"
    r"(?P<adl>\d+)\s+(?P<chl>\d+)\s+(?P<rms>\d+)\s+"
    r"(?P<mkt>\S+)\s+(?P<src>\S+)\s+(?P<status>[A-Z]+)\s*$"
)

# Respaldo: cuando el PDF original pega "Src. Code" y "Res. Status" sin espacio
# (ej. "VENTADP" en vez de "VENTA DP"), se reconocen los estados válidos conocidos
# como sufijo para poder separarlos igual.
ESTADOS_CONOCIDOS = ["CKIN", "COMP", "CORP", "GRP", "REF", "NON", "CC", "DP", "LA", "TA"]
ROW_RE_RESPALDO = re.compile(
    r"^(?P<room>\d{1,4})\s+"
    r"(?P<name>[^\d,]+?(?:,[^\d]+?)?)\s+"
    r"(?P<company>(?:[A-Za-z]-\s(?:(?!\d{2}-\d{2}-\d{2}).)*)?)\s*"
    r"(?P<arr>\d{2}-\d{2}-\d{2})\s+"
    r"(?P<dep>\d{2}-\d{2}-\d{2})\s+"
    r"(?P<roomtype>\S+)\s+"
    r"(?P<adl>\d+)\s+(?P<chl>\d+)\s+(?P<rms>\d+)\s+"
    r"(?P<mkt>\S+)\s+(?P<srcstatus>[A-Z]+)\s*$"
)


def _match_row(line):
    m = ROW_RE.match(line)
    if m:
        return m
    m2 = ROW_RE_RESPALDO.match(line)
    if not m2:
        return None
    combinado = m2.group("srcstatus")
    for estado in ESTADOS_CONOCIDOS:
        if combinado.endswith(estado) and len(combinado) > len(estado):
            d = m2.groupdict()
            d["src"] = combinado[: -len(estado)]
            d["status"] = estado
            return _DictMatch(d)
    return None


class _DictMatch:
    """Envoltorio simple para que _match_row se use igual que un re.Match."""
    def __init__(self, d):
        self._d = d

    def group(self, key):
        return self._d[key]
CONF_RE = re.compile(r"^(?P<conf>\d{6,9})\b(?:\s+(?P<time>\d{1,2}:\d{2}))?.*$")
ARRIVAL_DATE_HEADER_RE = re.compile(r"^Arrival Date\s+(\d{2}-\d{2}-\d{2})")

# Números de vuelo: el PDF los escribe de varias formas ("RZ1054", "RZ 1056",
# "Sansa 1054", "Flight RZ1054@13:00"). Se normalizan a formato "RZ1054".
VUELO_RE = re.compile(r"\b(?:RZ|SANSA)\s?(\d{3,4})\b", re.IGNORECASE)

# Las horas vienen escritas de muchas formas: "13:00", "3:00 p.m.", "3:00PM",
# "08:35", "2:20 PM". Se capturan todas y se normalizan a "3:00 p.m." / "8:35 a.m."
#
# SE TOLERAN LOS ESPACIOS Y EL PUNTO ALREDEDOR DEL SEPARADOR, y eso no es cosmético.
# La nota de una reserva real decía «Salida: Via Drake Sansa RZ1069 @2: 45 PM» —con un
# espacio después de los dos puntos— y el sistema leía el punto de embarque y el número
# de vuelo pero devolvía None en la hora. SIN DAR NINGÚN ERROR: la reserva quedaba con
# su vuelo y sin hora, el traslado no se podía calcular, y en la hoja del día salía una
# casilla vacía que nadie sabía a qué atribuir. Medido sobre la base: once reservas
# vivas tienen número de vuelo y ninguna hora.
#
# El punto se admite solo cuando detrás viene «am/pm»: en una nota suelta, «1.50» es un
# precio mucho más a menudo que la una y media.
#
# Los espacios son [ \t] y no \s a propósito: con \s, una hora cortada al final de una
# línea se uniría con el número de la siguiente y se inventaría una hora que nadie
# escribió.
HORA_RE = re.compile(
    r"(\d{1,2})[ \t]*[:.][ \t]*(\d{2})[ \t]*([ap])\.?[ \t]?m\.?", re.IGNORECASE)
HORA_SIMPLE_RE = re.compile(r"(?<!\d)(\d{1,2})[ \t]*:[ \t]*(\d{2})(?!\d)")

# LA HORA EN PUNTO, SIN MINUTOS. Medido sobre las notas reales del lodge: de once
# reservas que tenían vuelo y ninguna hora, SEIS la traían escrita así — «9am»,
# «1 pm», «1PM», «13hrs», «13h». Son horas perfectamente claras para quien las lee y
# el sistema las tiraba enteras.
#
# Van DESPUÉS de las dos de arriba a propósito: «12:50hrs» tiene que leerse como las
# 12:50, no como las 12 en punto. El orden de los intentos es el que decide eso.
HORA_EN_PUNTO_RE = re.compile(r"(?<!\d)(\d{1,2})[ \t]*([ap])\.?[ \t]?m\.?", re.IGNORECASE)
# «13hrs», «13 h». La 'h' tiene que cerrar palabra: así «3 hours» o «2 HOURS TOUR» —que
# son duraciones y están por todo el itinerario— no se confunden con una hora del día.
HORA_24_RE = re.compile(r"(?<!\d)(\d{1,2})[ \t]*h(?:rs?|s)?\b", re.IGNORECASE)

# Código de bloque del PMS: identifica reservas que viajan juntas (un grupo, una
# agencia). Aparece como "2608RUSSTI" o "2608CR2608". Es la única señal de grupo
# para las reservas que no traen la nota "viene con rsv".
BLOCK_RE = re.compile(r"\b(\d{4}[A-Z][A-Z0-9]{3,})\b")
# Palabras que descartan la línea: los números de certificación de buceo tienen la
# misma forma (ej. "Certification #1810S8860") y no son códigos de grupo.
BLOCK_EXCLUIR = re.compile(r"certificat|#|PADI|diver", re.IGNORECASE)


def _es_block_code(texto, candidato):
    """Un código de bloque real trae al menos dos letras tras los cuatro dígitos.
    Así se descarta '1810S8860' (certificación) y se conserva '2608RUSSTI'."""
    if BLOCK_EXCLUIR.search(texto):
        return False
    return sum(ch.isalpha() for ch in candidato[4:]) >= 2

# Documento de identidad del huésped. Aparece en muchos formatos y no siempre al
# final de la línea, así que se busca en cualquier posición:
#   555591746 · A13343206 · GD0011047 · PAMO75815 · C1VW6C3JF · 1-0745-0194
DOC_RE = re.compile(r"(?P<doc>\b(?:[A-Z]{1,5}\d[\dA-Z]{3,}|\d[\d-]{6,})\b)")


def normalizar_hora(texto):
    """Devuelve la hora en formato '3:00 p.m.'. Si viene en formato 24h la convierte."""
    if not texto:
        return None
    m = HORA_RE.search(texto)
    if m:
        h, mm, ap = int(m.group(1)), m.group(2), m.group(3).lower()
        if h > 12:
            h -= 12
        return f"{h}:{mm} {ap}.m."
    m = HORA_SIMPLE_RE.search(texto)
    if m:
        h, mm = int(m.group(1)), m.group(2)
        if h >= 13:
            return f"{h - 12}:{mm} p.m."
        if h == 12:
            return f"12:{mm} p.m."
        if h == 0:
            return f"12:{mm} a.m."
        # Sin indicador: los vuelos de la mañana son de madrugada/mañana temprano y
        # los de la tarde pasan del mediodía, así que 1-7 sin marca se asume p.m.
        return f"{h}:{mm} {'a' if h >= 8 else 'p'}.m."
    # La hora en punto, que es como la escribe media nota del lodge.
    m = HORA_EN_PUNTO_RE.search(texto)
    if m:
        h, ap = int(m.group(1)), m.group(2).lower()
        if h > 12:
            h -= 12
        if 1 <= h <= 12:
            return f"{h}:00 {ap}.m."
    m = HORA_24_RE.search(texto)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            if h == 0:
                return "12:00 a.m."
            if h == 12:
                return "12:00 p.m."
            return f"{h - 12}:00 p.m." if h > 12 else f"{h}:00 a.m."
    return None


def normalizar_vuelo(match):
    return f"RZ{match.group(1)}"


# GTT NO ESTÁ AQUÍ, y es deliberado: es el mismo tour que CLARO y entra por la tabla de
# alias (ver TOUR_ALIASES). Tenerlo en las dos listas duplicaba la salida — esta lista se
# recorre primero y deja «GTT», y después el alias añade «CLARO» como si fuera otro tour
# distinto, así que la misma reserva salía dos veces el mismo día.
TOUR_CODES = [
    "CLARO", "SPA",
    "PNC", "SIRENA", "BUCEO", "ISLA", "SNORKEL", "PAJAREO", "MANGLAR",
    "BALLENAS", "CABALGATA", "TREENET", "NW", "PESCA",
]

# Nombres alternativos que el PDF puede usar para un tour ya existente en el catálogo
# (ej. el PMS a veces escribe "Horseback Riding" en inglés para lo que el hotel
# gestiona internamente como "Cabalgata").
# El PMS escribe algunos tours en inglés o abreviados. Se traducen al código del
# catálogo para que no queden como actividades desconocidas.
TOUR_ALIASES = {
    "HORSEBACK RIDING": "CABALGATA",
    "HORSEBACK": "CABALGATA",
    "HORSE RIDING": "CABALGATA",
    "WHALE WATCHING": "BALLENAS",
    "WHALE": "BALLENAS",
    "WHALES": "BALLENAS",
    "DOLPHIN": "BALLENAS",
    "FISHING HALF DAY": "PESCA",
    "SPORTFISHING": "PESCA",
    "FISHING": "PESCA",
    "SNK": "SNORKEL",
    "SNORKELING": "SNORKEL",
    "NIGHT WALK": "NW",
    "BIRD WATCHING": "PAJAREO",
    "BIRDWATCHING": "PAJAREO",
    "EARLY BIRD TOUR": "PAJAREO",
    "EARLY BIRD": "PAJAREO",
    "EBT": "PAJAREO",
    "EBW": "PAJAREO",
    "BW": "PAJAREO",
    "MANGROVE": "MANGLAR",
    "DIVING": "BUCEO",
    "SCUBA": "BUCEO",
    "TREE NET": "TREENET",
    # Garden to Table es el mismo tour que Claro del Bosque. Lo confirmó el lodge, y son
    # tres formas de escribir lo mismo: GTT y GTE entran por la tabla de equivalencias de
    # los paquetes, y el nombre largo por aquí.
    #
    # GTE se nombra explícitamente porque vive en opera_paquetes.TOURS_POR_RAIZ y NO en
    # CATALOGO_2027, que es de donde sale _alias_2027(): escrito en el comentario de una
    # reserva no lo reconocía nadie. Es un hueco general de esa lista —hay más códigos
    # ahí que aquí no llegan— pero traerlos todos de golpe crearía tours donde hoy no se
    # crea ninguno, y eso se mira aparte.
    "GARDEN TO TABLE": "CLARO",
    "GARDEN-TO-TABLE": "CLARO",
    "GTE": "CLARO",
    "SAN PEDRILLO": "PNC",
    "CANO ISLAND": "ISLA",
    "CAÑO ISLAND": "ISLA",
    "CLARO DEL BOSQUE": "CLARO",
    "CB": "CLARO",
    "MASAJES": "SPA",
    "MASAJE": "SPA",
    "SPA TREATMENT": "SPA",
}

# ---------------------------------------------------------------------------
# El catálogo de abreviaturas 2027
# ---------------------------------------------------------------------------
# Los códigos nuevos del lodge van escritos en el COMENTARIO de la reserva —el propio
# documento lo dice: «La nomenclatura no modifica la estructura del comentario»— así que
# es aquí donde hay que reconocerlos, no solo en los paquetes de Opera.
#
# Ya están en uso: «PENSION COMPLETA CPL C-BT+C-CIS+C-NGW». Sin esto, esos tours no se
# creaban y no aparecían en la hoja del día — sin dar ningún error.
#
# Se leen de opera_paquetes para que haya UNA sola tabla de equivalencias. Dos listas
# que digan lo mismo se separan, y entonces el mismo código significa una cosa leyendo
# el comentario y otra leyendo el paquete.
def _alias_2027():
    from opera_paquetes import CATALOGO_2027
    return {cod: (equivalente or cod) for cod, equivalente, _, _ in CATALOGO_2027}


TOUR_ALIASES.update(_alias_2027())

# Y LAS RAÍCES DE LOS PAQUETES DE OPERA, que hasta ahora solo valían leyendo el paquete.
#
# EL HUECO QUE TAPA, medido sobre las reservas de verdad: «CEBT Y PNC 09/12» perdía el
# CEBT, porque CEBT vivía en opera_paquetes.TOURS_POR_RAIZ y esa tabla no llegaba aquí.
# Lo mismo con SPS (el Sirena privado), SCI, TSP, HCN, HCNP, CNP, PNWALK, NQ, CNW, WWE,
# SDPS, NWP y EBTP: todos son formas que el lodge escribe de verdad en el comentario, y
# ninguna se reconocía al leer texto.
#
# Van DESPUÉS de las de arriba a propósito: si un código estuviera en las dos tablas,
# manda la de los paquetes, que es la que la operación confirmó una por una.
def _alias_de_los_paquetes():
    from opera_paquetes import TOURS_POR_RAIZ
    return dict(TOURS_POR_RAIZ)


TOUR_ALIASES.update(_alias_de_los_paquetes())

# El prefijo de modalidad, para anotarlo en la salida. 'C-CIS' ya se reconoce como CIS
# —el guion es límite de palabra— pero sin esto se perdería que era una cortesía.
# Ojo con los nombres de los grupos: la cortesía del caso 'PRV|C-' estaba en un grupo SIN
# nombre, así que un servicio privado de cortesía —la forma canónica del comunicado para
# «privado + CPL»— se leía como privado y NADA MÁS, y no se marcaba como cortesía a la
# hora de cobrar. El de 'C-' solo sí estaba bien, que es por lo que no saltaba a la vista.
#
# 'PRIV' SE ACEPTA ADEMÁS DE 'PRV'. El documento dice PRV, pero en la base del lodge
# está escrito «PRIV-SIR 03/12», «PRIV-EBT 27/12» y «PRIV|CPLEBT 14/12». Rechazarlo por
# no ser la forma canónica no hace que recepción escriba mejor: hace que un tour privado
# entre como compartido, y entonces sale en un bote con otra gente.
#
# Y EL GUION ES OPCIONAL DESPUÉS DE 'CPL': el propio catálogo del lodge imprime la
# columna como «PRV|CPLPNC», sin guion, y así se copia.
_MODALIDAD = re.compile(
    r"(?:(?P<prv>PRV|PRIV)\s*\|\s*(?P<cpl1>CPL|C)\s*-?"
    r"|(?P<prv2>PRV|PRIV)\s*-"
    r"|(?P<cpl2>CPL|C)\s*-)\s*$",
    re.IGNORECASE)


def modalidad_antes_de(texto, posicion):
    """(privado, cortesia) leyendo lo que hay justo antes del código en el texto.

    Se mira solo lo pegado al código: 'C-CIS' es una cortesía, pero un 'CPL' suelto tres
    palabras antes puede estar hablando de otra cosa de la reserva.
    """
    m = _MODALIDAD.search(texto[max(0, posicion - 14):posicion])
    if not m:
        return False, False
    return (bool(m.group("prv") or m.group("prv2")),
            bool(m.group("cpl1") or m.group("cpl2")))


# ===========================================================================
# El itinerario escrito en prosa
# ===========================================================================
#
# POR QUÉ EXISTE. La sección de «Operación» tiene un formato —«10: PNC»— y el lector lo
# entiende. Pero recepción también escribe el itinerario en frases: «PRV-CID 26/11»,
# «A solicitud del cliente PNC 17/12 - CIS 18/12», «KATIANA SOLICITA - 07/12: C-EBT +
# CLW | 08/12: CIS». Todo eso se tiraba: el lector veía una fecha DD/MM en la línea y la
# apartaba entera como nota.
#
# Medido sobre las 376 reservas de la base: 71 líneas nombraban un tour con su fecha y
# NO producían ninguno. Ahí estaban los privados que el lodge echó en falta —PRV-CID,
# PRV-PNC, PRIV-SIR, «25/11 PRIVADO SIRENA»— y días enteros de itinerario.
#
# POR QUÉ SE TIRABAN, Y POR QUÉ ESO ERA RAZONABLE: después del itinerario vienen notas
# en texto libre que también nombran tours y fechas, y leerlas a lo bruto pone salidas
# que nadie pidió el día que no es. El comentario del lector lo decía con un ejemplo
# real. La respuesta no es leerlo todo ni tirarlo todo, es saber distinguirlo.
#
# LO QUE LO DISTINGUE ES LA ADYACENCIA. En una instrucción, el código y su fecha van
# pegados: entre los dos no hay más que separadores y, como mucho, otros códigos. En una
# frase hay palabras por medio. Medido contra la base real, esa sola regla separa
#
#     «PNC 22/11 - NW 23/11»                      -> dos tours, bien
#     «PNC E INSPECCIÓN 11/08»                    -> nada (y menos mal: 11/08 ni
#                                                    siquiera cae en la estadía)
#     «...un bote de unos amigos que van a Sirena» -> nada
#     «SE LE COBRA MGS POR 4 PAX»                 -> nada
#     «INTERESADOS EN RESERVAR CIS»               -> nada
#
# Y LO QUE NO SE PUEDE REPARTIR, NO SE REPARTE. Con una sola fecha en el trozo, es de
# todos los códigos pegados a ella; con tantas fechas como códigos, van en orden; con
# cualquier otra combinación se devuelve como no reconocido para que recepción lo mire.

# Los códigos más largos primero: así «PNWALK» gana a «PNC» y no se corta a medias.
def _codigos_conocidos():
    return sorted(set(list(TOUR_CODES) + list(TOUR_ALIASES)), key=len, reverse=True)


# Un prefijo de modalidad pegado al código, en todas las formas que el lodge escribe.
_PREFIJO = r"(?:PRV|PRIV)\s*(?:\|\s*(?:CPL|C))?\s*-?\s*|(?:CPL|C)\s*-\s*"

# Lo único que puede haber entre una fecha y su código sin que se rompa la unión.
_CONECTORES = {"EL", "LA", "DIA", "DÍA", "PARA", "LOS", "LAS", "Y", "DEL", "DE", "AND"}

# Transporte, no tours. Tienen su propio camino (traslados_extra) y meterlos aquí
# pondría una salida de bote en la agenda de guías.
_NO_SON_TOURS = {"TT", "BT", "TRB", "MGX"}

_RE_DIA_TRAS_CODIGO = re.compile(r":\s*(\d{1,2})\b(?!\s*[/:%\d])")


def _re_tokens():
    return re.compile(
        r"(?P<fecha>\b\d{1,2}\s*/\s*\d{1,2}(?:\s*/\s*\d{2,4})?\b)"
        # «el 9», «el día 18». El (?![/%]) es para que «el 01/03» siga siendo una fecha
        # entera y no el día 1, y para que «el 15%» no sea el día 15.
        r"|(?P<dia>\bel\s+(?:d[ií]a\s+)?\d{1,2}\b(?!\s*[/%]))"
        r"|(?P<codigo>\b(?:" + _PREFIJO + r")?(?:"
        + "|".join(re.escape(x) for x in _codigos_conocidos()) + r")\b)"
        # «PRIVADO SIRENA» es como el lodge lo escribe de palabra. Cuenta como marca de
        # modalidad del código de al lado, no como una palabra que corte el paso.
        r"|(?P<privado>\bPRIVADOS?\b|\bPRIVADAS?\b|\bPRIVATE\b)"
        r"|(?P<palabra>[A-Za-zÁÉÍÓÚÑáéíóúñ]{2,})",
        re.IGNORECASE)


def _trozos_de_la_linea(linea):
    """Parte la línea en grupos por «|» y «;», sin romper el prefijo PRV|CPL.

    El «|» hace de separador de días —«07/12: A + B | 08/12: C»— y a la vez va dentro
    del prefijo del catálogo. Se protege el segundo antes de partir por el primero.
    """
    # El reemplazo NO va en cadena cruda: hace falta el carácter NUL de verdad, y en
    # cruda «\x00» son cuatro caracteres que re.sub rechaza como escape inválido.
    protegida = re.sub(r"\b(PRV|PRIV)\s*\|\s*(CPL|C)", "\\1\x00\\2", linea,
                       flags=re.IGNORECASE)
    return [t.replace("\x00", "|") for t in re.split(r"[|;]", protegida)]


def _leer_tokens(trozo):
    # «NW: 18» -> el número suelto detrás de los dos puntos es un día.
    trozo = _RE_DIA_TRAS_CODIGO.sub(lambda m: f" el {m.group(1)} ", trozo)
    tokens = []
    for m in _re_tokens().finditer(trozo):
        grupo = m.lastgroup
        if grupo == "fecha":
            dia, mes = re.findall(r"\d{1,2}", m.group(0))[:2]
            tokens.append({"t": "FECHA", "dia": int(dia), "mes": int(mes)})
        elif grupo == "dia":
            tokens.append({"t": "FECHA",
                           "dia": int(re.findall(r"\d{1,2}", m.group(0))[0]), "mes": None})
        elif grupo == "codigo":
            bruto = m.group(0).upper()
            pref = re.match(r"^(?:" + _PREFIJO + r")", bruto, re.IGNORECASE)
            nombre = bruto[pref.end():] if pref else bruto
            real = TOUR_ALIASES.get(nombre, nombre)
            if real in _NO_SON_TOURS:
                continue
            privado = cortesia = False
            if pref:
                sin_espacios = re.sub(r"[\s|]", "", pref.group(0)).upper()
                privado = sin_espacios.startswith(("PRV", "PRIV"))
                cortesia = bool(re.search(r"(?:CPL|C)-?$", sin_espacios))
            tokens.append({"t": "CODIGO", "tour": real,
                           "privado": privado, "cortesia": cortesia})
        elif grupo == "privado":
            tokens.append({"t": "PRIVADO"})
        elif m.group(0).upper() not in _CONECTORES:
            tokens.append({"t": "PALABRA"})
    # La palabra «privado» marca al código que tiene al lado y después desaparece, para
    # que no corte el camino entre el código y su fecha.
    for i, tok in enumerate(tokens):
        if tok["t"] != "PRIVADO":
            continue
        for j in (i + 1, i - 1):
            if 0 <= j < len(tokens) and tokens[j]["t"] == "CODIGO":
                tokens[j]["privado"] = True
                break
    return [t for t in tokens if t["t"] != "PRIVADO"]


def _tiene_fecha_pegada(tokens, i):
    """¿Hay una fecha al alcance del código, sin cruzar ninguna palabra?"""
    for paso in (-1, 1):
        j = i + paso
        while 0 <= j < len(tokens) and tokens[j]["t"] == "CODIGO":
            j += paso
        if 0 <= j < len(tokens) and tokens[j]["t"] == "FECHA":
            return True
    return False


def tours_en_prosa(texto):
    """Los tours que una nota en texto libre coloca en un día, sin adivinar ninguno.

    Devuelve [{'dia', 'mes', 'tour', 'privado', 'cortesia'}]. 'mes' puede ser None
    cuando la nota solo dice el día («C-EBT el 09»), igual que el itinerario.
    """
    encontrados = []
    for linea in re.split(r"[·\n]", texto or ""):
        for trozo in _trozos_de_la_linea(linea):
            tokens = _leer_tokens(trozo)
            codigos = [t for i, t in enumerate(tokens)
                       if t["t"] == "CODIGO" and _tiene_fecha_pegada(tokens, i)]
            if not codigos:
                continue
            fechas = [t for t in tokens if t["t"] == "FECHA"]
            if len(fechas) == 1:
                parejas = [(fechas[0], c) for c in codigos]
            elif len(fechas) == len(codigos):
                parejas = list(zip(fechas, codigos))
            else:
                continue          # no se reparte lo que no cuadra
            for f, c in parejas:
                encontrados.append({"dia": f["dia"], "mes": f["mes"], "tour": c["tour"],
                                    "privado": c["privado"], "cortesia": c["cortesia"]})
    # Sin repetir: la misma nota puede nombrar el tour dos veces.
    vistos, limpio = set(), []
    for t in encontrados:
        clave = (t["dia"], t["mes"], t["tour"])
        if clave not in vistos:
            vistos.add(clave)
            limpio.append(t)
    return limpio


def manglar_es_solo_del_traslado(texto):
    """True si la palabra «manglar» del texto la explica un MGX y no hay tour de manglar.

    El comunicado lo subraya: MGX es la experiencia de manglar DURANTE el traslado en
    bote, y no se debe confundir con MGS, que sí es el tour. El problema es que la
    descripción que acompaña al código lleva la palabra —«BT+MGX: Boat transfer +
    Experiencia de Manglar durante el traslado»— y el reconocimiento de tours busca
    «MANGLAR» por texto. Resultado: una salida de manglar en la hoja del día, con su
    guía y su bote apartados, para un tour que no existe.

    Se descarta solo cuando NADA respalda un tour de verdad: ni MGS, ni el código
    MANGLAR escrito en mayúsculas. Lo segundo se mira sensible a mayúsculas a propósito,
    apoyándose en la regla del comunicado —«todos los códigos en mayúsculas, sin
    excepciones»—: así «Manglar» en prosa no cuenta y «MANGLAR» como código sí.
    """
    if not re.search(r"\bMGX\b", texto, re.IGNORECASE):
        return False
    if re.search(r"\bMGS\b", texto, re.IGNORECASE):
        return False
    return not re.search(r"\bMANGLAR\b", texto)


def extract_text(pdf_path):
    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines.extend(text.split("\n"))
    return lines


def clean_lines(lines):
    return [l for l in lines if l.strip() and not NOISE_RE.match(l.strip())]


def parse_reservations(pdf_path):
    raw_lines = extract_text(pdf_path)
    lines = clean_lines(raw_lines)

    reservations = []
    current = None
    section = None  # 'notes' | 'rooming' | 'operacion' | 'notas'
    current_arrival_date = None

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        m_date = ARRIVAL_DATE_HEADER_RE.match(line)
        if m_date:
            current_arrival_date = m_date.group(1)
            i += 1
            continue

        m_row = _match_row(line)
        if m_row:
            if current:
                reservations.append(current)
            current = {
                "room_no": m_row.group("room"),
                "nombre_principal": m_row.group("name").strip(),
                "company_travel_agent": m_row.group("company").strip(),
                "arr_date": m_row.group("arr"),
                "dep_date": m_row.group("dep"),
                "room_type": m_row.group("roomtype"),
                "adl": int(m_row.group("adl")),
                "chl": int(m_row.group("chl")),
                "rooms": int(m_row.group("rms")),
                "mkt_code": m_row.group("mkt"),
                "src_code": m_row.group("src"),
                "res_status": m_row.group("status"),
                "conf_no": None,
                "arr_time": None,
                "adicionales_raw": "",
                "punto_entrada": None,
                "punto_salida": None,
                "punto_entrada_sin_confirmar": None,
                "punto_salida_sin_confirmar": None,
                "hora_vuelo_entrada": None,
                "hora_vuelo_salida": None,
                "vuelo_entrada": None,
                "vuelo_salida": None,
                "rooming": [],
                "operacion": [],
                "notas": "",
                "texto_completo": "",
            "block_code": None,
                "guia_sugerido": None,
                "vinculo_texto": None,
            }
            section = "notes"
            i += 1
            continue

        if current is None:
            i += 1
            continue

        m_conf = CONF_RE.match(line)
        if m_conf and current["conf_no"] is None:
            current["conf_no"] = m_conf.group("conf")
            current["arr_time"] = m_conf.group("time")
            i += 1
            continue

        section = procesar_linea(line, current, section)
        i += 1

    if current:
        reservations.append(current)

    return reservations


def bloque_vacio():
    """Un bloque de reserva con todas las llaves que procesar_linea() espera.

    Lo usan las dos fuentes: el PDF al abrir una reserva nueva, y Opera al leer el
    texto de las Reservation Notes.
    """
    return {
        "adicionales_raw": "",
        "punto_entrada": None,
        "punto_salida": None,
        "punto_entrada_sin_confirmar": None,
        "punto_salida_sin_confirmar": None,
        "hora_vuelo_entrada": None,
        "hora_vuelo_salida": None,
        "vuelo_entrada": None,
        "vuelo_salida": None,
        "rooming": [],
        "operacion": [],
        "notas": "",
        "texto_completo": "",
        "block_code": None,
        "guia_sugerido": None,
        "vinculo_texto": None,
    }


# Cómo se nombra cada punto de embarque en las notas. UNA sola tabla: opera_mapeo la
# importa de aquí, porque tener dos listas hacía que el mismo texto se leyera distinto
# según por dónde entrara —el lector de notas solo conocía «Sierpe» y «Drake», y además
# solo como PRIMERA palabra, así que «playa agujitas» quedaba pendiente en un camino y
# resuelto en el otro—.
#
# Punta Marenco va a Drake por decisión de operación: el bote que recoge ahí es el de
# Drake. Es un punto de recogida, no un punto de embarque aparte.
#
# Copa de Árbol entra por lo mismo, y lo pidió el lodge el 1 de noviembre: la reserva de
# la hab 04 del día 7 dice «Entrada: RECOGER EN COPA DEL ARBOL RESORT A LAS 14:30H» y el
# sistema la dejaba pendiente de punto. Es otro lodge de la misma costa, en la ruta del
# bote de Drake, igual que Punta Marenco. Se escriben las dos formas porque la nota usa
# las dos: «Copa de Árbol» y «Copa del Árbol».
PUNTOS_CONOCIDOS = {
    "SIERPE": "Sierpe",
    "DRAKE": "Drake",
    "DRK": "Drake",
    "AGUJITAS": "Drake",
    "BAHIA": "Drake",
    "PUNTA MARENCO": "Drake",
    "MARENCO": "Drake",
    "COPA DE ARBOL": "Drake",
    "COPA DEL ARBOL": "Drake",
}


def _sin_acentos(texto):
    return (str(texto).upper().replace("Í", "I").replace("Á", "A").replace("É", "E")
            .replace("Ó", "O").replace("Ú", "U"))


def punto_de(texto):
    """El punto de embarque que nombra ese texto, o None si no se puede asegurar.

    Devuelve None cuando el texto nombra DOS puntos distintos —«no por Sierpe, por
    Drake»—: ahí no hay una respuesta sino una frase que hay que leer, y mandar el bote
    por suposición es el error caro que este módulo existe para no cometer.
    """
    if not texto:
        return None
    arriba = _sin_acentos(texto)
    encontrados = {punto for palabra, punto in PUNTOS_CONOCIDOS.items()
                   if re.search(rf"\b{re.escape(palabra)}\b", arriba)}
    if len(encontrados) == 1:
        return encontrados.pop()
    return None


# Dónde termina el valor de «Entrada:» o «Salida:». Normalmente termina con la línea,
# pero la nota de Opera se puede escribir seguida —«INGRESO: Drake 2:45 PM SALIDA: Drake
# 9:25 AM»— y entonces el valor de la entrada se comía el de la salida. Con eso la hora
# de salida salía siendo la de llegada: el bote se apartaría para la hora equivocada.
_FIN_DE_CAMPO = re.compile(
    r"\s*(?:ENTRADA|INGRESO|SALIDA|ROOMING|OPERACI[OÓ]N|NOTAS|ADICIONALES)\s*:|-{3,}",
    re.IGNORECASE)


def _valor_del_campo(texto):
    """El valor del campo, cortado donde empieza el siguiente rótulo o separador."""
    m = _FIN_DE_CAMPO.search(texto)
    return (texto[:m.start()] if m else texto).strip(" -:·,")


def _anotar_hora_y_vuelo(current, valor, cual):
    """La hora y el vuelo que traiga el valor de ese campo, sin pisar lo ya encontrado.

    Se busca DENTRO del valor del campo y no en la línea entera, que es lo que hacía
    antes: en una nota escrita seguida, la línea lleva las dos horas y las dos se leían
    como la primera.

    LA HORA SE DECIDE CON `normalizar_hora`, NO CON `HORA_RE`. Parece un detalle y era el
    fallo: `HORA_RE` exige la marca a.m./p.m., y la nota del lodge escribe la hora pegada
    al número de vuelo y sin marca —«Entrada: Via Drake RZ1116 9:15»—. Así que la hora se
    descartaba en la puerta, antes de llegar al convertidor, que sí la entiende. El vuelo
    entraba y la hora no, y en la hoja de traslados ese huésped aparecía sin hora.
    """
    if not valor:
        return
    if not current.get(f"hora_vuelo_{cual}"):
        hora = normalizar_hora(valor)
        if hora:
            current[f"hora_vuelo_{cual}"] = hora
    if not current.get(f"vuelo_{cual}"):
        m_vuelo = VUELO_RE.search(valor)
        if m_vuelo:
            current[f"vuelo_{cual}"] = normalizar_vuelo(m_vuelo)


def leer_texto_de_reserva(texto, current=None):
    """Lee el bloque de texto de UNA reserva y devuelve sus campos.

    El texto puede venir del PDF o de las Reservation Notes de Opera Cloud: son el
    MISMO contenido con el mismo formato, porque el reporte imprime esa nota. Ejemplo
    real de Opera:

        Paquete 4D/3N -Full board
        PNC e ISLA
        Entrada: Via Sierpe
        Salida: Via Sierpe
        ---------------------------
        Rooming:
        <nombre> <pasaporte>
        ---------------------------
        Operacion:
        09: In
        10: PNC 123456
        11: ISLA 123456
        12: Out
        ---------------------------
        Notas:
        Viene con rsv 123456

    POR QUÉ SE COMPARTE EL LECTOR Y NO SE ESCRIBE OTRO: este formato lo escribe
    recepción a mano, así que tiene mil variantes —'Operación' con tilde y sin, el
    ROOMING con o sin dos puntos, el punto de embarque vacío o con texto libre—. Todas
    esas variantes ya están resueltas aquí, y cada corrección futura le sirve a las dos
    fuentes. Con dos lectores, arreglar una sola sería arreglarla a medias.
    """
    current = current if current is not None else bloque_vacio()
    section = None
    for linea in (texto or "").splitlines():
        linea = linea.rstrip()
        if not linea.strip():
            continue
        section = procesar_linea(linea, current, section)
    _sumar_los_de_prosa(current, texto)
    return current


def _sumar_los_de_prosa(current, texto):
    """Añade los tours que recepción escribió en prosa, sin pisar el itinerario.

    EL ITINERARIO MANDA. Si la sección de operación ya colocó ese tour, la frase no
    añade nada: lo más que puede hacer es decir que es privado o de cortesía, que es un
    dato que el itinerario a veces no trae.

    Y SI LOS DOS LO COLOCAN EN DÍAS DISTINTOS, no se elige: se deja el del itinerario y
    se avisa. Son dos personas escribiendo en la misma reserva y solo recepción sabe
    cuál es la buena; adivinar aquí pondría al guía en el muelle el día que no es.
    """
    en_prosa = tours_en_prosa(texto)
    if not en_prosa:
        return
    del_itinerario = {}
    for o in current.get("operacion") or []:
        if o.get("tour"):
            del_itinerario.setdefault(o["tour"], []).append(o)

    for t in en_prosa:
        ya = del_itinerario.get(t["tour"])
        if ya:
            mismo_dia = [o for o in ya if str(o.get("dia")) == str(t["dia"])]
            if mismo_dia:
                # La frase solo aporta la modalidad. 'or' y no '=': que el itinerario
                # diga PRV-PNC y la nota diga PNC no quita el privado.
                for o in mismo_dia:
                    o["privado"] = bool(o.get("privado")) or t["privado"]
                    o["cortesia"] = bool(o.get("cortesia")) or t["cortesia"]
            else:
                current.setdefault("actividades_no_reconocidas", []).append(
                    {"dia": t["dia"], "texto":
                     f"{t['tour']} — el itinerario lo pone el día "
                     f"{', '.join(str(o.get('dia')) for o in ya)} y una nota dice el día "
                     f"{t['dia']}. Revisar cuál es el bueno."})
            continue
        nuevo = {"dia": str(t["dia"]), "tour": t["tour"], "conf_entrada": None,
                 "privado": t["privado"], "cortesia": t["cortesia"], "de_prosa": True}
        if t["mes"]:
            nuevo["mes"] = t["mes"]
        current["operacion"].append(nuevo)
        del_itinerario.setdefault(t["tour"], []).append(nuevo)


def procesar_linea(line, current, section):
    """Una línea del bloque de una reserva. Devuelve la sección en que quedó.

    Es el estado del lector: qué sección se está leyendo (rooming, operación, notas).
    Está aparte para que el PDF y las notas de Opera usen exactamente el mismo código.
    """
    # Se acumula todo el texto del bloque de la reserva. Las menciones de
    # amenidades pueden aparecer en cualquier parte (línea de RESERVATION, la de
    # Rooming, las notas...), no solo en la sección NOTAS.
    current["texto_completo"] += " " + line

    # Código de bloque del PMS. Identifica reservas que viajan juntas cuando no
    # traen la nota "viene con rsv" — es el caso de los grupos de agencia, que
    # antes quedaban sin agrupar y se separaban en la distribución.
    if not current.get("block_code"):
        mb = BLOCK_RE.search(line)
        if mb and _es_block_code(line, mb.group(1)):
            current["block_code"] = mb.group(1)

    if True:
        if re.match(r"^\s*ROOMING\b", line, re.IGNORECASE):
            return "rooming"
        # El encabezado puede venir con texto pegado ("OPERACION, PENDIENTE ACOMODAR
        # PESCA Y WHALE WATCHING, POR ANDREY"), así que basta con que empiece por la
        # palabra. Antes se exigían los dos puntos y esas reservas quedaban sin itinerario.
        if re.match(r"^\s*OPERACI[OÓ]N\b", line, re.IGNORECASE):
            return "operacion"
        if re.match(r"^\s*NOTAS\b", line, re.IGNORECASE):
            return "notas"
        if set(line) <= {"-"}:
            return section

        m_adic = re.search(r"Adicionales:\s*(.+)", line)
        if m_adic:
            current["adicionales_raw"] = m_adic.group(1).strip()

        # El PDF usa indistintamente "Entrada:", "ENTRADA VIA", "INGRESO:" o "Ingreso via"
        # para el punto de llegada, y "Salida:" / "SALIDA:" para el de partida.
        # Puede haber varias líneas mencionando entrada/salida (ej. una vacía o con texto
        # libre como "Recoger en Jaguar Lodge", y más abajo la que sí trae el punto real),
        # por lo que se sigue buscando hasta encontrar un punto válido y no se sobreescribe
        # una vez encontrado.
        m_ent = re.search(r"(?:ENTRADA|INGRESO)\s*:?\s*(?:V[ÍI]A\s+)?(.*)$", line, re.IGNORECASE)
        if m_ent and not re.match(r"^\s*SALIDA", line, re.IGNORECASE):
            texto_ent = _valor_del_campo(m_ent.group(1))
            punto = punto_de(texto_ent)
            if punto:
                if not current["punto_entrada"]:
                    current["punto_entrada"] = punto
                    # Si antes se había marcado como pendiente (por una línea vacía o con
                    # texto libre), ya no hace falta: se encontró el punto real.
                    current["punto_entrada_sin_confirmar"] = None
                    _anotar_hora_y_vuelo(current, texto_ent, "entrada")
            else:
                # La reserva menciona un ingreso, pero sin un punto reconocido (Sierpe o
                # Drake). Puede estar vacío ("Entrada:"), decir PTE, o traer texto libre
                # ("Recogerlos en Punta Marenco 03:00 pm"). Se guarda para que el sistema
                # lo marque como pendiente de confirmar, en vez de perderlo en silencio.
                # Solo se marca si NO se encontró ya un punto válido en otra línea.
                if not current["punto_entrada"] and not current.get("punto_entrada_sin_confirmar"):
                    current["punto_entrada_sin_confirmar"] = texto_ent or "(vacío en la reserva)"
                # La HORA sí sirve aunque el punto no se reconozca, y es justo lo que hace
                # falta para ir a buscar al huésped. Antes se tiraba: de «Recogerlos en
                # Punta Marenco 03:00 pm» el sistema se quedaba con el texto y perdía las
                # 3:00 pm, así que recepción tenía que volver a abrir Opera para leerla.
                if not current["punto_entrada"]:
                    _anotar_hora_y_vuelo(current, texto_ent, "entrada")

        m_sal = re.search(r"SALIDA\s*:?\s*(?:V[ÍI]A\s+)?(.*)$", line, re.IGNORECASE)
        if m_sal:
            texto_sal = _valor_del_campo(m_sal.group(1))
            punto = punto_de(texto_sal)
            if punto:
                if not current["punto_salida"]:
                    current["punto_salida"] = punto
                    current["punto_salida_sin_confirmar"] = None
                    _anotar_hora_y_vuelo(current, texto_sal, "salida")
            else:
                if not current["punto_salida"] and not current.get("punto_salida_sin_confirmar"):
                    current["punto_salida_sin_confirmar"] = texto_sal or "(vacío en la reserva)"
                if not current["punto_salida"]:
                    _anotar_hora_y_vuelo(current, texto_sal, "salida")

        m_guia = re.search(r"Gu[ií]a\s+([A-ZÁÉÍÓÚÑa-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑa-záéíóúñ]+)?)", line)
        if m_guia:
            current["guia_sugerido"] = m_guia.group(1).strip()

        m_vinculo = re.search(r"Viene con\s+(?:l[ao]s?\s+)?rsvs?\.?\s*(?:de\s+)?(.+)", line, re.IGNORECASE)
        if m_vinculo:
            current["vinculo_texto"] = line.strip()

        if section == "rooming":
            # El PDF escribe la lista de huéspedes de muchas formas, y con frecuencia
            # agrega texto DESPUÉS del documento: la edad, restricciones alimentarias,
            # el tour que hará, la fecha de nacimiento. Antes se exigía que el documento
            # fuera lo último de la línea y se perdían 9 de cada 12 huéspedes.
            #   "SYLVIA ROSEMARIE PARSONAGE 310720286 55 YRS OLD"
            #   "Brittany McGinnis Okimura 641734480 Dietary Restrictions: No Pork BUCEO"
            #   "Alexandra Eloise Bradford A49668023 15años Buceo"
            #   "Jordan Coutts: US passport # A91576900"
            #   "Mark Steven Landsberkg – A31222424 Buceo"
            texto = line.strip()
            if (texto and not re.match(r"^-+$", texto)
                    and not texto.upper().startswith("ROOMING")):
                m_doc = DOC_RE.search(texto)
                if m_doc:
                    nombre = texto[:m_doc.start()]
                    # Se limpian etiquetas, nacionalidad y separadores del nombre.
                    # Ej. "Jordan Coutts: US passport # A915..." -> "Jordan Coutts"
                    nombre = re.sub(
                        r"[:,]?\s*(?:[A-Z]{2,3}\s+)?(?:Pasaporte\s*N\.?|Passport\s*number|"
                        r"passport\s*#?|Ced\.?|C[ÉE]DULA)\s*[:#]?\s*$",
                        "", nombre, flags=re.IGNORECASE)
                    nombre = re.sub(r"^(?:Mr|Mrs|Ms|Sr|Sra|Srta)\.?\s+", "", nombre.strip(" .,:#–-"),
                                    flags=re.IGNORECASE)
                    nombre = nombre.strip(" .,:#–-")
                    if nombre and sum(ch.isalpha() for ch in nombre) >= 3:
                        current["rooming"].append({"nombre": nombre,
                                                  "pasaporte": m_doc.group("doc")})
                else:
                    # Línea con solo el nombre, sin documento
                    solo = re.sub(r"^(?:Mr|Mrs|Ms|Sr|Sra|Srta)\.?\s+", "", texto,
                                  flags=re.IGNORECASE).strip(" .,:#–-")
                    if (len(solo.split()) >= 2 and ":" not in solo
                            and not re.search(r"\d", solo)
                            and all(ch.isalpha() or ch in " .,'-áéíóúñÁÉÍÓÚÑüÜöÖäÄ" for ch in solo)):
                        current["rooming"].append({"nombre": solo, "pasaporte": None})

        if section == "operacion":
            m_op = re.match(
                r"(\d{1,2}):?\s*(Check ?In|Check ?Out|Ingreso|Salida|In|Out)\b\s*(.*)$",
                line, re.IGNORECASE)
            if m_op:
                current["operacion"].append({"dia": m_op.group(1),
                                             "evento": m_op.group(2).upper()})
            # Si además de el evento la línea trae algo más (ej. "07: In + NW"), se
            # sigue analizando para no perder ese tour.
            if not m_op or (m_op.group(3) or "").strip(" +/-·,"):
                if m_op:
                    line = f"{m_op.group(1)}: {m_op.group(3)}"
                # El itinerario real viene como "NN: TOUR" o a veces "NN TOUR" (sin los
                # dos puntos). Después del itinerario suelen aparecer notas en texto libre
                # que también mencionan fechas y tours, pero escritas como fecha completa
                # (ej. "08/08 SNK para bruce - shared DIVING 09/08 PNC"). Esas notas se
                # reconocen por el patrón DD/MM y se guardan aparte, para no crear tours
                # fantasma con el día equivocado.
                parece_nota_con_fechas = bool(re.search(r"\d{1,2}\s*[/]\s*\d{1,2}", line))
                # «09:CIS» y «09: CIS» y «09 CIS». Lo primero se escribe de verdad —en
                # la base hay «09:C-EBT» y «09:CIS»— y se perdía entero porque el patrón
                # exigía un espacio detrás de los dos puntos.
                #
                # El (?=[^\d]) después de los dos puntos es lo que deja fuera una HORA:
                # sin él, «14:30» se leería como el día 14, y el 30 que viene detrás
                # acabaría buscándose como número de entrada del parque.
                m_dia = None if parece_nota_con_fechas else re.match(
                    r"(\d{1,2})(?::\s*(?=[^\d])|\s+)(.+)", line)
                if not m_dia:
                    texto_nota = line.strip()
                    # Se ignoran los días vacíos del itinerario (ej. "07:") y separadores
                    if (texto_nota and not set(texto_nota) <= {"-"}
                            and not re.fullmatch(r"\d{1,2}:?\s*", texto_nota)):
                        current.setdefault("notas_operacion", []).append(texto_nota)
                if m_dia:
                    dia, resto = m_dia.group(1), m_dia.group(2)
                    numeros = re.findall(r"\b(\d{5,7})\b", resto)
                    # DÓNDE apareció cada tour en la línea, no solo cuál apareció.
                    #
                    # Hace falta para leer el prefijo de modalidad. Antes se buscaba el
                    # código CANÓNICO en la línea —«SNORKEL» en «14: C-CIS»— y no estaba,
                    # porque lo que está escrito es el alias. Así que el «C-» no se leía y
                    # TODOS los códigos de la nomenclatura 2027 perdían su privado y su
                    # cortesía: el servicio entraba como compartido y de pago.
                    posicion_de = {}
                    encontrados = []
                    for code in TOUR_CODES:
                        m_code = re.search(rf"\b{code}\b", resto, re.IGNORECASE)
                        if m_code:
                            encontrados.append(code.upper())
                            posicion_de.setdefault(code.upper(), m_code.start())
                    # Revisar tambien alias conocidos (ej. "Horseback Riding" -> CABALGATA),
                    # evitando duplicar si el codigo real ya fue encontrado arriba.
                    resto_para_alias = resto
                    for alias, code_real in TOUR_ALIASES.items():
                        m_alias = re.search(rf"\b{re.escape(alias)}\b", resto_para_alias, re.IGNORECASE)
                        if m_alias:
                            if code_real not in encontrados:
                                encontrados.append(code_real)
                            # La posición se toma del texto ORIGINAL: resto_para_alias va
                            # perdiendo trozos y sus posiciones ya no sirven para mirar
                            # qué hay pegado delante del código.
                            m_orig = re.search(rf"\b{re.escape(alias)}\b", resto,
                                               re.IGNORECASE)
                            if m_orig:
                                posicion_de.setdefault(code_real, m_orig.start())
                            resto_para_alias = resto_para_alias[:m_alias.start()] + resto_para_alias[m_alias.end():]
                    # El manglar del traslado (MGX) no es el tour de manglar (MGS): sin
                    # esto, la descripción que acompaña al código pone una salida de
                    # manglar en la hoja del día que no existe. Ver la función.
                    if "MANGLAR" in encontrados and manglar_es_solo_del_traslado(resto):
                        encontrados.remove("MANGLAR")
                    if encontrados:
                        for idx, code in enumerate(encontrados):
                            conf = None
                            if len(numeros) == len(encontrados):
                                conf = numeros[idx]
                            elif len(numeros) == 1:
                                conf = numeros[0]
                            # La modalidad del catálogo 2027, si el código venía con
                            # prefijo. No cambia QUÉ tour es —un PNC privado sigue
                            # siendo la caminata a San Pedrillo— pero sí cómo se opera
                            # y cómo se cobra, así que se anota.
                            privado = cortesia = False
                            pos = posicion_de.get(code)
                            if pos is not None:
                                privado, cortesia = modalidad_antes_de(resto, pos)
                            current["operacion"].append(
                                {"dia": dia, "tour": code, "conf_entrada": conf,
                                 "privado": privado, "cortesia": cortesia})
                    # Lo que sobra en la línea después de quitar tours conocidos, alias, números de
                    # confirmación y modificadores conocidos (ej. "PRIV" de "privado"): si no es
                    # solo puntuación/espacios, es una actividad que no está en el catálogo
                    # (ej. una actividad realmente nueva) y se guarda para revisión, en vez de
                    # perderse silenciosamente — aunque la línea también tuviera un tour reconocido.
                    # Se avisa solo cuando el sistema NO logró identificar ninguna
                    # actividad en la línea. Si reconoció al menos una, el texto que
                    # sobra es contexto (quién coordina, la hora, una nota) y avisarlo
                    # sería un falso positivo: los avisos falsos enseñan a ignorar los
                    # avisos de verdad. El texto completo queda igual en las notas.
                    # EL BT («boat transfer»): un viaje de bote EXTRA que pide la
                    # reserva, escrito en el itinerario como cualquier otro día:
                    # «08: BT».
                    #
                    # Aquí el día viene DADO, y eso es lo que lo hace fiable: no hay que
                    # deducirlo de una frase en texto libre, donde un número suelto
                    # puede ser un precio, un vuelo o una hora. Antes esta línea se
                    # perdía en silencio —«BT» tiene dos letras y el aviso de actividad
                    # no reconocida pide más de dos— así que el viaje no llegaba a
                    # Transporte y nadie le asignaba bote ni capitán.
                    #
                    # «\bBT\b» no caza «C-EBT», que es otra cosa (cama o almohada extra)
                    # y aparece en la misma reserva.
                    if re.search(r"\bBT\b", resto, re.IGNORECASE):
                        current.setdefault("traslados_extra", []).append({"dia": dia})
                    if not encontrados:
                        resto_limpio = re.sub(r"\([^)]*\)", " ", resto)
                        resto_limpio = re.sub(
                            r"\b(?:Check\s?In|Check\s?Out|In|Out|Ingreso|Salida|"
                            r"x\d+|\d+x|am|pm|hrs?)\b", " ", resto_limpio, flags=re.IGNORECASE)
                        sobra = re.sub(r"[\d:\+\-/,\.\s&]+", " ", resto_limpio).strip()
                        if sobra and len(sobra) > 2:
                            current.setdefault("actividades_no_reconocidas", []).append(
                                {"dia": dia, "texto": resto.strip()}
                            )

        if section == "notas" and not line.upper().startswith("NOTAS"):
            current["notas"] += (" " + line)

    return section


def cross_reference_tours(adicionales_raw):
    found = []
    upper = adicionales_raw.upper()
    for code in TOUR_CODES:
        if code in upper:
            found.append(code)
    if "MONITOREO DE BALLENAS" in upper and "BALLENAS" not in found:
        found.append("BALLENAS")
    for alias, code_real in TOUR_ALIASES.items():
        if alias in upper and code_real not in found:
            found.append(code_real)
    # El manglar del traslado (MGX) no es el tour de manglar (MGS). Ver la función.
    if "MANGLAR" in found and manglar_es_solo_del_traslado(adicionales_raw):
        found.remove("MANGLAR")
    return found


if __name__ == "__main__":
    import json
    result = parse_reservations("/mnt/user-data/uploads/Arrivals__Detailed.PDF")
    print(f"Reservas encontradas: {len(result)}\n")
    for r in result[:2]:
        print(json.dumps(r, indent=2, ensure_ascii=False))
        print("Tours detectados:", cross_reference_tours(r["adicionales_raw"]))
        print("---")
