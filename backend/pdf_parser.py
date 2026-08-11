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
HORA_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([ap])\.?\s?m\.?", re.IGNORECASE)
HORA_SIMPLE_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")

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
    return None


def normalizar_vuelo(match):
    return f"RZ{match.group(1)}"


TOUR_CODES = [
    "CLARO", "SPA",
    "PNC", "SIRENA", "BUCEO", "ISLA", "SNORKEL", "PAJAREO", "MANGLAR",
    "BALLENAS", "CABALGATA", "TREENET", "GTT", "NW", "PESCA",
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
    "GARDEN TO TABLE": "GTT",
    "SAN PEDRILLO": "PNC",
    "CANO ISLAND": "ISLA",
    "CAÑO ISLAND": "ISLA",
    "CLARO DEL BOSQUE": "CLARO",
    "CB": "CLARO",
    "MASAJES": "SPA",
    "MASAJE": "SPA",
    "SPA TREATMENT": "SPA",
}


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
                "guia_sugerido": None,
                "vinculo_texto": None,
            }
            section = "notes"
            i += 1
            continue

        if current is None:
            i += 1
            continue

        # Se acumula todo el texto del bloque de la reserva. Las menciones de
        # amenidades pueden aparecer en cualquier parte (línea de RESERVATION, la de
        # Rooming, las notas...), no solo en la sección NOTAS.
        current["texto_completo"] += " " + line

        m_conf = CONF_RE.match(line)
        if m_conf and current["conf_no"] is None:
            current["conf_no"] = m_conf.group("conf")
            current["arr_time"] = m_conf.group("time")
            i += 1
            continue

        if re.match(r"^\s*ROOMING\b", line, re.IGNORECASE):
            section = "rooming"
            i += 1
            continue
        # El encabezado puede venir con texto pegado ("OPERACION, PENDIENTE ACOMODAR
        # PESCA Y WHALE WATCHING, POR ANDREY"), así que basta con que empiece por la
        # palabra. Antes se exigían los dos puntos y esas reservas quedaban sin itinerario.
        if re.match(r"^\s*OPERACI[OÓ]N\b", line, re.IGNORECASE):
            section = "operacion"
            i += 1
            continue
        if re.match(r"^\s*NOTAS\b", line, re.IGNORECASE):
            section = "notas"
            i += 1
            continue
        if set(line) <= {"-"}:
            i += 1
            continue

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
            texto_ent = m_ent.group(1).strip()
            primera_palabra = texto_ent.split()[0].capitalize() if texto_ent.split() else ""
            if primera_palabra.lower() in ("sierpe", "drake"):
                if not current["punto_entrada"]:
                    current["punto_entrada"] = primera_palabra
                    # Si antes se había marcado como pendiente (por una línea vacía o con
                    # texto libre), ya no hace falta: se encontró el punto real.
                    current["punto_entrada_sin_confirmar"] = None
                    m_hora = HORA_RE.search(line)
                    if m_hora:
                        current["hora_vuelo_entrada"] = normalizar_hora(line)
                    m_vuelo = VUELO_RE.search(line)
                    if m_vuelo:
                        current["vuelo_entrada"] = normalizar_vuelo(m_vuelo)
            else:
                # El PDF menciona un ingreso, pero sin un punto reconocido (Sierpe/Drake).
                # Puede estar vacío ("Entrada:") o traer texto libre ("Recoger en Jaguar
                # Lodge"). Se guarda para que el sistema lo marque como pendiente de
                # confirmar, en vez de perderlo silenciosamente. Solo se marca si NO se
                # encontró ya un punto válido en otra línea de esta misma reserva.
                if not current["punto_entrada"] and not current.get("punto_entrada_sin_confirmar"):
                    current["punto_entrada_sin_confirmar"] = texto_ent or "(vacío en el PDF)"

        m_sal = re.search(r"SALIDA\s*:?\s*(?:V[ÍI]A\s+)?(.*)$", line, re.IGNORECASE)
        if m_sal:
            texto_sal = m_sal.group(1).strip()
            primera_palabra = texto_sal.split()[0].capitalize() if texto_sal.split() else ""
            if primera_palabra.lower() in ("sierpe", "drake"):
                if not current["punto_salida"]:
                    current["punto_salida"] = primera_palabra
                    current["punto_salida_sin_confirmar"] = None
                    m_hora = HORA_RE.search(line)
                    if m_hora:
                        current["hora_vuelo_salida"] = normalizar_hora(line)
                    m_vuelo = VUELO_RE.search(line)
                    if m_vuelo:
                        current["vuelo_salida"] = normalizar_vuelo(m_vuelo)
            else:
                if not current["punto_salida"] and not current.get("punto_salida_sin_confirmar"):
                    current["punto_salida_sin_confirmar"] = texto_sal or "(vacío en el PDF)"

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
                m_dia = None if parece_nota_con_fechas else re.match(r"(\d{1,2}):?\s+(.+)", line)
                if not m_dia:
                    texto_nota = line.strip()
                    # Se ignoran los días vacíos del itinerario (ej. "07:") y separadores
                    if (texto_nota and not set(texto_nota) <= {"-"}
                            and not re.fullmatch(r"\d{1,2}:?\s*", texto_nota)):
                        current.setdefault("notas_operacion", []).append(texto_nota)
                if m_dia:
                    dia, resto = m_dia.group(1), m_dia.group(2)
                    numeros = re.findall(r"\b(\d{5,7})\b", resto)
                    encontrados = [code.upper() for code in TOUR_CODES if re.search(rf"\b{code}\b", resto, re.IGNORECASE)]
                    # Revisar tambien alias conocidos (ej. "Horseback Riding" -> CABALGATA),
                    # evitando duplicar si el codigo real ya fue encontrado arriba.
                    resto_para_alias = resto
                    for alias, code_real in TOUR_ALIASES.items():
                        m_alias = re.search(rf"\b{re.escape(alias)}\b", resto_para_alias, re.IGNORECASE)
                        if m_alias:
                            if code_real not in encontrados:
                                encontrados.append(code_real)
                            resto_para_alias = resto_para_alias[:m_alias.start()] + resto_para_alias[m_alias.end():]
                    if encontrados:
                        for idx, code in enumerate(encontrados):
                            conf = None
                            if len(numeros) == len(encontrados):
                                conf = numeros[idx]
                            elif len(numeros) == 1:
                                conf = numeros[0]
                            current["operacion"].append({"dia": dia, "tour": code, "conf_entrada": conf})
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

        i += 1

    if current:
        reservations.append(current)

    return reservations


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
    return found


if __name__ == "__main__":
    import json
    result = parse_reservations("/mnt/user-data/uploads/Arrivals__Detailed.PDF")
    print(f"Reservas encontradas: {len(result)}\n")
    for r in result[:2]:
        print(json.dumps(r, indent=2, ensure_ascii=False))
        print("Tours detectados:", cross_reference_tours(r["adicionales_raw"]))
        print("---")
