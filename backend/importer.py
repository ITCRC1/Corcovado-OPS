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
AMENIDADES_PATRONES = [
    ("Sofá cama extra", r"sof[áa]\s*cama"),
    # Nota: se busca "cliente VIP" y no solo "VIP", porque varios paquetes comerciales
    # se llaman "VIP Experience Package" y eso no implica una amenidad que preparar.
    ("Luna de miel / cliente VIP", r"luna\s+de\s+miel|honeymoon|aniversario|anniversary|cliente\s+vip|hu[ée]sped\s+vip"),
    ("Decoración por cumpleaños", r"cumplea[ñn]os|birthday|decoraci[óo]n"),
    ("Cena privada", r"cena\s+privada|private\s+dinner"),
    ("Botella de vino cortesía", r"botella\s+de\s+vino|vino\s+de\s+cortes[íi]a|champ[áa]n|champagne"),
    ("Frutas con chocolate cortesía", r"frutas?\s+con\s+chocolate|chocolate\s+covered"),
    ("Frutas de cortesía", r"frutas?\s+(?:de\s+)?cortes[íi]a|canasta\s+de\s+frutas"),
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

# Se mantiene la lista simple por compatibilidad con código existente
AMENIDADES_CATALOGO = [nombre for nombre, _ in AMENIDADES_PATRONES]


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


def detectar_amenidades(reserva):
    """Devuelve los nombres exactos del catálogo de amenidades mencionadas en la reserva.
    Busca en 'Adicionales' y en las notas libres, tolerando variantes de escritura."""
    texto = reserva.get("texto_completo") or f"{reserva.get('adicionales_raw','')} {reserva.get('notas','')}"
    encontradas = []
    for nombre_catalogo, patron in AMENIDADES_PATRONES:
        if re.search(patron, texto, re.IGNORECASE) and nombre_catalogo not in encontradas:
            encontradas.append(nombre_catalogo)
    return encontradas


def to_iso_date(arr_date_ddmmyy, dia_num):
    # arr_date viene como "23-07-26" (DD-MM-YY)
    dd, mm, yy = arr_date_ddmmyy.split("-")
    year, month, arr_day, dia_num = 2000 + int(yy), int(mm), int(dd), int(dia_num)
    # Si el día de "Operacion" es menor que el día de llegada, la estadía cruzó de mes
    # (ej. llega el 29 de julio, día "1" de Operacion es en realidad 1 de agosto).
    if dia_num < arr_day:
        month += 1
        if month > 12:
            month = 1
            year += 1
    return date(year, month, dia_num).isoformat()


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
    reservas = parse_reservations(pdf_path)
    for r in reservas:
        r["tours_detectados"] = cross_reference_tours(r["adicionales_raw"])
        r["grupo_link"] = detect_group_link(r)
        r.update(clasificar_notas(r["notas"]))
        r["amenidades_detectadas"] = detectar_amenidades(r)

    grupo_de = build_group_sets(reservas)

    entradas_sinac = {}  # key: (tour, fecha, conf_entrada) -> {pax_total, grupos: set, conf_nos: []}
    review_items = []

    for r in reservas:
        agenda = []
        for op in r["operacion"]:
            if "tour" not in op:
                continue
            fecha_iso = to_iso_date(r["arr_date"], op["dia"])
            contradiccion = detect_contradiction(r, op["tour"])
            agenda.append({
                "fecha": fecha_iso,
                "tour": op["tour"],
                "conf_entrada": op.get("conf_entrada"),
                "contradiccion": contradiccion,
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
                entradas_sinac[key]["pax_total"] += r["adl"] + r["chl"]
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
