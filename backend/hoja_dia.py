"""La hoja del día que se le manda al staff, con el formato que el lodge ya usa.

POR QUÉ EXISTE. El lodge arma a mano un Excel y manda un pantallazo al grupo con la
operación del día siguiente. Casi todo lo que lleva ese Excel ya está en el sistema, pero
repartido por pantallas, así que alguien lo copiaba. Esta hoja lo entrega hecho, en PDF
para el pantallazo y en Excel para quien quiera tocarlo, mientras se completa la
transición a la app.

UNA SOLA DEFINICIÓN para los dos formatos: `definicion()` arma los datos y `pdf()` y
`excel()` los dibujan. Es la misma regla que ya cumplen los demás informes del sistema —
si el PDF y el Excel se armaran por separado, acabarían diciendo cosas distintas y el
que circula por WhatsApp es justo el que nadie contrasta.

El formato imita el del lodge a propósito: la gente que lo recibe lleva meses leyéndolo
así, y cambiarles el dibujo el mismo día que cambia la herramienta es pedirles dos cosas
a la vez.
"""
import datetime
import io

import notas as _notas

# Los colores del Excel del lodge. Se copian tal cual: el staff ya asocia el verde con
# «se queda», el rojo con «se va» y el amarillo con «llega», y eso se lee antes que el
# texto de la fila.
VERDE_CAB = "2D5A27"
VERDE_SUB = "3D7A33"
FONDO = {"EN CASA": "DFF0D8", "SALE": "F8C9C9", "ENTRA": "FDF3A6"}
LINEA = "9B9B9B"
ROJO = "C0392B"

# Las columnas de la tabla ancha, en el orden del Excel del lodge.
# (clave, título, ancho en mm para el PDF)
#
# LOS ANCHOS TIENEN QUE CABER EN LA HOJA. A4 apaisado da 297 mm y los márgenes se comen
# 14, así que el total no puede pasar de 283. Con 308 la tabla se salía por los dos
# lados y la primera columna se leía «CASA» en vez de «EN CASA»: justo la que dice de un
# vistazo quién llega y quién se va.
COLUMNAS = [
    ("estado", "ESTADO", 15),
    ("hab", "HAB.", 11),
    ("huesped", "HUÉSPED", 54),
    ("pax", "PAX", 8),
    ("sierpe", "SIERPE", 12),
    ("drake", "DRAKE", 12),
    ("horario", "HORARIO", 17),
    ("guia_t", "GUÍA T", 19),
    ("bote_t", "BOTE / CAPITÁN", 25),
    ("notas", "NOTAS", 46),
    ("tour", "TOUR", 17),
    ("tour_guia", "GUÍA", 18),
    ("tour_bote", "BOTE", 18),
]
ANCHO_UTIL_MM = 283

# Los tres grupos de la cabecera superior, con cuántas columnas abarca cada uno.
GRUPOS = [("HUÉSPEDES", 4), ("INGRESOS Y SALIDAS", 6), ("ACTIVIDADES", 3)]


def _nombre_legible(acompanantes, principal):
    """«Johnson/Derek» -> «DEREK JOHNSON», y los acompañantes unidos por Y.

    Es como lo escribe el lodge en su hoja —«DEREK JOHNSON Y ANDREA OGG»— y no es un
    capricho: quien la lee busca por el nombre de pila con el que saluda al huésped, no
    por el apellido del sistema.
    """
    nombres = [n.strip() for n in (acompanantes or []) if n and n.strip()]
    if not nombres:
        if "/" in (principal or ""):
            apellido, nombre = principal.split("/", 1)
            nombres = [f"{nombre.strip()} {apellido.strip()}"]
        elif principal:
            nombres = [principal]
    return " Y ".join(n.upper() for n in nombres)


def _acompanantes(conn, conf_nos):
    """{conf_no: [nombres]} del rooming, para escribir la fila como la escribe el lodge."""
    salida = {}
    if not conf_nos:
        return salida
    lista = list(conf_nos)
    for i in range(0, len(lista), 400):
        lote = lista[i:i + 400]
        marcas = ",".join("?" * len(lote))
        for f in conn.execute(
                f"""SELECT conf_no, nombre_completo FROM huesped
                    WHERE conf_no IN ({marcas}) ORDER BY id""", lote):
            salida.setdefault(f["conf_no"], []).append(f["nombre_completo"])
    return salida


def definicion(conn, fecha, resumen):
    """Los datos de la hoja. `resumen` es lo que devuelve el módulo de Resumen.

    Se recibe ya calculado a propósito: así la hoja y la pantalla no pueden contar
    distinto. Lo único que se añade aquí es el rooming (para el nombre) y la tripulación
    de cada corrida, que la hoja de Excel del lodge no tenía.
    """
    import traslados as _tras

    # --- Una fila por habitación, igual que la hoja del lodge ---
    por_conf, por_hab = {}, {}

    def meter(r, estado):
        clave = r["conf_no"]
        # ENTRA y SALE mandan sobre EN CASA: el día que alguien llega o se va, eso es lo
        # que el staff necesita ver en su renglón.
        if clave in por_conf and por_conf[clave]["estado"] != "EN CASA":
            return
        fila = {
            "estado": estado,
            "hab": r.get("room_no") or "",
            "huesped": "",
            "conf_no": clave,
            "pax": (r.get("adl") or 0) + (r.get("chl") or 0),
            "sierpe": "", "drake": "", "horario": "", "guia_t": "", "bote_t": "",
            "notas": _notas.solo_lo_operativo(
                r.get("nota_salida") or r.get("nota_ingreso")),
            "tours": [],
            "tour": "", "tour_guia": "", "tour_bote": "",
        }
        por_conf[clave] = fila
        if fila["hab"]:
            por_hab[str(fila["hab"])] = fila

    for r in resumen.get("en_casa", []):
        meter(r, "EN CASA")
    for r in resumen.get("ingresos", []):
        meter(r, "ENTRA")
    for r in resumen.get("salidas", []):
        meter(r, "SALE")

    nombres = _acompanantes(conn, por_conf)
    for clave, fila in por_conf.items():
        origen = next((r for r in (resumen.get("en_casa", []) + resumen.get("ingresos", [])
                                   + resumen.get("salidas", []))
                       if r["conf_no"] == clave), {})
        fila["huesped"] = _nombre_legible(nombres.get(clave),
                                          origen.get("nombre_principal"))

    # --- El movimiento por muelle ---
    #
    # SE EMPAREJA POR RESERVA, NO POR HABITACIÓN. El número de habitación se reutiliza: el
    # día que un cuarto cambia de huésped, el que SE VA y el que LLEGA tienen el mismo, y
    # la fila del que se va era la última en quedarse con el cuarto. El 8 de noviembre la
    # habitación 13 salía con el vuelo del huésped que ENTRABA pegado en sus notas y con
    # la hora de otro en su horario, mientras el renglón del que entraba quedaba vacío.
    # Es la misma lección que ya está escrita aquí mismo para los tours.
    totales = {"Sierpe": {"ENTRA": 0, "SALE": 0}, "Drake": {"ENTRA": 0, "SALE": 0}}
    for punto in resumen.get("puntos", []):
        nombre_punto = punto["punto"]
        for det in punto.get("detalle", []):
            es_entrada = str(det.get("tipo") or "").lower().startswith("entrada")
            if nombre_punto in totales:
                totales[nombre_punto]["ENTRA" if es_entrada else "SALE"] += det.get("pax") or 0
            fila = por_conf.get(str(det.get("conf_no") or "")) \
                or por_hab.get(str(det.get("room_no")))
            if not fila:
                continue
            col = "sierpe" if nombre_punto.lower().startswith("sierpe") else "drake"
            fila[col] = det.get("pax") or ""
            # EL HORARIO ES EL DEL TRASLADO, NO EL DEL VUELO. Es la hora a la que el
            # huésped se mueve, que es lo único que el staff puede ejecutar: por Sierpe
            # el bote sale a su hora fija, y por Drake sale DOS HORAS ANTES del vuelo —la
            # regla que dio el lodge—. Poniendo la del vuelo, la hoja del 8 de noviembre
            # mandaba al muelle a las 9:25 a gente cuyo bote salía a las 7:25. El vuelo
            # no se pierde: va en la columna de notas, con su número.
            fila["horario"] = det.get("hora_traslado") or det.get("hora") or ""
            fila["guia_t"] = det.get("guia") or ""
            fila["bote_t"] = det.get("bote") or ""
            if det.get("vuelo"):
                vuelo = f"VUELO {det['vuelo']}"
                if det.get("hora"):
                    vuelo += f" · {det['hora']}"
                fila["notas"] = f"{fila['notas']} · {vuelo}".strip(" ·") if fila["notas"] else vuelo

    # --- La tripulación de cada corrida ---
    # Esto el Excel del lodge no lo tenía: el capitán y el ayudante se asignan ahora en
    # Transporte, y quien lee la hoja en el muelle necesita saber quién maneja el bote.
    corridas = _tras.corridas(conn, fecha, fecha)
    for c in corridas:
        for h in c.get("huespedes", []):
            fila = por_hab.get(str(h.get("room_no")))
            if not fila:
                continue
            if not fila["bote_t"]:
                fila["bote_t"] = " / ".join(
                    x for x in (c.get("bote_nombre"), c.get("capitan_nombre")) if x)
            if not fila["guia_t"]:
                fila["guia_t"] = c.get("guia_nombre") or ""

    # --- Los tours de cada habitación ---
    #
    # SE EMPAREJA POR RESERVA, NO POR HABITACIÓN. Es la misma lección que ya está escrita
    # en el resumen para las alergias: la habitación se reutiliza cada pocos días y el
    # número de reserva es lo único que identifica al huésped. Aquí el fallo tenía una
    # forma concreta: el día que una habitación cambia de huésped —55 veces en los
    # próximos cuatro meses— la fila de quien SE VA es la última que se queda con el
    # cuarto, así que el tour del que LLEGA se habría pintado en el renglón del que se
    # va. Y al revés: el que llega se quedaba sin su tour. Las dos mitades en silencio.
    # TODOS LOS DEL DÍA, NO EL PRIMERO. Lo pidió el lodge: «cuando un cliente tiene 2
    # tours el mismo día, ejemplo EBT y NW, solo se refleja un tour, hay que corregir el
    # resto porque perdemos información ahí». Pasa de verdad y es la combinación normal:
    # el pajareo de las 6 de la mañana y la caminata nocturna de las 17:45 son el mismo
    # día y los dos necesitan guía. Quedarse con el primero no daba error — daba una hoja
    # en la que el segundo guía no existía.
    #
    # Cada tour en su propio renglón DENTRO de la casilla, y el guía y el bote en el
    # suyo, para que las tres columnas se lean en paralelo: la primera línea de GUÍA es
    # la del primer tour. Con los tres pegados en una sola línea no habría forma de saber
    # cuál guía es de cuál salida.
    tours = resumen.get("tours", [])
    for t in tours:
        for conf in str(t.get("reservas") or "").split(","):
            fila = por_conf.get(conf.strip())
            if not fila or not t.get("tour_codigo"):
                continue
            fila["tours"].append({
                "codigo": t["tour_codigo"],
                "guia": t.get("guia_nombre") or "",
                "bote": t.get("bote_nombre") or "",
            })
    for fila in por_conf.values():
        # Ordenados como la jornada, que es como se lee la hoja.
        orden = {t.get("tour_codigo"): (t.get("horario_inicio") or "99:99") for t in tours}
        fila["tours"].sort(key=lambda x: orden.get(x["codigo"], "99:99"))
        fila["tour"] = "\n".join(x["codigo"] for x in fila["tours"])

        def columna(campo):
            """Un renglón por tour, alineado con el de la casilla TOUR.

            El guion solo aparece cuando hay algo con qué confundirlo: con dos tours y
            un solo guía asignado, sin el hueco marcado no se sabría de cuál de los dos
            es. Si no hay ninguno asignado la casilla va vacía, que es lo que ya decía
            antes y se lee mejor que una columna de guiones.
            """
            valores = [x[campo] for x in fila["tours"]]
            if not any(valores):
                return ""
            return "\n".join(v or "—" for v in valores)

        fila["tour_guia"] = columna("guia")
        fila["tour_bote"] = columna("bote")

    filas = sorted(por_conf.values(),
                   key=lambda x: int(x["hab"]) if str(x["hab"]).isdigit() else 999)

    sin_guia = sum(1 for t in tours if not t.get("guia_nombre"))
    sin_bote = sum(1 for t in tours if not t.get("bote_nombre"))
    return {
        "fecha": fecha,
        "filas": filas,
        "tours": tours,
        "totales_punto": totales,
        "movimientos": [
            ("ENTRA", resumen.get("total_ingresos", 0), resumen.get("pax_ingresos", 0)),
            ("SALE", resumen.get("total_salidas", 0), resumen.get("pax_salidas", 0)),
            ("EN CASA", resumen.get("total_en_casa", 0), resumen.get("pax_en_casa", 0)),
        ],
        "pax_desayunos": resumen.get("pax_desayunos", 0),
        "pax_en_casa": resumen.get("pax_en_casa", 0),
        "alertas": [
            ("Tours sin guía", sin_guia, "Agenda de tours"),
            ("Tours sin bote", sin_bote, "Transporte"),
            ("Habs. sin asignar", sum(1 for f in filas if not f["hab"]), "Reservas"),
            ("Corridas sin cubrir", sum(1 for c in corridas if c.get("falta")),
             "Transporte"),
            # Lo que se quitó de la hoja, dicho en la hoja. Si se escondiera sin contarlo,
            # nadie iría a arreglar la reserva y el tour seguiría mal puesto para siempre.
            ("Tours el día que se va", len(resumen.get("tours_fuera_por_salida") or []),
             "Agenda de tours"),
        ],
    }


def _dmy(iso):
    try:
        d = datetime.date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.day}/{d.month}/{d.year}"


# ---------------------------------------------------------------------------
# El PDF, apaisado y de una hoja: es lo que se fotografía y se manda al grupo
# ---------------------------------------------------------------------------

def pdf(d):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle)

    verde = colors.HexColor("#" + VERDE_CAB)
    verde2 = colors.HexColor("#" + VERDE_SUB)
    linea = colors.HexColor("#" + LINEA)
    rojo = colors.HexColor("#" + ROJO)

    chico = ParagraphStyle("c", fontName="Helvetica", fontSize=6.4, leading=7.6)
    chico_b = ParagraphStyle("cb", parent=chico, fontName="Helvetica-Bold")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        topMargin=8 * mm, bottomMargin=8 * mm,
        leftMargin=7 * mm, rightMargin=7 * mm,
        title=f"Operación {_dmy(d['fecha'])}")
    e = []

    def cabecera_verde(tabla, hasta_col=-1):
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (hasta_col, 0), verde),
            ("TEXTCOLOR", (0, 0), (hasta_col, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, linea),
            ("FONTSIZE", (0, 0), (-1, -1), 6.4),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ]))

    # ---- Las tres cajas de arriba ----
    t_tours = [["Tour", "Pax", "Guía", "Bote"]]
    for t in d["tours"]:
        grupo = "" if (t.get("grupo_operativo") or "A") == "A" else f" gr.{t['grupo_operativo']}"
        t_tours.append([f"{t.get('tour_codigo') or ''}{grupo}",
                        t.get("pax_total") or "",
                        t.get("guia_nombre") or "SIN ASIGNAR",
                        t.get("bote_nombre") or "—"])
    if len(t_tours) == 1:
        t_tours.append(["Sin tours este día", "", "", ""])
    tabla_tours = Table(t_tours, colWidths=[34 * mm, 12 * mm, 24 * mm, 24 * mm],
                        hAlign="LEFT")
    cabecera_verde(tabla_tours)
    for i, t in enumerate(d["tours"], start=1):
        if not t.get("guia_nombre"):
            tabla_tours.setStyle(TableStyle([("TEXTCOLOR", (2, i), (2, i), rojo)]))
        if not t.get("bote_nombre"):
            tabla_tours.setStyle(TableStyle([("TEXTCOLOR", (3, i), (3, i), rojo)]))

    t_mov = [["Estado", "Habs.", "Pax"]]
    for estado, habs, pax in d["movimientos"]:
        t_mov.append([estado, habs, pax])
    t_mov.append(["TOTAL + BKF", "", d["pax_desayunos"]])
    tabla_mov = Table(t_mov, colWidths=[26 * mm, 16 * mm, 14 * mm], hAlign="LEFT")
    cabecera_verde(tabla_mov)
    tabla_mov.setStyle(TableStyle([
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))

    t_al = [["Pendiente", "", ""]]
    for etiqueta, cuantos, donde in d["alertas"]:
        t_al.append([etiqueta, cuantos, donde])
    tabla_al = Table(t_al, colWidths=[32 * mm, 10 * mm, 28 * mm], hAlign="LEFT")
    cabecera_verde(tabla_al)
    tabla_al.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "CENTER")]))
    for i, (_, cuantos, _) in enumerate(d["alertas"], start=1):
        if cuantos:
            tabla_al.setStyle(TableStyle([
                ("TEXTCOLOR", (1, i), (1, i), rojo),
                ("FONTNAME", (1, i), (1, i), "Helvetica-Bold")]))

    titulos = Table(
        [[Paragraph("<b>Resumen de Tours</b>", chico_b),
          Paragraph("<b>Resumen de Movimientos</b>", chico_b),
          Paragraph("<b>Alertas / pendientes</b>", chico_b)]],
        colWidths=[98 * mm, 60 * mm, 74 * mm], hAlign="LEFT")
    titulos.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), verde),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    arriba = Table([[tabla_tours, tabla_mov, tabla_al]],
                   colWidths=[98 * mm, 60 * mm, 74 * mm], hAlign="LEFT")
    arriba.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    e += [titulos, arriba, Spacer(1, 5)]

    # ---- La franja de la fecha y los muelles ----
    s = d["totales_punto"]["Sierpe"]
    dr = d["totales_punto"]["Drake"]
    franja = Table(
        [["Fecha", _dmy(d["fecha"]), "IN HOUSE", d["pax_en_casa"], "",
          "SIERPE", "", "DRAKE", ""],
         ["", "", "", "", "", "entra", "sale", "entra", "sale"],
         ["", "", "", "", "", s["ENTRA"] or "", s["SALE"] or "",
          dr["ENTRA"] or "", dr["SALE"] or ""]],
        colWidths=[16 * mm, 24 * mm, 24 * mm, 14 * mm, 8 * mm,
                   16 * mm, 16 * mm, 16 * mm, 16 * mm], hAlign="LEFT")
    franja.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 6.4),
        ("GRID", (0, 0), (3, 0), 0.4, linea),
        ("GRID", (5, 0), (-1, -1), 0.4, linea),
        ("SPAN", (5, 0), (6, 0)), ("SPAN", (7, 0), (8, 0)),
        ("SPAN", (0, 0), (0, 2)), ("SPAN", (1, 0), (1, 2)),
        ("SPAN", (2, 0), (2, 2)), ("SPAN", (3, 0), (3, 2)),
        ("BACKGROUND", (2, 0), (2, 0), verde),
        ("TEXTCOLOR", (2, 0), (2, 0), colors.white),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#D9EAD3")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#D9EAD3")),
        ("BACKGROUND", (5, 0), (-1, 1), verde),
        ("TEXTCOLOR", (5, 0), (-1, 1), colors.white),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    e += [franja, Spacer(1, 5)]

    # ---- La tabla ancha ----
    anchos = [c[2] * mm for c in COLUMNAS]
    grupo_fila, i = [], 0
    for titulo, cuantas in GRUPOS:
        grupo_fila.append(titulo)
        grupo_fila += [""] * (cuantas - 1)
        i += cuantas
    datos = [grupo_fila, [c[1] for c in COLUMNAS]]
    def renglones(texto):
        """Un párrafo con un renglón por tour. Sin esto el segundo tour se saldría de la
        casilla: una celda de texto suelto no parte la línea, y el PDF se genera igual."""
        from xml.sax.saxutils import escape
        return Paragraph("<br/>".join(escape(x) for x in str(texto or "").split("\n")),
                         chico)

    for f in d["filas"]:
        datos.append([
            f["estado"], f["hab"],
            Paragraph(f["huesped"], chico),
            f["pax"], f["sierpe"], f["drake"], f["horario"],
            Paragraph(f["guia_t"], chico), Paragraph(f["bote_t"], chico),
            Paragraph((f["notas"] or "")[:110], chico),
            renglones(f["tour"]), renglones(f["tour_guia"]), renglones(f["tour_bote"]),
        ])
    if not d["filas"]:
        datos.append(["Sin movimiento este día"] + [""] * (len(COLUMNAS) - 1))

    tabla = Table(datos, colWidths=anchos, repeatRows=2, hAlign="LEFT")
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 1), verde),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), verde2),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.4),
        ("GRID", (0, 0), (-1, -1), 0.4, linea),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
        ("ALIGN", (1, 2), (1, -1), "CENTER"),
        ("ALIGN", (3, 2), (6, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("FONTNAME", (0, 2), (1, -1), "Helvetica-Bold"),
    ]
    col = 0
    for titulo, cuantas in GRUPOS:
        estilo.append(("SPAN", (col, 0), (col + cuantas - 1, 0)))
        col += cuantas
    for n, f in enumerate(d["filas"], start=2):
        fondo = FONDO.get(f["estado"])
        if fondo:
            estilo.append(("BACKGROUND", (0, n), (-1, n), colors.HexColor("#" + fondo)))
    tabla.setStyle(TableStyle(estilo))
    e.append(tabla)

    doc.build(e)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# El Excel, con las MISMAS columnas y los mismos colores
# ---------------------------------------------------------------------------

def excel(d):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Operación"
    borde = Border(*[Side(style="thin", color=LINEA)] * 4)
    blanco_negrita = Font(bold=True, color="FFFFFF")
    relleno_verde = PatternFill("solid", fgColor=VERDE_CAB)
    relleno_verde2 = PatternFill("solid", fgColor=VERDE_SUB)
    centrado = Alignment(horizontal="center", vertical="center")

    def poner(fila, col, valor, **kw):
        c = ws.cell(row=fila, column=col, value=valor)
        c.border = borde
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    # ---- Cajas de arriba ----
    poner(1, 1, "Resumen de Tours", font=blanco_negrita, fill=relleno_verde,
          alignment=centrado)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
    for i, titulo in enumerate(("Tour", "Pax", "Guía", "Bote"), start=1):
        poner(2, i, titulo, font=blanco_negrita, fill=relleno_verde2, alignment=centrado)
    fila = 2
    for t in d["tours"]:
        fila += 1
        grupo = "" if (t.get("grupo_operativo") or "A") == "A" else f" gr.{t['grupo_operativo']}"
        poner(fila, 1, f"{t.get('tour_codigo') or ''}{grupo}")
        poner(fila, 2, t.get("pax_total"), alignment=centrado)
        poner(fila, 3, t.get("guia_nombre") or "SIN ASIGNAR")
        poner(fila, 4, t.get("bote_nombre") or "—")
    if not d["tours"]:
        fila += 1
        poner(fila, 1, "Sin tours este día")

    poner(1, 6, "Resumen de Movimientos", font=blanco_negrita, fill=relleno_verde,
          alignment=centrado)
    ws.merge_cells(start_row=1, start_column=6, end_row=1, end_column=8)
    for i, titulo in enumerate(("Estado", "Habs.", "Pax"), start=6):
        poner(2, i, titulo, font=blanco_negrita, fill=relleno_verde2, alignment=centrado)
    for n, (estado, habs, pax) in enumerate(d["movimientos"], start=3):
        poner(n, 6, estado, font=Font(bold=True))
        poner(n, 7, habs, alignment=centrado)
        poner(n, 8, pax, alignment=centrado)
    poner(6, 6, "TOTAL + BKF", font=Font(bold=True))
    poner(6, 7, "")
    poner(6, 8, d["pax_desayunos"], alignment=centrado)

    poner(1, 10, "Alertas / pendientes", font=blanco_negrita, fill=relleno_verde,
          alignment=centrado)
    ws.merge_cells(start_row=1, start_column=10, end_row=1, end_column=12)
    for n, (etiqueta, cuantos, donde) in enumerate(d["alertas"], start=2):
        poner(n, 10, etiqueta)
        poner(n, 11, cuantos, alignment=centrado,
              font=Font(bold=True, color=ROJO) if cuantos else Font())
        poner(n, 12, donde)

    # ---- Franja de fecha y muelles ----
    s, dr = d["totales_punto"]["Sierpe"], d["totales_punto"]["Drake"]
    poner(8, 1, "Fecha", font=Font(bold=True))
    poner(8, 2, _dmy(d["fecha"]), alignment=centrado, font=Font(bold=True))
    poner(8, 3, "IN HOUSE", font=blanco_negrita, fill=relleno_verde)
    poner(8, 4, d["pax_en_casa"], alignment=centrado, font=Font(bold=True))
    for i, (titulo, valor) in enumerate(
            (("SIERPE entra", s["ENTRA"]), ("SIERPE sale", s["SALE"]),
             ("DRAKE entra", dr["ENTRA"]), ("DRAKE sale", dr["SALE"])), start=6):
        poner(8, i, titulo, font=blanco_negrita, fill=relleno_verde2, alignment=centrado)
        poner(9, i, valor, alignment=centrado)

    # ---- La tabla ancha ----
    inicio = 11
    col = 1
    for titulo, cuantas in GRUPOS:
        poner(inicio, col, titulo, font=blanco_negrita, fill=relleno_verde,
              alignment=centrado)
        if cuantas > 1:
            ws.merge_cells(start_row=inicio, start_column=col,
                           end_row=inicio, end_column=col + cuantas - 1)
            for x in range(col + 1, col + cuantas):
                ws.cell(row=inicio, column=x).border = borde
        col += cuantas
    for i, (_, titulo, _) in enumerate(COLUMNAS, start=1):
        poner(inicio + 1, i, titulo, font=blanco_negrita, fill=relleno_verde2,
              alignment=centrado)
    ws.freeze_panes = ws.cell(row=inicio + 2, column=1)

    for n, f in enumerate(d["filas"], start=inicio + 2):
        relleno = FONDO.get(f["estado"])
        for i, (clave, _, _) in enumerate(COLUMNAS, start=1):
            valor = f.get(clave)
            c = poner(n, i, valor if valor != "" else None)
            if relleno:
                c.fill = PatternFill("solid", fgColor=relleno)
            if clave in ("estado", "hab"):
                c.font = Font(bold=True)
            if clave in ("hab", "pax", "sierpe", "drake", "horario"):
                c.alignment = centrado
            # Las de actividades llevan un tour por renglón. Sin ajuste de texto Excel
            # enseña solo el primero y el resto se queda escondido dentro de la celda.
            if clave in ("tour", "tour_guia", "tour_bote", "huesped", "notas"):
                c.alignment = Alignment(vertical="top", wrap_text=True)

    for i, (_, titulo, ancho) in enumerate(COLUMNAS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(ancho * 0.52, len(titulo) + 2)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
