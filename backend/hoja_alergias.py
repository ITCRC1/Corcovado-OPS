"""La hoja de alergias y preferencias que cocina mira antes de servir.

POR QUÉ EXISTE. El lodge la arma a mano y la manda al grupo de cocina: una tarjeta con
las habitaciones del día, el pax de cada una y, al lado, una etiqueta de color con lo que
no se les puede servir. La pidió tal cual: «en el botón de alergia, un pequeño botón o
signo de descarga, donde las alergias se puedan ver en previsualización en el siguiente
formato». Así que se imita ese formato, no se inventa otro: quien la recibe lleva meses
leyéndola así.

SALEN TODAS LAS HABITACIONES QUE COMEN, no solo las que tienen algo. Es lo que hace que
la hoja sirva para servir: el salonero recorre la lista cuarto por cuarto y ve de un
vistazo cuáles llevan cuidado y cuáles no. Una lista con solo cuatro habitaciones no dice
nada sobre las otras veinte — ¿no tienen nada, o es que nadie lo anotó?

EL COLOR DICE DE QUÉ CLASE ES, y ante la duda es ROJO. Una preferencia servida como
alergia es una molestia; una alergia servida como preferencia es una ambulancia.
"""
import datetime
import io
import unicodedata

# Los colores de la tarjeta que el lodge ya usa.
AZUL_CABECERA = "16305A"
BARRA_GRUPO = "8CB4E8"
BARRA_OTRAS = "7FD1C1"
TEXTO = "1A1A1A"
LINEA = "D8D8D8"

COLOR_CLASE = {
    "alergia": "C0392B",      # rojo: no se le puede servir
    "dieta": "1E7E34",        # verde: vegano, vegetariano, pescetariano
    "preferencia": "C8921A",  # ámbar: lo que prefiere, no lo que le hace daño
    "casa": "8C8C8C",         # gris: los de casa
}

# Las tres dietas que el lodge nombró. Van sin tildes porque el texto se compara sin
# ellas: recepción escribe «vegetariano» y el PMS «Vegetarian», y las dos tienen que caer
# en el mismo sitio.
PALABRAS_DIETA = ("vegan", "vegetarian", "vegetarian", "pescatarian", "pescetarian",
                  "pesquetarian", "pescetarian", "vegetarianos", "vegana", "vegano")

# Lo que dice una PREFERENCIA y no un daño. La lista es corta a propósito: todo lo que no
# esté aquí ni sea dieta se pinta de rojo, que es el lado seguro.
PALABRAS_PREFERENCIA = ("prefier", "prefer", "no le gusta", "no les gusta", "dislike",
                        "solo come", "solo pollo", "no carne", "sin carne")

ETIQUETA_CASA = "(Los de casa)"


def _plano(texto):
    """Sin tildes y en minúsculas: «alérgico» y «alergico» son la misma palabra."""
    t = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def clase_de(texto):
    """Qué clase de cosa es, que es lo que decide el color.

    El orden importa: primero la dieta, porque «vegetariano, no come carne» lleva las
    palabras de las dos y lo que manda es que es vegetariano. Y lo que no cae en ninguna
    de las dos listas es ALERGIA, que es el lado seguro: pintar una preferencia de rojo
    hace que cocina pregunte; pintar una alergia de ámbar hace que no pregunte.
    """
    t = _plano(texto)
    if any(p in t for p in PALABRAS_DIETA):
        return "dieta"
    if any(p in t for p in PALABRAS_PREFERENCIA):
        return "preferencia"
    return "alergia"


def _texto_de(r):
    """Lo que se escribe en la etiqueta: el detalle, y si no hay, el nombre de la tarea.

    El detalle es lo que recepción escribió —«John: no shrimp, lobster»— y es lo único
    que cocina puede ejecutar. El nombre de la amenidad («Restricción alimentaria») no
    dice nada que sirva en la cocina, así que solo se usa cuando no hay detalle.
    """
    for campo in ("detalle", "tarea", "amenidad"):
        v = (r.get(campo) or "").strip()
        if v:
            return v
    return ""


def _dmy(iso):
    try:
        d = datetime.date.fromisoformat(str(iso))
    except ValueError:
        return str(iso)
    return f"{d.day:02d}-{d.month:02d}-{d.year}"


def definicion(conn, fecha):
    """Los datos de la hoja: las habitaciones que comen ese día, por grupo, con lo suyo.

    Se apoya en las MISMAS funciones que la pantalla de Restaurantes —quién come, qué
    restricciones tiene y qué habitaciones viajan juntas— para que el papel que llega a
    cocina no pueda decir algo distinto de lo que recepción ve en pantalla.
    """
    import grupos as _grupos
    import restaurantes as rest

    f = datetime.date.fromisoformat(fecha) if isinstance(fecha, str) else fecha
    cache = {}
    entradas, en_casa, _salen = rest._reservas_del_dia(conn, f, cache)
    comen = entradas + en_casa

    # Las restricciones salen de la misma función que alimenta la pestaña de Alergias, y
    # con la MISMA lista de quién come: si una decidiera distinto, una alergia podría
    # verse en pantalla y no en el papel.
    por_conf = {}
    for r in rest.restricciones_del_dia(conn, f, distribucion=comen, cache=cache):
        por_conf.setdefault(str(r["conf_no"]), []).append(r)

    etiquetas = {}
    for g in _grupos.resumen(conn).values():
        etiquetas[g["clave"]] = g["etiqueta"]

    # --- Se reparten en bloques: los que viajan juntos y el resto ---
    por_clave = {}
    for r in comen:
        por_clave.setdefault(r.get("clave_grupo"), []).append(r)

    def fila_de(r):
        suyas = por_conf.get(str(r["conf_no"]), [])
        texto = " · ".join(x for x in (_texto_de(s) for s in suyas) if x)
        if texto:
            return {"hab": r.get("room_no") or "—", "pax": r.get("pax") or 0,
                    "texto": texto, "clase": clase_de(texto)}
        # LOS DE CASA, en gris. Es la etiqueta que el lodge ya pone en su hoja, y no es
        # decoración: una habitación de cortesía sin nada anotado se lee igual que una de
        # huésped sin nada anotado, y no se atienden igual.
        if r.get("cortesia"):
            return {"hab": r.get("room_no") or "—", "pax": r.get("pax") or 0,
                    "texto": ETIQUETA_CASA, "clase": "casa"}
        return {"hab": r.get("room_no") or "—", "pax": r.get("pax") or 0,
                "texto": "", "clase": None}

    def por_numero(filas):
        return sorted(filas, key=lambda x: (int(x["hab"]) if str(x["hab"]).isdigit()
                                            else 999, str(x["hab"])))

    bloques, sueltas = [], []
    for clave, miembros in por_clave.items():
        if len(miembros) < 2:
            sueltas += miembros
            continue
        pax = sum(m.get("pax") or 0 for m in miembros)
        nombre = etiquetas.get(clave) or "Grupo"
        bloques.append({
            "titulo": f"{nombre} · {pax} pax",
            "color": BARRA_GRUPO,
            "filas": por_numero([fila_de(m) for m in miembros]),
            # Para ordenar: primero el grupo más grande, que es el que condiciona la noche.
            "_pax": pax,
        })
    bloques.sort(key=lambda b: -b["_pax"])
    if sueltas:
        bloques.append({
            "titulo": "Parejas / Otras habitaciones",
            "color": BARRA_OTRAS,
            "filas": por_numero([fila_de(m) for m in sueltas]),
            "_pax": sum(m.get("pax") or 0 for m in sueltas),
        })

    totales = rest.resumen_dia(conn, f)
    return {
        "fecha": f.isoformat(),
        "pax_almuerzo": (totales["almuerzo_tk"] or 0) + (totales["almuerzo_bosque"] or 0),
        "pax_cena": (totales["cena_tk"] or 0) + (totales["cena_bosque"] or 0),
        "bloques": bloques,
        "cuantas": sum(len(b["filas"]) for b in bloques),
        "con_restriccion": sum(1 for b in bloques for f_ in b["filas"]
                               if f_["texto"] and f_["clase"] != "casa"),
    }


# ---------------------------------------------------------------------------
# El PDF, vertical y angosto: se fotografía y se manda al grupo de cocina
# ---------------------------------------------------------------------------
#
# ANGOSTO A PROPÓSITO. Esto no se imprime para archivarlo: se mira en un teléfono y se
# reenvía por WhatsApp. Con el ancho de un folio, en la pantalla de un teléfono la letra
# queda del tamaño de un grano de arroz; con el ancho de una tarjeta se lee sin ampliar.
ANCHO_MM = 120
MARGEN_MM = 6


def pdf(d):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)
    from xml.sax.saxutils import escape

    ancho = ANCHO_MM * mm
    util = ancho - 2 * MARGEN_MM * mm

    tinta = colors.HexColor("#" + TEXTO)
    gris = colors.HexColor("#" + LINEA)
    titulo = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=13, leading=15.5,
                            textColor=tinta)
    cab = ParagraphStyle("c", fontName="Helvetica-Bold", fontSize=8.2, leading=10,
                         textColor=colors.white)
    barra = ParagraphStyle("b", fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                           textColor=colors.white)
    hab = ParagraphStyle("h", fontName="Helvetica", fontSize=9.5, leading=12,
                         textColor=tinta)
    pildora = ParagraphStyle("p", fontName="Helvetica-Bold", fontSize=7.8, leading=9.4,
                             textColor=colors.white)

    e = []

    # ---- La cabecera azul ----
    cabecera = Table(
        [[Paragraph(f"Día: {escape(_dmy(d['fecha']))}", cab),
          Paragraph(f"Total: {d['pax_almuerzo']} pax Lunch | {d['pax_cena']} pax Dinner",
                    cab)]],
        colWidths=[util * 0.36, util * 0.64])
    cabecera.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#" + AZUL_CABECERA)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    e += [cabecera, Spacer(1, 10),
          Paragraph("Alergias y Preferencias", titulo), Spacer(1, 6)]

    def etiqueta(texto, clase):
        """La píldora de color. Es una tabla de una casilla para poder pintarle el fondo.

        Con las esquinas redondeadas si la versión de ReportLab las sabe hacer, y
        cuadradas si no: lo que no puede pasar es que la hoja no salga por un adorno.
        """
        t = Table([[Paragraph(escape(texto), pildora)]])
        orden = [
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#" + COLOR_CLASE[clase])),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]
        try:
            t.setStyle(TableStyle(orden + [("ROUNDEDCORNERS", [7, 7, 7, 7])]))
        except Exception:
            t.setStyle(TableStyle(orden))
        return t

    for bloque in d["bloques"]:
        titulo_bloque = Table([[Paragraph(escape(bloque["titulo"]), barra)]],
                              colWidths=[util])
        titulo_bloque.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#" + bloque["color"])),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ]))
        filas = [[Paragraph(f"Hab. {escape(str(f['hab']))}"
                            f"<font color='#8A8A8A'>&nbsp;&nbsp;|&nbsp;&nbsp;</font>"
                            f"{f['pax']} pax", hab),
                  etiqueta(f["texto"], f["clase"]) if f["texto"] else ""]
                 for f in bloque["filas"]]
        tabla = Table(filas or [["", ""]], colWidths=[util * 0.36, util * 0.64])
        tabla.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, gris),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (0, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ]))
        # Sin KeepTogether: el papel crece hasta que cabe todo, así que no hay página
        # donde separarse. (Y además `wrap` de KeepTogether pide un lienzo que todavía no
        # existe cuando se mide, que es como se descubrió.)
        e += [titulo_bloque, tabla, Spacer(1, 9)]

    if not d["bloques"]:
        e.append(Paragraph("No hay nadie comiendo este día.", hab))
    elif isinstance(e[-1], Spacer):
        # El aire que separa un bloque del siguiente sobra después del último, y abajo de
        # una tarjeta que se mira en un teléfono un dedo de blanco se nota.
        e.pop()

    # El papel crece con el contenido en vez de partirse: esta hoja se mira de un tirón
    # en un teléfono, y pasar de página en una lista de habitaciones es perder el hilo.
    alto = _alto_necesario(e, util) + 2 * MARGEN_MM * mm
    buf = io.BytesIO()
    SimpleDocTemplate(
        buf, pagesize=(ancho, alto),
        topMargin=MARGEN_MM * mm, bottomMargin=MARGEN_MM * mm,
        leftMargin=MARGEN_MM * mm, rightMargin=MARGEN_MM * mm,
        title=f"Alergias y preferencias {_dmy(d['fecha'])}").build(e)
    buf.seek(0)
    return buf


def _alto_necesario(piezas, ancho):
    """Lo que mide la hoja armada, en puntos. El marco se queda 12 pt de relleno."""
    return sum(p.wrap(ancho, 0x7FFFFFFF)[1] for p in piezas) + 12


# Lo bastante nítida para leerla ampliada en un teléfono y lo bastante liviana para
# mandarla por WhatsApp: a 200 puntos por pulgada, la tarjeta de 120 mm sale de unos
# 945 px de ancho y pesa menos de 200 KB.
RESOLUCION = 200


def imagen(d, resolucion=RESOLUCION):
    """La MISMA tarjeta, en PNG.

    POR QUÉ HACE FALTA. Android no dibuja un PDF dentro de un marco: en vez de la tarjeta
    enseña un recuadro gris con el nombre del archivo y un botón «Abrir» —que además se
    lo pasa al gestor de descargas—. Una imagen la dibuja cualquier teléfono sin
    descargar nada. Y de paso es lo que se acaba reenviando al grupo de cocina: una foto
    se pega en WhatsApp, un PDF se adjunta.

    SE RASTERIZA EL PDF, no se vuelve a dibujar. Dibujar la tarjeta dos veces —una para
    el papel y otra para la pantalla— es garantizar que algún día digan cosas distintas,
    y aquí lo que diferiría serían alergias. La imagen ES el PDF, fotografiado.
    """
    import pdfplumber

    salida = io.BytesIO()
    with pdfplumber.open(pdf(d)) as doc:
        doc.pages[0].to_image(resolution=resolucion).original.save(salida, format="PNG")
    salida.seek(0)
    return salida
