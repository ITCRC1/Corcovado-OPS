"""Los informes: una hoja, el mismo formato en todas las areas, y en ingles.

Lo que se descargaba antes era una tabla plana de tres columnas, la misma para todo, sin
totales ni comparacion, y con secciones enteras fuera. Ahora cada area declara su informe
UNA vez y de ahi salen el PDF y el libro de Excel.

Lo que estas pruebas fijan, que es lo facil de romper sin darse cuenta:

  1. UNA pagina, en TODAS las areas. Basta con que un mes traiga un guia mas para que se
     desborde a la segunda hoja.
  2. El MISMO formato por dia y por mes.
  3. El PDF y el Excel salen de la MISMA definicion. Si divergieran, nadie sabria cual
     creer.
  4. Todo en INGLES: se mandan afuera.
"""
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun
from comun import cargar, reserva

import informe as inf
import informes_areas as areas

HOY = datetime.date.today()


def ddmmyy(d):
    return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"


def _sembrar(conn, dias=40, cuantas=30, cortesias=4):
    """Un periodo con de todo, para que los informes tengan que resumir."""
    import random
    random.seed(5)
    tours = ["PNC", "SIRENA", "SNORKEL", "MANGLAR", "NW", "BALLENAS", "CABALGATA"]
    inicio = HOY - datetime.timedelta(days=dias)
    lote = []
    for i in range(cuantas):
        llega = inicio + datetime.timedelta(days=random.randint(0, dias - 4))
        noches = random.choice([2, 3, 4])
        lote.append(reserva(
            f"80{i:04d}", f"{(i % 20) + 1:02d}", ddmmyy(llega),
            ddmmyy(llega + datetime.timedelta(days=noches)),
            estado="EN CASA", adl=random.choice([1, 2, 2, 3]),
            punto_entrada=random.choice(["Sierpe", "Drake"]),
            punto_salida=random.choice(["Sierpe", "Drake"]),
            # Ni la cortesia ni las amenidades se ponen a mano: se escriben en el texto
            # y las detecta el importador, que es como llegan de Opera.
            texto_completo=" ".join([
                "PAQUETE 3D/2N+ FULLBOARD CPL EN HOSPEDAJE" if i < cortesias
                else "PENSION COMPLETA",
                random.choice(["", "", "Gluten free diet", "no seafood",
                               "Honeymoon - luna de miel", "Vegetarian"]),
            ]).strip(),
            operacion=[{"dia": (llega + datetime.timedelta(days=d)).day,
                        "tour": random.choice(tours)}
                       for d in range(1, min(noches, 3))]))
    cargar(lote)
    botes = [r["nombre"] for r in conn.execute("SELECT nombre FROM bote")][:4]
    guias = [r["nombre"] for r in conn.execute("SELECT nombre FROM guia")][:6]
    for f in conn.execute("SELECT id FROM tour_asignado").fetchall():
        conn.execute("UPDATE tour_asignado SET bote_nombre=?, guia_nombre=? WHERE id=?",
                     (random.choice(botes), random.choice(guias), f["id"]))
    servicio = conn.execute("SELECT codigo FROM spa_servicio LIMIT 1").fetchone()
    terapeuta = conn.execute("SELECT nombre FROM spa_terapeuta LIMIT 1").fetchone()
    confs = [r["conf_no"] for r in conn.execute("SELECT conf_no FROM reserva")]
    for i in range(25):
        conn.execute(
            """INSERT INTO spa_cita (conf_no, fecha, servicio_codigo, minutos,
                                     terapeuta, estado, origen)
               VALUES (?,?,?,?,?,?,'HUESPED')""",
            (random.choice(confs),
             (inicio + datetime.timedelta(days=random.randint(0, dias))).isoformat(),
             servicio["codigo"], random.choice([50, 60, 80]),
             terapeuta["nombre"] if terapeuta else None,
             random.choice(["HECHA", "CONFIRMADA", "SOLICITADA", "CANCELADA"])))
    conn.commit()


def _paginas(buf):
    import pdfplumber
    buf.seek(0)
    with pdfplumber.open(buf) as pdf:
        return len(pdf.pages), "\n".join((p.extract_text() or "") for p in pdf.pages)


def _mes_pasado():
    fin = HOY.replace(day=1) - datetime.timedelta(days=1)
    return fin.replace(day=1).isoformat(), fin.isoformat()


# ---------------------------------------------------------------------------
# Que quepan, TODAS
# ---------------------------------------------------------------------------

def todas_las_areas_caben_en_una_hoja(c):
    """Es el requisito, y vale para las ocho: un informe de dos hojas ya no es un
    informe de una hoja."""
    conn = comun.base_limpia()
    _sembrar(conn)
    ini, fin = _mes_pasado()
    for area in areas.AREAS:
        n, _ = _paginas(areas.construir(area, conn, ini, fin, "pdf"))
        c.igual(n, 1, f"«{area}» de un mes ocupa UNA hoja")
    conn.close()


def todas_las_areas_caben_tambien_por_dia(c):
    conn = comun.base_limpia()
    _sembrar(conn)
    for area in areas.AREAS:
        n, _ = _paginas(areas.construir(area, conn, HOY.isoformat(), HOY.isoformat(), "pdf"))
        c.igual(n, 1, f"«{area}» de un dia ocupa UNA hoja")
    conn.close()


def un_periodo_sin_nada_no_revienta(c):
    """Un dia sin movimiento tiene que dar un informe que lo diga, no un error ni una
    hoja rota: se va a pedir en temporada baja."""
    conn = comun.base_limpia()
    lejos = (HOY + datetime.timedelta(days=300)).isoformat()
    for area in areas.AREAS:
        n, texto = _paginas(areas.construir(area, conn, lejos, lejos, "pdf"))
        c.igual(n, 1, f"«{area}» sin datos sigue siendo una hoja")
        c.cierto(len(texto) > 50, f"«{area}» sin datos sigue diciendo algo")
    conn.close()


# ---------------------------------------------------------------------------
# Que sea el MISMO formato
# ---------------------------------------------------------------------------

def el_formato_es_el_mismo_por_dia_y_por_mes(c):
    conn = comun.base_limpia()
    _sembrar(conn)
    ini, fin = _mes_pasado()
    _, mes = _paginas(areas.construir("analitica", conn, ini, fin, "pdf"))
    _, dia = _paginas(areas.construir("analitica", conn, HOY.isoformat(),
                                      HOY.isoformat(), "pdf"))
    for bloque in ("TOURS BY TYPE", "GUIDES", "BOATS", "EMBARKATION POINTS", "SPA",
                   "PERIOD SUMMARY", "PAX-NIGHTS", "COMPLIMENTARY"):
        c.cierto(bloque in mes, f"«{bloque}» esta en el informe del mes")
        c.cierto(bloque in dia, f"«{bloque}» esta tambien en el del dia")
    conn.close()


def todas_las_areas_tienen_la_misma_estructura(c):
    """Es lo que se pidio: el informe de Restaurantes se lee igual que el de Analitica."""
    conn = comun.base_limpia()
    _sembrar(conn)
    ini, fin = _mes_pasado()
    for area in areas.AREAS:
        spec = areas.AREAS[area](conn, ini, fin)
        c.cierto(spec.get("titulo"), f"«{area}» tiene titulo")
        c.cierto(len(spec.get("kpis") or []) >= 4,
                 f"«{area}» tiene su banda de cifras")
        c.cierto(len(spec.get("bloques") or []) >= 2,
                 f"«{area}» tiene al menos dos bloques de tabla")
        c.cierto(spec.get("lectura"), f"«{area}» tiene su parrafo de lectura")
        c.cierto(spec.get("datos"), f"«{area}» tiene su tabla plana para el Excel")
        for b in spec["bloques"]:
            c.igual(len(b["anchos"]), len(b["columnas"]),
                    f"«{area} / {b['titulo']}»: un ancho por columna")
    conn.close()


def el_pdf_y_el_excel_salen_de_la_misma_definicion(c):
    """Si salieran de dos codigos distintos, uno se quedaria viejo y nadie sabria cual
    creer. El libro lleva una hoja por bloque, con el mismo nombre y en el mismo orden."""
    import openpyxl
    conn = comun.base_limpia()
    _sembrar(conn)
    ini, fin = _mes_pasado()
    spec = areas.AREAS["analitica"](conn, ini, fin)
    wb = openpyxl.load_workbook(areas.construir("analitica", conn, ini, fin, "xlsx"))
    hojas = wb.sheetnames
    c.igual(hojas[0], "Summary", "el libro abre con el resumen")
    for i, b in enumerate(spec["bloques"]):
        c.igual(hojas[i + 1], b["titulo"][:31],
                f"la hoja {i + 2} es «{b['titulo']}», igual que en el PDF")
    for esperada in ("Trend", "Data", "Glossary"):
        c.cierto(esperada in hojas, f"y el libro trae «{esperada}»")
    ws = wb["Data"]
    c.cierto("Records" in list(ws.tables),
             "la hoja de datos es una TABLA de Excel, para poder pivotear")
    c.cierto(ws.freeze_panes is not None, "con el encabezado fijo")
    conn.close()


def el_excel_guarda_numeros_no_texto(c):
    import openpyxl
    conn = comun.base_limpia()
    _sembrar(conn)
    ini, fin = _mes_pasado()
    wb = openpyxl.load_workbook(areas.construir("analitica", conn, ini, fin, "xlsx"))
    ws = wb["Summary"]
    c.cierto(any(isinstance(ws.cell(row=r, column=2).value, (int, float))
                 for r in range(5, 12)), "los valores son numeros")
    c.igual(ws.cell(row=5, column=4).number_format, "0.0%",
            "y la variacion lleva formato de porcentaje")
    conn.close()


# ---------------------------------------------------------------------------
# En ingles
# ---------------------------------------------------------------------------

def los_informes_salen_en_ingles(c):
    """Se mandan a inversionistas y socios que no leen espanol. La pantalla sigue en
    espanol; lo que cambia es lo que se imprime."""
    conn = comun.base_limpia()
    _sembrar(conn)
    ini, fin = _mes_pasado()
    # Palabras que delatan que quedo texto en espanol en la parte que se IMPRIME. No se
    # buscan nombres propios ni datos: Sierpe, Drake o los tours se quedan como estan.
    delatoras = re.compile(
        r"\b(Informe|Reporte|Periodo|Resumen|Guías|Botes|Cortesías|Comparado|"
        r"Generado|Página|Fecha|Huésped|Salidas|Tratamiento|Alcance)\b")
    for area in areas.AREAS:
        _, texto = _paginas(areas.construir(area, conn, ini, fin, "pdf"))
        encontradas = sorted(set(delatoras.findall(texto)))
        c.igual(encontradas, [], f"«{area}» no imprime palabras en espanol")
    conn.close()


def los_meses_y_los_estados_van_en_ingles(c):
    c.igual(inf.titulo_del_periodo("2026-03-01", "2026-03-31"), "March 2026",
            "un mes completo se dice por su nombre, en ingles")
    c.igual(inf.titulo_del_periodo("2026-03-10", "2026-03-10"), "March 10, 2026",
            "un dia, con su fecha")
    c.igual(areas._ingles_estado("HECHA"), "completed", "los estados se traducen")
    c.igual(areas._ingles_estado("SOLICITADA"), "requested", "todos")


# ---------------------------------------------------------------------------
# Lo que cambia entre un dia y un mes
# ---------------------------------------------------------------------------

def un_mes_se_compara_con_el_mes_anterior(c):
    """Comparar un mes contra «los 30 dias de antes» corre el corte y mezcla dos meses."""
    c.igual(inf.periodo_anterior("2026-03-01", "2026-03-31"),
            ("2026-02-01", "2026-02-28"), "marzo se compara con febrero entero")
    c.igual(inf.periodo_anterior("2026-01-01", "2026-01-31"),
            ("2025-12-01", "2025-12-31"), "enero, con diciembre del ano anterior")
    c.igual(inf.periodo_anterior("2026-03-05", "2026-03-11"),
            ("2026-02-26", "2026-03-04"), "una semana, con la semana de antes")
    c.igual(inf.periodo_anterior("2026-03-10", "2026-03-10"),
            ("2026-03-09", "2026-03-09"), "un dia, con el dia anterior")


def la_tendencia_se_adapta_al_largo_del_periodo(c):
    """«Por semana» no significa nada en un informe de un dia."""
    conn = comun.base_limpia()
    _sembrar(conn)
    _, _, _, titulo_mes = inf.serie_de_tendencia(
        conn, (HOY - datetime.timedelta(days=29)).isoformat(), HOY.isoformat())
    c.cierto("week" in titulo_mes, "un mes se grafica por semana")

    valores, _, dentro, titulo_dia = inf.serie_de_tendencia(
        conn, HOY.isoformat(), HOY.isoformat())
    c.cierto("day" in titulo_dia, "un dia se grafica por dia")
    c.cierto(len(valores) >= inf.MINIMO_BARRAS,
             "y se completa hacia atras para tener con que comparar")
    c.igual(dentro.count(True), 1, "solo la barra del dia pedido es del periodo")
    c.igual(dentro[-1], True, "y es la ultima")
    conn.close()


# ---------------------------------------------------------------------------
# Que los numeros sean los de la pantalla
# ---------------------------------------------------------------------------

def ninguna_tendencia_sale_entera_en_cero(c):
    """El fallo que costo mas de encontrar: las consultas que agrupan por la fecha de la
    reserva devuelven la clave en YY-MM-DD y la serie la busca en ISO. Sin convertirla no
    encontraba NADA y el grafico salia entero en cero, sin dar ningun error — que es la
    peor forma de fallar, porque un cero se lee como «no hubo nadie»."""
    conn = comun.base_limpia()
    _sembrar(conn)
    ini, fin = _mes_pasado()
    for area in areas.AREAS:
        spec = areas.AREAS[area](conn, ini, fin)
        t = spec.get("tendencia")
        if not t or not t["valores"]:
            continue
        c.cierto(sum(t["valores"]) > 0,
                 f"la tendencia de «{area}» tiene datos, no puros ceros")
    conn.close()


def las_etiquetas_caben_en_su_casilla(c):
    """Con siete casillas cada una tiene 26 mm. Una etiqueta larga se parte en dos
    renglones y se monta encima del numero."""
    conn = comun.base_limpia()
    _sembrar(conn)
    ini, fin = _mes_pasado()
    for area in areas.AREAS:
        spec = areas.AREAS[area](conn, ini, fin)
        ancho = inf.ANCHO / len(spec["kpis"]) / inf.mm
        for etiqueta, *_ in spec["kpis"]:
            # ~1.55 mm por caracter a 6.2 pt en mayusculas, medido sobre la hoja.
            c.cierto(len(etiqueta) * 1.55 <= ancho + 1,
                     f"«{area}»: la etiqueta «{etiqueta}» cabe en {ancho:.0f} mm")
        for b in spec["bloques"]:
            for i, col in enumerate(b["columnas"]):
                if col[0] == b.get("barra_en"):
                    continue
                mm_col = b["anchos"][i] / inf.mm
                c.cierto(len(col[1]) * 1.35 <= mm_col + 2,
                         f"«{area} / {b['titulo']}»: «{col[1]}» cabe en {mm_col:.0f} mm")
    conn.close()


def las_cortesias_se_cuentan_no_se_valoran(c):
    conn = comun.base_limpia()
    _sembrar(conn, cortesias=4)
    m = inf.metricas(conn, (HOY - datetime.timedelta(days=40)).isoformat(),
                     HOY.isoformat())
    c.igual(m["cortesias"], 4, "cuenta las reservas marcadas como cortesia")
    c.cierto(m["cortesias_pax"] >= 4, "y su gente")
    conn.close()


def la_ocupacion_usa_el_mismo_total_que_la_pantalla(c):
    """Si el informe contara las habitaciones de otra forma, diria un porcentaje distinto
    al de la pantalla de ocupacion y nadie sabria cual creer."""
    conn = comun.base_limpia()
    llega = HOY - datetime.timedelta(days=1)
    cargar([reserva(f"90{i}", f"{i:02d}", ddmmyy(llega),
                    ddmmyy(HOY + datetime.timedelta(days=2)), estado="EN CASA", adl=2)
            for i in range(1, 11)])
    m = inf.metricas(conn, HOY.isoformat(), HOY.isoformat(), habitaciones=20)
    c.igual(m["ocupacion"], 50, "10 habitaciones de 20 es 50%")
    c.igual(m["pax_noche"], 20, "y 20 pax durmiendo")
    conn.close()


def el_spa_si_entra_en_el_informe(c):
    """El reporte viejo dejaba el spa fuera aunque la pantalla lo mostraba."""
    conn = comun.base_limpia()
    _sembrar(conn)
    ini, fin = _mes_pasado()
    _, texto = _paginas(areas.construir("analitica", conn, ini, fin, "pdf"))
    c.cierto("SPA" in texto, "el spa aparece en la hoja")
    conn.close()


# ---------------------------------------------------------------------------
# La hoja del dia que se le manda al staff
# ---------------------------------------------------------------------------

def la_hoja_del_dia_cabe_en_el_ancho(c):
    """El fallo que esta prueba evita NO DA ERROR: recorta.

    Con las columnas sumando mas de lo que mide la hoja, la tabla se sale por los dos
    lados y la primera columna se lee «CASA» en vez de «EN CASA» — justo la que dice de
    un vistazo quien llega y quien se va. El PDF se genera igual, asi que nadie se
    entera hasta que alguien lee el pantallazo en el muelle.

    A4 apaisado son 297 mm y los margenes se comen 14."""
    import hoja_dia
    ancho = sum(col[2] for col in hoja_dia.COLUMNAS)
    c.cierto(ancho <= hoja_dia.ANCHO_UTIL_MM,
             f"las columnas caben en la hoja ({ancho} mm de {hoja_dia.ANCHO_UTIL_MM})")
    c.igual(len(hoja_dia.COLUMNAS), sum(n for _, n in hoja_dia.GRUPOS),
            "los grupos de la cabecera cubren todas las columnas")


def _hoja_falsa(cuantas, tours=0, pesadas=0):
    """Una definicion de hoja con el volumen que se le pida.

    Se arma a mano y no desde `definicion()` porque lo que se esta probando aqui es el
    DIBUJO: cuanta hoja ocupa y si cabe. Montar 40 reservas de verdad en la base para
    medir un PDF seria probar el cargador otra vez y tardar veinte veces mas.

    `pesadas` son las filas que llevan el nombre y la nota mas largos vistos en Opera
    —tres renglones cada una—. Se cuentan aparte porque son LA variable: lo que hace
    crecer la hoja no es cuantas filas hay sino cuantos renglones ocupa cada una. En el
    dia mas cargado de los proximos cuatro meses, 2 de 34 son asi.
    """
    largo = ("MARIA GUADALUPE FERNANDEZ DE LA TORRE Y JUAN SEBASTIAN ECHEVERRIA "
             "MONTOYA Y ANA CRISTINA ECHEVERRIA FERNANDEZ")
    nota = ("CLIENTES SE HIPER CUIDAN CON EL COVID Y POR ESO RESERVARON TODO PRIVADO, "
            "DE MOMENTO EL TRANSPORTE DE SALIDA ESTA PENDIENTE DE CONFIRMAR")
    filas = []
    for i in range(cuantas):
        estado = ("ENTRA", "SALE", "EN CASA")[i % 3]
        pesada = i < pesadas
        filas.append({
            "estado": estado,
            "hab": f"{i + 1:02d}",
            "huesped": largo if pesada else "DEREK JOHNSON Y ANDREA OGG",
            "conf_no": f"90{i:04d}",
            "pax": 2,
            "sierpe": 2 if estado == "ENTRA" else "",
            "drake": 2 if estado == "SALE" else "",
            "horario": "7:10 a.m." if estado != "EN CASA" else "",
            "guia_t": "", "bote_t": "",
            "notas": nota if pesada else "VUELO RZ1116",
            "tours": [],
            "tour": "SNORKEL", "tour_guia": "", "tour_bote": "",
        })
    return {
        "fecha": HOY.isoformat(),
        "filas": filas,
        "tours": [{"tour_codigo": "SNORKEL", "grupo_operativo": "A", "es_privado": 0,
                   "pax_total": 4, "guia_nombre": None, "bote_nombre": None,
                   "horario_inicio": "08:00"} for _ in range(tours)],
        "totales_punto": {"Sierpe": {"ENTRA": 4, "SALE": 0},
                          "Drake": {"ENTRA": 0, "SALE": 4}},
        "movimientos": [("ENTRA", 2, 4), ("SALE", 2, 4), ("EN CASA", 8, 16)],
        "pax_desayunos": 20, "pax_en_casa": 16,
        "alertas": [("Tours sin guia", tours, "Agenda de tours"),
                    ("Tours sin bote", tours, "Transporte"),
                    ("Habs. sin asignar", 0, "Reservas"),
                    ("Corridas sin cubrir", 0, "Transporte"),
                    ("Tours el dia que se va", 0, "Agenda de tours")],
    }


def la_hoja_del_dia_cabe_SIEMPRE_en_una_pagina(c):
    """El fallo que esta prueba evita tampoco da error: PARTE.

    Lo pidio el lodge —«hay dias que estan quedando en 2 paginas y me gustaria ver todo
    en una pagina siempre»— y la segunda pagina es la que se pierde: la hoja se
    fotografia para mandarla al grupo y nadie manda dos fotos. Con la letra fija de
    antes, 27 de los 73 dias con operacion se partian.

    Se prueban volumenes de 1 a 40 habitaciones y, encima, con UN TERCIO de las filas
    llevando el nombre y la nota mas largos de Opera — un dia bastante peor que
    cualquiera de los proximos cuatro meses.
    """
    import hoja_dia
    for cuantas in (1, 8, 18, 28, 34, 40):
        d = _hoja_falsa(cuantas, tours=4, pesadas=cuantas // 3)
        paginas, texto = _paginas(hoja_dia.pdf(d))
        c.igual(paginas, 1, f"con {cuantas} habitaciones la hoja es UNA")
        # Caber no puede significar perder filas por el camino: la primera y la ultima
        # habitacion tienen que estar las dos en el papel.
        c.cierto("01" in texto and f"{cuantas:02d}" in texto,
                 f"con {cuantas} habitaciones no se queda ninguna fuera")


def la_letra_de_la_hoja_se_adapta_al_dia(c):
    """Un dia flojo se lee mas grande, uno cargado mas chico, y los dos en una hoja.

    No es cosmetica: la hoja se mira en un telefono. Dejar la letra de un dia de 34
    habitaciones en un dia de 3 es mandar un pantallazo con el tercio de arriba escrito
    y dos tercios en blanco.
    """
    import hoja_dia
    import pdfplumber
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    ancho_hoja, alto_hoja = landscape(A4)
    ancho, alto = ancho_hoja - 14 * mm - 12, alto_hoja - 16 * mm - 12

    # 34 habitaciones con 2 filas pesadas es, medido, el peor dia de los proximos cuatro
    # meses en la base de verdad.
    peor = _hoja_falsa(34, tours=4, pesadas=2)
    flojo, _ = hoja_dia._la_letra_que_cabe(_hoja_falsa(3, tours=1), ancho, alto)
    cargado, _ = hoja_dia._la_letra_que_cabe(peor, ancho, alto)
    c.cierto(flojo > cargado,
             f"el dia flojo se escribe mas grande que el cargado ({flojo} vs {cargado})")
    c.cierto(flojo <= hoja_dia.MAS_GRANDE and cargado >= hoja_dia.MAS_CHICA,
             "los dos se quedan dentro de los limites de tamaño")
    # Y el peor dia real no se encoge de mas: tiene que seguir leyendose en el muelle.
    c.cierto(hoja_dia.FUENTE * cargado >= 5.5,
             f"el peor dia no baja de 5,5 pt (sale a {hoja_dia.FUENTE * cargado:.2f})")

    buf = hoja_dia.pdf(peor)
    buf.seek(0)
    with pdfplumber.open(buf) as pdf:
        c.cierto(abs(pdf.pages[0].width - ancho_hoja) < 1
                 and abs(pdf.pages[0].height - alto_hoja) < 1,
                 "y cabe en A4 apaisado, que es el papel que hay en la oficina")


def el_renglon_de_la_hoja_encoge_con_la_letra(c):
    """La trampa que hacia que la hoja se partiera aun con letra chica.

    `FONTSIZE` en una tabla de ReportLab NO toca la interlinea, que se queda en los
    12 pt de fabrica. Sin poner `LEADING` a mano, la letra encogia y el renglon no: cada
    fila seguia midiendo lo mismo y encoger la letra no servia de nada.

    Se mide el bloque de verdad: a mitad de tamaño, la tabla tiene que ocupar mas o
    menos la mitad. Con el fallo puesto ocupaba el 85%.
    """
    import hoja_dia
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    ancho = landscape(A4)[0] - 14 * mm - 12
    d = _hoja_falsa(20)
    entera = hoja_dia._historia(d, 1.0)[-1].wrap(ancho, 0x7FFFFFFF)[1]
    mitad = hoja_dia._historia(d, 0.5)[-1].wrap(ancho, 0x7FFFFFFF)[1]
    c.cierto(mitad / entera < 0.62,
             f"a media letra la tabla ocupa media hoja (salio {mitad / entera:.0%})")


def la_hoja_no_parte_las_palabras_por_la_mitad(c):
    """«SNORKE / L» en la columna de TOUR.

    Pasaba al crecer la letra: ReportLab parte la palabra sin avisar y un codigo de tour
    partido no es un codigo ilegible, es OTRO codigo. Se comprueba la regla y no el
    sintoma: a la escala que la hoja elige, ninguna palabra de ninguna columna puede
    medir mas que su casilla. Con los codigos de verdad del catalogo, que es donde
    viven «CABALGATA» y «SAN JOSECITO».
    """
    import hoja_dia
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.lib.pagesizes import A4, landscape
    ancho_hoja, alto_hoja = landscape(A4)

    conn = comun.base_limpia()
    codigos = [f["codigo"] for f in conn.execute(
        "SELECT codigo FROM tour_catalogo ORDER BY codigo")]
    conn.close()
    c.cierto(len(codigos) > 10, "el catalogo trae los codigos de verdad")

    d = _hoja_falsa(len(codigos), tours=0)
    for fila, codigo in zip(d["filas"], codigos):
        fila["tour"] = codigo
        fila["tour_bote"] = "TAMANDUA"
        fila["tour_guia"] = "EXTERNO"
    k, _ = hoja_dia._la_letra_que_cabe(
        d, ancho_hoja - 14 * mm - 12, alto_hoja - 16 * mm - 12)

    for clave, titulo, ancho in hoja_dia.COLUMNAS:
        hueco = ancho * mm - 2 * hoja_dia.MARGEN_CELDA * k
        for fila in d["filas"]:
            for palabra in str(fila.get(clave) or "").split():
                mide = stringWidth(palabra, "Helvetica", hoja_dia.FUENTE * k)
                c.cierto(mide <= hueco,
                         f"«{palabra}» cabe entero en la columna {titulo} "
                         f"({mide:.1f} pt de {hueco:.1f})")


def un_nombre_larguisimo_encoge_la_hoja_en_vez_de_partirlo(c):
    """El techo tiene que MORDER, no solo existir.

    El dia que el lodge invente un tour con un nombre mas largo que la columna, la hoja
    tiene que crecer menos — no partir la palabra. Es lo que convierte la regla en algo
    que se mantiene solo.
    """
    import hoja_dia
    normal = hoja_dia._techo_por_las_palabras(_hoja_falsa(4, tours=1))
    d = _hoja_falsa(4, tours=1)
    d["filas"][0]["tour"] = "CONTRACORRIENTE"
    apretado = hoja_dia._techo_por_las_palabras(d)
    c.cierto(apretado < normal,
             f"un codigo larguisimo baja el techo ({apretado:.2f} vs {normal:.2f})")
    c.cierto(apretado >= hoja_dia.MAS_CHICA,
             "pero nunca por debajo del suelo: eso seria arreglar la columna, no la hoja")


def un_dia_imposible_alarga_el_papel_pero_no_lo_parte(c):
    """El ultimo recurso. No se ha visto un dia asi —el peor de los proximos cuatro
    meses tiene 34 habitaciones— pero si llega, que llegue entero: antes que partir la
    hoja en dos se alarga el papel, que la impresora ajusta sola al folio."""
    import hoja_dia
    import pdfplumber
    from reportlab.lib.pagesizes import A4, landscape
    buf = hoja_dia.pdf(_hoja_falsa(120, tours=10, pesadas=60))
    buf.seek(0)
    with pdfplumber.open(buf) as pdf:
        c.igual(len(pdf.pages), 1, "120 habitaciones siguen siendo UNA pagina")
        c.cierto(pdf.pages[0].height > landscape(A4)[1],
                 "el papel se alarga en vez de partirse")


def la_hoja_del_dia_sale_en_pdf_y_en_excel(c):
    """De punta a punta, con datos de verdad. Y los DOS formatos de la MISMA definicion:
    el pantallazo que circula por WhatsApp es el que nadie contrasta, asi que no puede
    decir algo distinto del Excel."""
    import hoja_dia
    conn = comun.base_limpia()
    llega = ddmmyy(HOY)
    sale = ddmmyy(HOY + datetime.timedelta(days=3))
    lote = [dict(reserva(700100, "07", llega, sale, adl=2), punto_entrada="Sierpe"),
            dict(reserva(700101, "12", llega, sale, adl=2), punto_entrada="Drake",
                 hora_vuelo_entrada="14:45", vuelo_entrada="RZ1124")]
    cargar(lote, vistas=lote)

    resumen = {
        "ingresos": [{"conf_no": "700100", "room_no": "07",
                      "nombre_principal": "Johnson/Derek", "adl": 2, "chl": 0},
                     {"conf_no": "700101", "room_no": "12",
                      "nombre_principal": "Grimm/Christine", "adl": 2, "chl": 0}],
        "salidas": [], "en_casa": [], "tours": [],
        "puntos": [{"punto": "Sierpe", "detalle": [
            {"tipo": "Entrada", "room_no": "07", "pax": 2, "hora": None,
             "hora_traslado": "11:30 a.m.", "guia": None, "bote": None}]}],
        "total_ingresos": 2, "pax_ingresos": 4, "total_salidas": 0, "pax_salidas": 0,
        "total_en_casa": 2, "pax_en_casa": 4, "pax_desayunos": 4,
    }
    d = hoja_dia.definicion(conn, HOY.isoformat(), resumen)
    conn.close()

    c.igual(len(d["filas"]), 2, "una fila por habitacion")
    # El nombre se escribe como lo escribe el lodge, no como lo guarda el PMS.
    c.cierto(all("/" not in f["huesped"] for f in d["filas"]),
             "el nombre sale legible, no «Apellido/Nombre»")
    c.igual(d["totales_punto"]["Sierpe"]["ENTRA"], 2, "el pax va al muelle que le toca")

    paginas, texto = _paginas(hoja_dia.pdf(d))
    c.igual(paginas, 1, "el PDF es de UNA hoja: es lo que se fotografia")
    for esperado in ("HUÉSPEDES", "INGRESOS Y SALIDAS", "ACTIVIDADES", "IN HOUSE"):
        c.cierto(esperado in texto, f"el PDF trae «{esperado}»")
    # La columna de estado tiene que salir ENTERA. Es la comprobacion que habria
    # cazado el recorte, y la que no se ve mirando si «el PDF se genero».
    c.cierto("ENTRA" in texto, "y el estado sin recortar")

    from openpyxl import load_workbook
    wb = load_workbook(hoja_dia.excel(d))
    ws = wb.active
    cabeceras = [ws.cell(row=12, column=i).value for i in range(1, len(hoja_dia.COLUMNAS) + 1)]
    c.igual(cabeceras, [col[1] for col in hoja_dia.COLUMNAS],
            "el Excel lleva las MISMAS columnas que el PDF, en el mismo orden")


def la_hoja_del_dia_enseña_los_DOS_tours_del_mismo_dia(c):
    """Lo pidio el lodge: «cuando un cliente tiene 2 tours el mismo dia, ejemplo EBT y
    NW, solo se refleja un tour, hay que corregir el resto porque perdemos informacion».

    Es la combinacion normal: el pajareo de las 6 de la manana y la caminata nocturna de
    las 17:45. Quedarse con el primero no da error — da una hoja en la que el segundo
    guia no existe. Medido sobre la base real: nueve reservas con dos tours el mismo dia.

    Y los tres renglones tienen que leerse EN PARALELO: la primera linea de GUIA es la
    del primer tour. Si no, con un guia asignado y otro no, no habria forma de saber a
    cual de los dos le falta.
    """
    import hoja_dia
    conn = comun.base_limpia()
    resumen = {
        "ingresos": [], "salidas": [], "puntos": [],
        "en_casa": [{"conf_no": "810001", "room_no": "08",
                     "nombre_principal": "Johnson/Derek", "adl": 2, "chl": 0}],
        "tours": [
            {"tour_codigo": "NW", "horario_inicio": "17:45", "reservas": "810001",
             "habitaciones": "08", "guia_nombre": "Marvin", "bote_nombre": None},
            {"tour_codigo": "PAJAREO", "horario_inicio": "06:00", "reservas": "810001",
             "habitaciones": "08", "guia_nombre": None, "bote_nombre": None},
        ],
        "total_ingresos": 0, "pax_ingresos": 0, "total_salidas": 0, "pax_salidas": 0,
        "total_en_casa": 1, "pax_en_casa": 2, "pax_desayunos": 2,
    }
    d = hoja_dia.definicion(conn, HOY.isoformat(), resumen)
    conn.close()

    fila = d["filas"][0]
    c.igual(fila["tour"], "PAJAREO\nNW", "salen los dos, y en el orden de la jornada")
    c.igual(fila["tour_guia"], "—\nMarvin",
            "el guia va en el renglon de SU tour, con el hueco marcado")
    c.igual(fila["tour_bote"], "",
            "y sin ningun bote puesto la casilla va vacia, no una columna de guiones")

    # Y que el PDF los dibuje los dos: una celda de texto suelto no parte la linea, asi
    # que el segundo tour se saldria de la casilla sin dar error.
    paginas, texto = _paginas(hoja_dia.pdf(d))
    c.igual(paginas, 1, "sigue siendo de una hoja")
    for esperado in ("PAJAREO", "NW", "Marvin"):
        c.cierto(esperado in texto, f"el PDF trae «{esperado}»")


def _resumen_de_un_dia(conf_sale, conf_entra, hab):
    """Un dia con una habitacion que CAMBIA DE HUESPED: uno sale por Drake y otro entra
    por Sierpe, los dos en el mismo cuarto. Es el caso del 8 de noviembre."""
    return {
        "ingresos": [{"conf_no": conf_entra, "room_no": hab,
                      "nombre_principal": "Llega/Marta", "adl": 2, "chl": 0}],
        "salidas": [{"conf_no": conf_sale, "room_no": hab,
                     "nombre_principal": "SeVa/Pedro", "adl": 2, "chl": 0}],
        "en_casa": [], "tours": [],
        "puntos": [
            {"punto": "Drake", "detalle": [
                {"tipo": "Salida", "conf_no": conf_sale, "room_no": hab, "pax": 2,
                 # La hora del VUELO es las 9:10; el bote sale DOS HORAS antes.
                 "hora": "9:10 a.m.", "hora_traslado": "7:10 a.m.",
                 "vuelo": "RZ5759", "guia": None, "bote": None}]},
            {"punto": "Sierpe", "detalle": [
                {"tipo": "Entrada", "conf_no": conf_entra, "room_no": hab, "pax": 2,
                 "hora": None, "hora_traslado": "11:30 a.m.",
                 "vuelo": None, "guia": None, "bote": None}]},
        ],
        "total_ingresos": 1, "pax_ingresos": 2, "total_salidas": 1, "pax_salidas": 2,
        "total_en_casa": 0, "pax_en_casa": 0, "pax_desayunos": 2,
    }


def el_horario_de_la_hoja_es_el_del_traslado_no_el_del_vuelo(c):
    """Lo pidio el lodge y lo vio en la hoja del 8 de noviembre.

    HORARIO es la hora a la que el huesped SE MUEVE, que es lo unico que el staff puede
    ejecutar: por Sierpe el bote sale a su hora fija y por Drake sale DOS HORAS ANTES del
    vuelo. Poniendo la del vuelo, la hoja mandaba al muelle a las 9:10 a gente cuyo bote
    salia a las 7:10 — y no daba ningun error, daba una hora creible y equivocada.
    """
    import hoja_dia
    conn = comun.base_limpia()
    d = hoja_dia.definicion(conn, HOY.isoformat(),
                            _resumen_de_un_dia("820001", "820002", "04"))
    conn.close()
    sale = next(f for f in d["filas"] if f["estado"] == "SALE")
    c.igual(sale["horario"], "7:10 a.m.", "el horario es el del bote")
    c.cierto("RZ5759" in sale["notas"], "el numero del vuelo no se pierde: va en notas")
    # LA HORA DEL VUELO YA NO VA EN NOTAS. Lo pidio el lodge: «colocar el numero del
    # vuelo pero no la hora, ya que la hora fue designada en otra columna y no crear
    # confusion». Y era justo esa confusion: en HORARIO va la del BOTE (7:10) y al lado,
    # en notas, aparecia la del AVION (9:10). Dos horas distintas en el mismo renglon,
    # y la que hay que ejecutar es la de la columna.
    c.cierto("9:10" not in sale["notas"],
             "y la hora del avion NO, que la del bote ya esta en su columna")


def una_habitacion_que_cambia_de_huesped_no_mezcla_sus_horas(c):
    """EL FALLO QUE EL LODGE VIO: la habitacion 04 del 8 de noviembre salia con su vuelo
    de las 9:10 en las notas y las 11:30 del OTRO huesped en el horario.

    La hoja emparejaba cada movimiento de muelle con su fila por numero de HABITACION, y
    el numero de habitacion se reutiliza: el dia que un cuarto cambia de huesped, el que
    se va y el que llega tienen el mismo, y la fila del que se va era la ultima en
    quedarse con el cuarto. Se queda con los datos de los dos y el otro renglon, vacio.
    Ninguna de las dos mitades da error.
    """
    import hoja_dia
    conn = comun.base_limpia()
    d = hoja_dia.definicion(conn, HOY.isoformat(),
                            _resumen_de_un_dia("820010", "820011", "04"))
    conn.close()
    por_conf = {f["conf_no"]: f for f in d["filas"]}
    c.igual(len(d["filas"]), 2, "son DOS renglones, uno por reserva")

    sale = por_conf["820010"]
    entra = por_conf["820011"]
    c.igual(sale["horario"], "7:10 a.m.", "el que sale lleva su propia hora")
    c.igual(sale["drake"], 2, "y su propio muelle")
    c.igual(sale["sierpe"], "", "no el del otro")
    c.igual(entra["horario"], "11:30 a.m.", "el que entra lleva la suya")
    c.igual(entra["sierpe"], 2, "y su muelle")
    c.igual(entra["notas"], "", "sin el vuelo del que se va pegado")
    c.cierto("RZ5759" in sale["notas"], "el vuelo queda en el renglon de quien vuela")


def la_hoja_del_dia_deja_fuera_las_notas_de_plata(c):
    """«En la parte de notas solo colocar notas relevantes (no tarifas, no upgrades, no
    negociaciones)». La columna corta a 110 caracteres, asi que la factura por delante se
    come el renglon y tapa lo que habia que hacer."""
    import hoja_dia
    conn = comun.base_limpia()
    resumen = {
        "ingresos": [], "salidas": [
            {"conf_no": "810002", "room_no": "18", "nombre_principal": "Grimm/Ann",
             "adl": 2, "chl": 0,
             "nota_salida": ("se agrega adicional Sirena $772.92 facturar a la agencia "
                             "Para el vuelo de salida deben estar registrando a las "
                             "13:45 PM, favor indicar salida del Lodge.")}],
        "en_casa": [], "tours": [], "puntos": [],
        "total_ingresos": 0, "pax_ingresos": 0, "total_salidas": 1, "pax_salidas": 2,
        "total_en_casa": 0, "pax_en_casa": 0, "pax_desayunos": 2,
    }
    d = hoja_dia.definicion(conn, HOY.isoformat(), resumen)
    conn.close()

    notas = d["filas"][0]["notas"]
    c.cierto("772.92" not in notas and "facturar" not in notas, "la factura no sale")
    c.cierto("13:45" in notas,
             "pero la hora a la que tiene que registrarse para el vuelo SI")


def un_area_inventada_se_rechaza(c):
    conn = comun.base_limpia()
    try:
        areas.construir("no-existe", conn, HOY.isoformat(), HOY.isoformat())
        c.cierto(False, "un area desconocida tiene que rebotar")
    except ValueError:
        c.ok += 1
    conn.close()


PRUEBAS = [
    todas_las_areas_caben_en_una_hoja,
    todas_las_areas_caben_tambien_por_dia,
    un_periodo_sin_nada_no_revienta,
    el_formato_es_el_mismo_por_dia_y_por_mes,
    todas_las_areas_tienen_la_misma_estructura,
    el_pdf_y_el_excel_salen_de_la_misma_definicion,
    el_excel_guarda_numeros_no_texto,
    los_informes_salen_en_ingles,
    los_meses_y_los_estados_van_en_ingles,
    un_mes_se_compara_con_el_mes_anterior,
    la_tendencia_se_adapta_al_largo_del_periodo,
    ninguna_tendencia_sale_entera_en_cero,
    las_etiquetas_caben_en_su_casilla,
    las_cortesias_se_cuentan_no_se_valoran,
    la_ocupacion_usa_el_mismo_total_que_la_pantalla,
    el_spa_si_entra_en_el_informe,
    la_hoja_del_dia_cabe_en_el_ancho,
    la_hoja_del_dia_cabe_SIEMPRE_en_una_pagina,
    la_letra_de_la_hoja_se_adapta_al_dia,
    el_renglon_de_la_hoja_encoge_con_la_letra,
    la_hoja_no_parte_las_palabras_por_la_mitad,
    un_nombre_larguisimo_encoge_la_hoja_en_vez_de_partirlo,
    un_dia_imposible_alarga_el_papel_pero_no_lo_parte,
    la_hoja_del_dia_sale_en_pdf_y_en_excel,
    la_hoja_del_dia_enseña_los_DOS_tours_del_mismo_dia,
    el_horario_de_la_hoja_es_el_del_traslado_no_el_del_vuelo,
    una_habitacion_que_cambia_de_huesped_no_mezcla_sus_horas,
    la_hoja_del_dia_deja_fuera_las_notas_de_plata,
    un_area_inventada_se_rechaza,
]


if __name__ == "__main__":
    sys.exit(comun.correr("informes", PRUEBAS))
