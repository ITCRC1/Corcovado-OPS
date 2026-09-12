"""
El informe de operación: UNA hoja, para leer y para pasar a inversionistas.

QUÉ PROBLEMA RESUELVE
---------------------
Lo que se descargaba antes era una tabla plana de tres columnas —«Sección | Detalle |
Valor»— con el mismo molde para todas las pantallas. Se leía como una foto de la lista
que ya estaba en pantalla: sin totales, sin porcentajes, sin comparación, y con el spa
fuera, que la pantalla sí mostraba. Un número suelto —«EXTERNO 18»— no dice nada: ni de
cuántos, ni contra qué mes, ni si eso es mucho o poco para ese bote.

Este informe cabe en una hoja a propósito. La regla al armarlo: si algo no cabe, no es
que haya que encogerlo, es que no entra — entra lo que se mira para decidir, y el detalle
completo va en el libro de Excel del mismo periodo.

POR DÍA O POR MES, EL MISMO FORMATO
-----------------------------------
El informe recibe un rango cualquiera. Lo único que se adapta es el bloque de tendencia,
porque «pax por semana» no significa nada en un informe de un día:

  · hasta 21 días  -> una barra por DÍA. Si el rango es más corto que una semana, se
    extiende hacia atrás hasta completar siete barras, y las de antes del periodo van en
    tono claro: son contexto, no son el periodo.
  · más de 21 días -> una barra por SEMANA.

La comparación también se adapta: si el rango es un mes de calendario exacto se compara
con el mes anterior de calendario; si no, con la misma cantidad de días justo antes.

NADA DE DINERO
--------------
No lleva tarifas, precios ni montos, por decisión de operación. Las CORTESÍAS sí van,
pero como CUÁNTAS, que es el número que se quiere seguir.
"""
import calendar
import datetime
import io
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, Image, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

# ---------------------------------------------------------------------------
# Identidad. Los mismos colores de la pantalla.
# ---------------------------------------------------------------------------
BOSQUE = colors.HexColor("#2C4A3E")
VERDE_MEDIO = colors.HexColor("#5A7A6B")
VERDE_PALIDO = colors.HexColor("#B9C9BF")
ARENA = colors.HexColor("#F7F4EC")
LINEA = colors.HexColor("#DCD7C9")
TINTA = colors.HexColor("#23241F")
GRIS = colors.HexColor("#6E6A5C")
BAJA = colors.HexColor("#9C5B2E")
SUBE = colors.HexColor("#3F7A52")

MARGEN = 13 * mm
ANCHO = A4[0] - 2 * MARGEN
HUECO = 6 * mm
COL = (ANCHO - HUECO) / 2

T = ParagraphStyle("t", fontName="Helvetica", fontSize=7.8, leading=9.6, textColor=TINTA)
T_D = ParagraphStyle("td", parent=T, alignment=TA_RIGHT)
T_B = ParagraphStyle("tb", parent=T, fontName="Helvetica-Bold")
T_BD = ParagraphStyle("tbd", parent=T_B, alignment=TA_RIGHT)
MUTE = ParagraphStyle("m", parent=T, fontSize=6.8, leading=8.2, textColor=GRIS)
H_SEC = ParagraphStyle("hs", fontName="Helvetica-Bold", fontSize=9, leading=10.5,
                       textColor=BOSQUE)

MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# Hasta aquí se grafica por día; de aquí en adelante, por semana.
TOPE_DIARIO = 21
MINIMO_BARRAS = 7


def _logo():
    ruta = os.path.join(os.path.dirname(__file__), "..", "frontend", "assets", "logo.jpg")
    return ruta if os.path.exists(ruta) else None


def sql_fecha(col):
    """La MISMA expresión que main.sql_fecha: reordena 'DD-MM-YY' a 'YY-MM-DD'."""
    return f"(substr({col},7,2)||'-'||substr({col},4,2)||'-'||substr({col},1,2))"


def yymmdd(iso):
    y, m, d = iso.split("-")
    return f"{y[2:]}-{m}-{d}"


def fecha_larga(iso, con_ano=True):
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {MESES[d.month - 1]}" + (f" {d.year}" if con_ano else "")


def titulo_del_periodo(desde, hasta):
    """Cómo se llama este periodo en la cabecera. Un mes entero se dice por su nombre."""
    d0, d1 = datetime.date.fromisoformat(desde), datetime.date.fromisoformat(hasta)
    if d0 == d1:
        return f"{d0.day} de {MESES_LARGOS[d0.month - 1]} de {d0.year}"
    if es_mes_completo(desde, hasta):
        return f"{MESES_LARGOS[d0.month - 1].capitalize()} {d0.year}"
    return f"{fecha_larga(desde, False)} — {fecha_larga(hasta)}"


def es_mes_completo(desde, hasta):
    d0, d1 = datetime.date.fromisoformat(desde), datetime.date.fromisoformat(hasta)
    return (d0.day == 1 and d0.year == d1.year and d0.month == d1.month
            and d1.day == calendar.monthrange(d1.year, d1.month)[1])


def periodo_anterior(desde, hasta):
    """Contra qué se compara. Un mes se compara con el mes anterior, no con 30 días."""
    d0, d1 = datetime.date.fromisoformat(desde), datetime.date.fromisoformat(hasta)
    if es_mes_completo(desde, hasta):
        fin = d0 - datetime.timedelta(days=1)
        ini = fin.replace(day=1)
        return ini.isoformat(), fin.isoformat()
    dias = (d1 - d0).days + 1
    return ((d0 - datetime.timedelta(days=dias)).isoformat(),
            (d0 - datetime.timedelta(days=1)).isoformat())


# ---------------------------------------------------------------------------
# Los datos
# ---------------------------------------------------------------------------

def _a_fecha(valor):
    try:
        d, m, y = (valor or "").split("-")
        return datetime.date(2000 + int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def total_habitaciones():
    """El mismo total que usa la pantalla de ocupación, para que no se contradigan."""
    try:
        import publicador as _pub
        return len(_pub.cargar_config().get("habitaciones") or []) or 30
    except Exception:
        return 30


def metricas(conn, desde, hasta, habitaciones=None):
    """Todo lo que el informe necesita de un periodo. Solo lee."""
    habitaciones = habitaciones or total_habitaciones()
    d0 = datetime.date.fromisoformat(desde)
    d1 = datetime.date.fromisoformat(hasta)
    noches = (d1 - d0).days + 1

    reservas = [dict(r) for r in conn.execute(
        """SELECT conf_no, room_no, arr_date, dep_date, adl, chl, punto_entrada,
                  punto_salida, cortesia
           FROM reserva WHERE res_status != 'CANCELADA'""")]

    pax_noche, hab_noche = 0, 0
    for i in range(noches):
        dia = d0 + datetime.timedelta(days=i)
        habs = set()
        for r in reservas:
            llega, sale = _a_fecha(r["arr_date"]), _a_fecha(r["dep_date"])
            # Se cuenta ocupada la noche que el huésped duerme ahí: desde su llegada
            # hasta el día antes de su salida. Igual que la pantalla de ocupación.
            if llega and llega <= dia and (sale is None or dia < sale):
                habs.add(r["room_no"])
                pax_noche += (r["adl"] or 0) + (r["chl"] or 0)
        hab_noche += len(habs)
    ocupacion = round(100 * hab_noche / (habitaciones * noches)) if noches else 0

    tours = [dict(r) for r in conn.execute(
        """SELECT ta.fecha, ta.tour_codigo, ta.pax, ta.guia_nombre, ta.bote_nombre
           FROM tour_asignado ta
           JOIN reserva r ON r.conf_no = ta.conf_no
           WHERE ta.fecha BETWEEN ? AND ? AND r.res_status != 'CANCELADA'""",
        (desde, hasta))]

    con_tour = {r["conf_no"] for r in conn.execute(
        "SELECT DISTINCT conf_no FROM tour_asignado WHERE fecha BETWEEN ? AND ?",
        (desde, hasta))}
    entraron = [r for r in reservas
                if _a_fecha(r["arr_date"]) and d0 <= _a_fecha(r["arr_date"]) <= d1]
    ids_entraron = {r["conf_no"] for r in entraron}

    # Cuántas cortesías, no cuánto valen. Sale de la columna que se llena leyendo la
    # nota de la reserva, así que cuenta lo que Reservaciones escribió.
    cortesias = [r for r in entraron if r.get("cortesia")]

    spa = [dict(r) for r in conn.execute(
        """SELECT c.estado, c.origen, c.minutos,
                  COALESCE(s.nombre, c.servicio_codigo) AS tratamiento
           FROM spa_cita c LEFT JOIN spa_servicio s ON s.codigo = c.servicio_codigo
           WHERE c.fecha BETWEEN ? AND ?""", (desde, hasta))]

    return {
        "desde": desde, "hasta": hasta, "noches": noches,
        "pax_noche": pax_noche, "ocupacion": ocupacion,
        "salidas": len(tours), "pax_tours": sum(t["pax"] or 0 for t in tours),
        "reservas_periodo": len(ids_entraron),
        "reservas_con_tour": len(ids_entraron & con_tour),
        "cortesias": len(cortesias),
        "cortesias_pax": sum((r["adl"] or 0) + (r["chl"] or 0) for r in cortesias),
        "tours": tours, "spa": spa,
        "spa_activas": len([c for c in spa if c["estado"] in ("HECHA", "CONFIRMADA")]),
    }


def agrupar(filas, clave):
    salida = {}
    for f in filas:
        k = f.get(clave) or "(sin asignar)"
        d = salida.setdefault(k, {"n": 0, "pax": 0})
        d["n"] += 1
        d["pax"] += f.get("pax") or 0
    return salida


def top_y_otros(pares, n, nombre="nombre"):
    """Los n primeros y el resto agrupado.

    Agrupar UNO solo en «Otros (1)» no resume nada y esconde un nombre: si sobra uno
    nada más, entra con el suyo.
    """
    ordenados = sorted(pares.items(), key=lambda x: -x[1]["pax"])
    if len(ordenados) == n + 1:
        n += 1
    primeros, resto = ordenados[:n], ordenados[n:]
    filas = [{nombre: k, "n": v["n"], "pax": v["pax"]} for k, v in primeros]
    if resto:
        filas.append({nombre: f"Otros ({len(resto)})",
                      "n": sum(v["n"] for _, v in resto),
                      "pax": sum(v["pax"] for _, v in resto)})
    return filas


def serie_de_tendencia(conn, desde, hasta):
    """(valores, etiquetas, dentro, titulo). 'dentro' dice qué barras son del periodo.

    Ver el encabezado del módulo: el cubo se adapta al largo del rango para que el mismo
    bloque sirva en un informe de un día y en uno de un mes.
    """
    d0 = datetime.date.fromisoformat(desde)
    d1 = datetime.date.fromisoformat(hasta)
    dias = (d1 - d0).days + 1

    if dias > TOPE_DIARIO:
        ini_serie, paso, titulo = d0, 7, "Pax en tours por semana"
        cubos = []
        cursor = ini_serie
        while cursor <= d1:
            fin = min(cursor + datetime.timedelta(days=6), d1)
            cubos.append((cursor, fin, f"sem. {cursor.strftime('%d/%m')}", True))
            cursor = fin + datetime.timedelta(days=1)
    else:
        # Rango corto: se completa hacia atrás para que la barra tenga con qué compararse.
        faltan = max(0, MINIMO_BARRAS - dias)
        ini_serie = d0 - datetime.timedelta(days=faltan)
        cubos = []
        cursor = ini_serie
        while cursor <= d1:
            cubos.append((cursor, cursor, cursor.strftime("%d/%m"), cursor >= d0))
            cursor += datetime.timedelta(days=1)
        titulo = ("Pax en tours por día" if dias > 1
                  else f"Pax en tours · últimos {len(cubos)} días")

    filas = conn.execute(
        """SELECT ta.fecha f, SUM(ta.pax) pax FROM tour_asignado ta
           JOIN reserva r ON r.conf_no = ta.conf_no
           WHERE ta.fecha BETWEEN ? AND ? AND r.res_status != 'CANCELADA'
           GROUP BY ta.fecha""",
        (ini_serie.isoformat(), hasta)).fetchall()
    por_dia = {r["f"]: r["pax"] or 0 for r in filas}

    valores, etiquetas, dentro = [], [], []
    for ini, fin, etiqueta, es_del_periodo in cubos:
        total = 0
        cur = ini
        while cur <= fin:
            total += por_dia.get(cur.isoformat(), 0)
            cur += datetime.timedelta(days=1)
        valores.append(total)
        etiquetas.append(etiqueta)
        dentro.append(es_del_periodo)
    return valores, etiquetas, dentro, titulo


# ---------------------------------------------------------------------------
# Piezas del dibujo
# ---------------------------------------------------------------------------

def _p(txt, estilo=T):
    return Paragraph(txt, estilo)


def _delta(actual, previo):
    if previo in (None, 0):
        return ("—", GRIS) if not actual else ("nuevo", GRIS)
    cambio = (actual - previo) / previo * 100
    if abs(cambio) < 0.5:
        return "igual", GRIS
    return (f"{'▲' if cambio > 0 else '▼'} {abs(cambio):.0f}%",
            SUBE if cambio > 0 else BAJA)


def seccion(titulo, aclaracion=None, ancho=None):
    t = Table([[_p(titulo.upper(), H_SEC)]], colWidths=[ancho or COL])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, BOSQUE),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    piezas = [t]
    if aclaracion:
        piezas += [Spacer(1, 1.5), _p(aclaracion, MUTE)]
    piezas.append(Spacer(1, 2.5))
    return piezas


def barra(valor, maximo, ancho_mm, color=VERDE_MEDIO):
    llena = 0 if not maximo else max(0.5, ancho_mm * valor / maximo)
    t = Table([["", ""]], colWidths=[llena * mm, max(0.1, ancho_mm - llena) * mm],
              rowHeights=[3.6 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), color),
        ("BACKGROUND", (1, 0), (1, 0), ARENA),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8),
    ]))
    return t


def tablita(columnas, filas, anchos, total=None, barra_en=None, tope=None):
    cab = [_p(f'<font color="white"><b>{et}</b></font>', T_D if ali == "d" else T)
           for _, et, ali in columnas]
    datos = [cab]
    for f in filas:
        fila = []
        for clave, _, ali in columnas:
            if barra_en and clave == barra_en:
                fila.append(barra(f.get(clave) or 0, tope, anchos[len(fila)] / mm - 1))
                continue
            v = f.get(clave)
            fila.append(_p("—" if v in (None, "") else str(v),
                           T_D if ali == "d" else T))
        datos.append(fila)
    if total:
        datos.append([_p(f'<b>{total.get(c[0], "")}</b>',
                         T_BD if c[2] == "d" else T_B) for c in columnas])

    t = Table(datos, colWidths=anchos, hAlign="LEFT")
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), BOSQUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2 if total else -1), [colors.white, ARENA]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3.5), ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
    ]
    if total:
        estilo += [("LINEABOVE", (0, -1), (-1, -1), 0.7, BOSQUE),
                   ("BACKGROUND", (0, -1), (-1, -1), colors.white)]
    t.setStyle(TableStyle(estilo))
    return t


def banda_kpi(kpis, neutrales=()):
    """kpis: (etiqueta, valor, previo, sufijo, pie).

    'neutrales' son las cifras donde subir no es bueno ni malo. Las cortesías son el
    caso: pintar de rojo que bajaron da a entender que pasó algo malo, y bajar cortesías
    normalmente es lo contrario. Se muestra el cambio sin opinar.
    """
    p_val = ParagraphStyle("kv", parent=T, fontSize=17, leading=19)
    p_et = ParagraphStyle("ke", parent=T, fontSize=6.2, leading=7.4, textColor=GRIS)
    p_dl = ParagraphStyle("kd", parent=T, fontSize=6.6, leading=8)
    ets, vals, dels = [], [], []
    for etiqueta, valor, previo, sufijo, pie in kpis:
        ets.append(_p(etiqueta.upper(), p_et))
        vals.append(_p(f'<font color="#2C4A3E"><b>{valor}</b></font>'
                       f'<font size="7.5" color="#6E6A5C"> {sufijo}</font>', p_val))
        texto, color = _delta(valor if isinstance(valor, (int, float)) else 0, previo)
        if etiqueta in neutrales:
            color = GRIS
        cola = pie or (f"antes {previo}" if previo not in (None, 0) else "")
        dels.append(_p(f'<font color="#{color.hexval()[2:]}"><b>{texto}</b></font>'
                       + (f'<font color="#6E6A5C"> · {cola}</font>' if cola else ""), p_dl))
    t = Table([ets, vals, dels], colWidths=[ANCHO / len(kpis)] * len(kpis),
              rowHeights=[8, 20, 10])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def franja(valores, etiquetas, dentro, ancho_total, alto_mm=22):
    """Las barras de tendencia. Las de fuera del periodo van en tono claro: son
    contexto y no deben leerse como parte de lo que se informa."""
    maximo = max(valores) or 1
    ancho_col = ancho_total / max(len(valores), 1)
    centro = ParagraphStyle("c", parent=T, fontSize=6.6, leading=7.8, alignment=TA_CENTER)
    centro_m = ParagraphStyle("cm", parent=MUTE, alignment=TA_CENTER)
    cimas, barras, pies = [], [], []
    for v, et, es_del_periodo in zip(valores, etiquetas, dentro):
        alto = max(0.5, alto_mm * v / maximo)
        b = Table([[""]], colWidths=[ancho_col * 0.55], rowHeights=[alto * mm])
        b.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), VERDE_MEDIO if es_del_periodo else VERDE_PALIDO),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        caja = Table([[b]], colWidths=[ancho_col], rowHeights=[(alto_mm + 0.5) * mm])
        caja.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        color = "#23241F" if es_del_periodo else "#9A968A"
        cimas.append(_p(f'<font color="{color}"><b>{v}</b></font>', centro))
        barras.append(caja)
        pies.append(_p(et, centro_m))
    t = Table([cimas, barras, pies], colWidths=[ancho_col] * len(valores))
    t.setStyle(TableStyle([
        ("VALIGN", (0, 1), (-1, 1), "BOTTOM"),
        ("LINEBELOW", (0, 1), (-1, 1), 0.5, LINEA),
        ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    t.hAlign = "LEFT"
    return t


def lectura(m, ant, pct, mejor_tour, ocupacion_flota):
    """El párrafo de arriba. Se redacta con los MISMOS datos de las tablas, no a mano:
    escrito aparte, tarde o temprano diría algo que las tablas desmienten."""
    var_pax = _delta(m["pax_noche"], ant["pax_noche"])[0]

    def plural(n, uno, varios):
        return f"{n} {uno if n == 1 else varios}"

    # Con cero reservas entrando, «0% hicieron una actividad» es cierto y se lee mal:
    # parece un mal resultado cuando no hubo a quién ofrecerle nada.
    if m["reservas_periodo"]:
        entrada = (f"<b>{pct}%</b> de las reservas que ingresaron hicieron al menos una "
                   f"actividad")
    else:
        entrada = "No ingresaron reservas nuevas"

    frases = [
        f"El lodge alojó <b>{plural(m['pax_noche'], 'pax-noche', 'pax-noche')}</b> con "
        f"una ocupación media del <b>{m['ocupacion']}%</b> "
        f"({var_pax} contra el periodo anterior).",
        f"{entrada}; se realizaron "
        f"<b>{plural(m['salidas'], 'salida', 'salidas')}</b> que "
        f"{'movió' if m['salidas'] == 1 else 'movieron'} <b>{m['pax_tours']} pax</b>."
        + (f" La actividad de mayor demanda fue <b>{mejor_tour}</b>." if mejor_tour else ""),
    ]
    if ocupacion_flota:
        frases.append(
            f"La flota propia operó a un <b>{ocupacion_flota}%</b> de su capacidad "
            f"promedio por viaje.")
    if m["cortesias"] or ant["cortesias"]:
        frases.append(
            f"Se {'registró' if m['cortesias'] == 1 else 'registraron'} "
            f"<b>{plural(m['cortesias'], 'reserva de cortesía', 'reservas de cortesía')}</b> "
            f"({m['cortesias_pax']} pax), frente a {ant['cortesias']} del periodo anterior.")
    return " ".join(frases)


# ---------------------------------------------------------------------------
# El documento
# ---------------------------------------------------------------------------

def una_pagina(conn, desde, hasta):
    """El informe completo. Devuelve un BytesIO listo para descargar."""
    m = metricas(conn, desde, hasta)
    p_desde, p_hasta = periodo_anterior(desde, hasta)
    ant = metricas(conn, p_desde, p_hasta)
    dias = (datetime.date.fromisoformat(hasta) - datetime.date.fromisoformat(desde)).days + 1

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, topMargin=11 * mm, bottomMargin=11 * mm,
                          leftMargin=MARGEN, rightMargin=MARGEN,
                          title=f"Informe de operación · {titulo_del_periodo(desde, hasta)}")
    marco = Frame(MARGEN, 11 * mm, ANCHO, A4[1] - 22 * mm, id="c",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def pie(canvas, d):
        canvas.saveState()
        canvas.setStrokeColor(LINEA)
        canvas.setLineWidth(0.5)
        canvas.line(MARGEN, 8.5 * mm, A4[0] - MARGEN, 8.5 * mm)
        canvas.setFont("Helvetica", 6.2)
        canvas.setFillColor(GRIS)
        canvas.drawString(MARGEN, 5.5 * mm,
                          "Corcovado Wilderness Lodge · el detalle completo va en el "
                          "libro de Excel de este mismo periodo")
        canvas.drawRightString(A4[0] - MARGEN, 5.5 * mm,
                               f"Generado {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="u", frames=[marco], onPage=pie)])
    e = []

    # ---- Cabecera ----
    izq = []
    logo = _logo()
    if logo:
        img = Image(logo, width=30 * mm, height=9.5 * mm)
        img.hAlign = "LEFT"
        izq.append(img)
    izq += [Spacer(1, 2),
            _p('<font size="13" color="#2C4A3E"><b>Informe de operación</b></font>',
               ParagraphStyle("h", parent=T, fontSize=13, leading=15)),
            _p("Reporte a inversionistas", MUTE)]
    der = [_p(f'<b>{titulo_del_periodo(desde, hasta)}</b>'
              + (f' · {dias} días' if dias > 1 else ""),
              ParagraphStyle("d1", parent=T, fontSize=8.5, leading=11, alignment=TA_RIGHT)),
           _p(f'comparado con {fecha_larga(p_desde, False)} — {fecha_larga(p_hasta)}',
              ParagraphStyle("d2", parent=MUTE, alignment=TA_RIGHT))]
    cab = Table([[izq, der]], colWidths=[COL, COL + HUECO])
    cab.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, 0), "TOP"), ("VALIGN", (1, 0), (1, 0), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, BOSQUE),
    ]))
    e += [cab, Spacer(1, 5)]

    # ---- Cifras ----
    pct = round(100 * m["reservas_con_tour"] / m["reservas_periodo"]) if m["reservas_periodo"] else 0
    pct_ant = round(100 * ant["reservas_con_tour"] / ant["reservas_periodo"]) if ant["reservas_periodo"] else 0
    e.append(banda_kpi([
        ("Pax-noche", m["pax_noche"], ant["pax_noche"], "", None),
        ("Ocupación", m["ocupacion"], ant["ocupacion"], "%", None),
        ("Salidas de tour", m["salidas"], ant["salidas"], "", None),
        ("Pax en tours", m["pax_tours"], ant["pax_tours"], "", None),
        ("Hacen tour", pct, pct_ant, "%",
         f"{m['reservas_con_tour']} de {m['reservas_periodo']}"),
        ("Citas de spa", m["spa_activas"], ant["spa_activas"], "", None),
        ("Cortesías", m["cortesias"], ant["cortesias"], "", f"{m['cortesias_pax']} pax"),
    ], neutrales=("Cortesías",)))
    linea = Table([[""]], colWidths=[ANCHO], rowHeights=[0.5])
    linea.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LINEA)]))
    e += [Spacer(1, 1), linea, Spacer(1, 6)]

    # ---- Columna izquierda: tours y guías ----
    izq = []
    por_tour = agrupar(m["tours"], "tour_codigo")
    filas_t = top_y_otros(por_tour, 7, "tour")
    izq += seccion("Tours por tipo",
                   "Una salida = una reserva en un tour una fecha. El pax es el del tour.")
    izq.append(tablita(
        [("tour", "Tour", "i"), ("n", "Sal.", "d"), ("pax", "Pax", "d"), ("bar", "", "i")],
        [dict(f, bar=f["pax"]) for f in filas_t],
        [26 * mm, 12 * mm, 13 * mm, 38 * mm],
        total={"tour": "TOTAL", "n": sum(f["n"] for f in filas_t),
               "pax": sum(f["pax"] for f in filas_t)},
        barra_en="bar",
        tope=max((v["pax"] for v in por_tour.values()), default=1)))
    izq.append(Spacer(1, 6))

    por_guia = agrupar(m["tours"], "guia_nombre")
    filas_g = top_y_otros(por_guia, 6, "guia")
    izq += seccion("Guías", "Salidas atendidas y pasajeros por guía.")
    izq.append(tablita(
        [("guia", "Guía", "i"), ("n", "Sal.", "d"), ("pax", "Pax", "d"), ("bar", "", "i")],
        [dict(f, bar=f["pax"]) for f in filas_g],
        [26 * mm, 12 * mm, 13 * mm, 38 * mm],
        total={"guia": "TOTAL", "n": sum(f["n"] for f in filas_g),
               "pax": sum(f["pax"] for f in filas_g)},
        barra_en="bar",
        tope=max((v["pax"] for v in por_guia.values()), default=1)))

    # ---- Columna derecha: botes, puntos y spa ----
    der = []
    caps = {r["nombre"]: r["capacidad_max"]
            for r in conn.execute("SELECT nombre, capacidad_max FROM bote")}
    por_bote = agrupar(m["tours"], "bote_nombre")
    filas_b, ocupaciones = [], []
    for k, v in sorted(por_bote.items(), key=lambda x: -x[1]["pax"])[:6]:
        cap = caps.get(k)
        prom = v["pax"] / v["n"] if v["n"] else 0
        if cap:
            ocupaciones.append(100 * prom / cap)
        filas_b.append({"bote": k, "n": v["n"], "prom": f"{prom:.1f}",
                        "ocup": f"{100 * prom / cap:.0f}%" if cap else "s/tope",
                        "bar": round(100 * prom / cap) if cap else 0})
    der += seccion("Botes · ocupación",
                   "Pax promedio por viaje sobre la capacidad. Dice si sobra o falta flota.")
    der.append(tablita(
        [("bote", "Bote", "i"), ("n", "Viajes", "d"), ("prom", "Pax/viaje", "d"),
         ("ocup", "Ocup.", "d"), ("bar", "", "i")],
        filas_b, [23 * mm, 13 * mm, 18 * mm, 13 * mm, 22 * mm],
        barra_en="bar", tope=100))
    der.append(Spacer(1, 6))

    d0i, d1i = yymmdd(desde), yymmdd(hasta)
    puntos = {}
    for col, lado, fecha in (("punto_entrada", "e", "arr_date"),
                             ("punto_salida", "s", "dep_date")):
        for r in conn.execute(
                f"""SELECT {col} p, SUM(adl+chl) pax FROM reserva
                    WHERE {col} IS NOT NULL AND res_status != 'CANCELADA'
                      AND {sql_fecha(fecha)} BETWEEN ? AND ?
                    GROUP BY {col}""", (d0i, d1i)):
            puntos.setdefault(r["p"], {"e": 0, "s": 0})[lado] = r["pax"] or 0
    filas_p = [{"punto": k, "e": v["e"], "s": v["s"]} for k, v in sorted(puntos.items())]
    der += seccion("Puntos de embarque", "Pax que entra y sale por cada punto.")
    der.append(tablita(
        [("punto", "Punto", "i"), ("e", "Pax entra", "d"), ("s", "Pax sale", "d")],
        filas_p, [37 * mm, 26 * mm, 26 * mm],
        total={"punto": "TOTAL", "e": sum(f["e"] for f in filas_p),
               "s": sum(f["s"] for f in filas_p)}))
    der.append(Spacer(1, 6))

    trat = {}
    for c in m["spa"]:
        if c["estado"] not in ("HECHA", "CONFIRMADA"):
            continue
        d = trat.setdefault(c["tratamiento"] or "(sin código)", {"n": 0, "pax": 0})
        d["n"] += 1
        d["pax"] += c["minutos"] or 0
    filas_s = top_y_otros(trat, 5, "trat")
    estados = {}
    for c in m["spa"]:
        estados[c["estado"]] = estados.get(c["estado"], 0) + 1
    der += seccion("Spa", "Citas realizadas y confirmadas en el periodo.")
    der.append(tablita(
        [("trat", "Tratamiento", "i"), ("n", "Citas", "d"), ("horas", "Horas", "d")],
        [dict(f, horas=f"{f['pax'] / 60:.1f}") for f in filas_s],
        [45 * mm, 20 * mm, 24 * mm],
        total={"trat": "TOTAL", "n": sum(f["n"] for f in filas_s),
               "horas": f"{sum(f['pax'] for f in filas_s) / 60:.1f}"}))
    if m["spa"]:
        der += [Spacer(1, 1.5),
                _p(f"De las {len(m['spa'])} citas del periodo: "
                   + " · ".join(f"{k.lower()} {v}" for k, v in sorted(estados.items())),
                   MUTE)]

    cuerpo = Table([[izq, der]], colWidths=[COL, COL], hAlign="LEFT")
    cuerpo.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), HUECO),
        ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    e += [cuerpo, Spacer(1, 7)]

    # ---- Tendencia ----
    valores, etiquetas, dentro, titulo = serie_de_tendencia(conn, desde, hasta)
    aclaracion = (None if all(dentro)
                  else "En tono claro, los días anteriores al periodo: van como contexto.")
    e += seccion(titulo, aclaracion, ancho=ANCHO)
    e.append(franja(valores, etiquetas, dentro, ANCHO))
    e.append(Spacer(1, 7))

    # ---- Lectura ----
    mejor = max(por_tour.items(), key=lambda x: x[1]["pax"], default=(None, None))[0]
    flota = round(sum(ocupaciones) / len(ocupaciones)) if ocupaciones else 0
    e += seccion("Lectura del periodo", ancho=ANCHO)
    caja = Table([[_p(lectura(m, ant, pct, mejor, flota),
                      ParagraphStyle("lec", parent=T, fontSize=7.6, leading=10.5))]],
                 colWidths=[ANCHO])
    caja.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ARENA),
        ("BOX", (0, 0), (-1, -1), 0.5, LINEA),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    e += [caja, Spacer(1, 3),
          _p("Alcance: cifras de operación del sistema del lodge (reservas, actividades, "
             "traslados y spa). No incluye información financiera.", MUTE)]

    doc.build(e)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# El libro de Excel: para trabajar, no para leer
# ---------------------------------------------------------------------------

def libro(conn, desde, hasta):
    """El mismo periodo, en varias hojas y con los números como NÚMEROS.

    El PDF es para leer y presentar; esto es para filtrar y cruzar. La hoja «Datos» trae
    un renglón por salida, con filtro y formato de tabla, que es lo que hace falta para
    armar una tabla dinámica sin volver a pedirle nada a nadie.
    """
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table as XTable, TableStyleInfo

    m = metricas(conn, desde, hasta)
    p_desde, p_hasta = periodo_anterior(desde, hasta)
    ant = metricas(conn, p_desde, p_hasta)
    VERDE = "2C4A3E"
    wb = Workbook()

    def hoja(nombre, titulo, bajada=None):
        ws = wb.create_sheet(nombre)
        ws["A1"] = titulo
        ws["A1"].font = Font(size=13, bold=True, color=VERDE)
        ws["A2"] = bajada or titulo_del_periodo(desde, hasta)
        ws["A2"].font = Font(size=9, italic=True, color="6E6A5C")
        return ws

    def volcar(ws, fila, columnas, filas, totales=None):
        for i, (_, etiqueta, _) in enumerate(columnas, start=1):
            c = ws.cell(row=fila, column=i, value=etiqueta)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor=VERDE)
        ws.freeze_panes = ws.cell(row=fila + 1, column=1)
        r = fila
        for f in filas:
            r += 1
            for i, (clave, _, fmt) in enumerate(columnas, start=1):
                c = ws.cell(row=r, column=i, value=f.get(clave))
                if fmt:
                    c.number_format = fmt
        if totales:
            r += 1
            borde = Border(top=Side(style="thin", color=VERDE))
            for i, (clave, _, fmt) in enumerate(columnas, start=1):
                c = ws.cell(row=r, column=i, value=totales.get(clave))
                c.font = Font(bold=True)
                c.border = borde
                if fmt:
                    c.number_format = fmt
        for i, (clave, etiqueta, _) in enumerate(columnas, start=1):
            largos = [len(str(etiqueta))] + [len(str(f.get(clave) or "")) for f in filas]
            ws.column_dimensions[get_column_letter(i)].width = min(max(largos) + 3, 42)
        return r

    def var(a, b):
        return None if not b else (a - b) / b

    ws = hoja("Resumen", "Informe de operación · Corcovado Wilderness Lodge",
              f"{titulo_del_periodo(desde, hasta)} · comparado con "
              f"{fecha_larga(p_desde, False)} — {fecha_larga(p_hasta)}")
    pct = round(100 * m["reservas_con_tour"] / m["reservas_periodo"]) if m["reservas_periodo"] else 0
    pct_a = round(100 * ant["reservas_con_tour"] / ant["reservas_periodo"]) if ant["reservas_periodo"] else 0
    volcar(ws, 4, [("kpi", "Indicador", None), ("actual", "Periodo", "#,##0"),
                   ("previo", "Anterior", "#,##0"), ("var", "Variación", "0.0%")],
           [{"kpi": k, "actual": a, "previo": b, "var": var(a, b)} for k, a, b in [
               ("Pax-noche", m["pax_noche"], ant["pax_noche"]),
               ("Ocupación media (%)", m["ocupacion"], ant["ocupacion"]),
               ("Salidas de tour", m["salidas"], ant["salidas"]),
               ("Pax en tours", m["pax_tours"], ant["pax_tours"]),
               ("Reservas que entraron", m["reservas_periodo"], ant["reservas_periodo"]),
               ("…con al menos un tour", m["reservas_con_tour"], ant["reservas_con_tour"]),
               ("% que hace tour", pct, pct_a),
               ("Citas de spa activas", m["spa_activas"], ant["spa_activas"]),
               ("Reservas de cortesía", m["cortesias"], ant["cortesias"]),
               ("Pax en cortesías", m["cortesias_pax"], ant["cortesias_pax"]),
           ]])

    ws = hoja("Tours", "Tours por tipo")
    por_tour = agrupar(m["tours"], "tour_codigo")
    filas = [{"tour": k, "n": v["n"], "pax": v["pax"],
              "prom": round(v["pax"] / v["n"], 2) if v["n"] else 0}
             for k, v in sorted(por_tour.items(), key=lambda x: -x[1]["pax"])]
    volcar(ws, 4, [("tour", "Tour", None), ("n", "Salidas", "#,##0"),
                   ("pax", "Pax", "#,##0"), ("prom", "Pax por salida", "0.0")],
           filas, {"tour": "TOTAL", "n": sum(f["n"] for f in filas),
                   "pax": sum(f["pax"] for f in filas)})
    if filas:
        ch = BarChart()
        ch.type, ch.title, ch.legend = "bar", "Pax por tipo de tour", None
        ch.height, ch.width = 8, 14
        ch.add_data(Reference(ws, min_col=3, min_row=4, max_row=4 + len(filas)),
                    titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=5, max_row=4 + len(filas)))
        ws.add_chart(ch, "G4")

    ws = hoja("Guías", "Salidas y pax por guía")
    por_guia = agrupar(m["tours"], "guia_nombre")
    filas = [{"guia": k, "n": v["n"], "pax": v["pax"],
              "prom": round(v["pax"] / v["n"], 2) if v["n"] else 0}
             for k, v in sorted(por_guia.items(), key=lambda x: -x[1]["pax"])]
    volcar(ws, 4, [("guia", "Guía", None), ("n", "Salidas", "#,##0"),
                   ("pax", "Pax", "#,##0"), ("prom", "Pax por salida", "0.0")],
           filas, {"guia": "TOTAL", "n": sum(f["n"] for f in filas),
                   "pax": sum(f["pax"] for f in filas)})

    ws = hoja("Botes", "Viajes, pax y ocupación por bote",
              "La ocupación es el pax promedio por viaje sobre la capacidad del bote.")
    caps = {r["nombre"]: r["capacidad_max"]
            for r in conn.execute("SELECT nombre, capacidad_max FROM bote")}
    por_bote = agrupar(m["tours"], "bote_nombre")
    filas = []
    for k, v in sorted(por_bote.items(), key=lambda x: -x[1]["pax"]):
        cap = caps.get(k)
        prom = v["pax"] / v["n"] if v["n"] else 0
        filas.append({"bote": k, "n": v["n"], "pax": v["pax"], "prom": round(prom, 2),
                      "cap": cap, "ocup": (prom / cap) if cap else None})
    volcar(ws, 4, [("bote", "Bote", None), ("n", "Viajes", "#,##0"),
                   ("pax", "Pax", "#,##0"), ("prom", "Pax por viaje", "0.0"),
                   ("cap", "Capacidad", "#,##0"), ("ocup", "Ocupación", "0%")],
           filas, {"bote": "TOTAL", "n": sum(f["n"] for f in filas),
                   "pax": sum(f["pax"] for f in filas)})

    ws = hoja("Spa", "Spa por tratamiento", "Solo citas hechas y confirmadas.")
    trat = {}
    for c in m["spa"]:
        if c["estado"] in ("HECHA", "CONFIRMADA"):
            d = trat.setdefault(c["tratamiento"] or "(sin código)", {"n": 0, "min": 0})
            d["n"] += 1
            d["min"] += c["minutos"] or 0
    filas = [{"trat": k, "n": v["n"], "min": v["min"], "horas": round(v["min"] / 60, 1)}
             for k, v in sorted(trat.items(), key=lambda x: -x[1]["n"])]
    volcar(ws, 4, [("trat", "Tratamiento", None), ("n", "Citas", "#,##0"),
                   ("min", "Minutos", "#,##0"), ("horas", "Horas", "0.0")],
           filas, {"trat": "TOTAL", "n": sum(f["n"] for f in filas),
                   "min": sum(f["min"] for f in filas),
                   "horas": round(sum(f["min"] for f in filas) / 60, 1)})

    ws = hoja("Datos", "Un renglón por salida de tour",
              "Esta es la hoja para tablas dinámicas: tiene filtro y formato de tabla.")
    cols = [("fecha", "Fecha", None), ("tour", "Tour", None), ("pax", "Pax", "#,##0"),
            ("guia", "Guía", None), ("bote", "Bote", None), ("semana", "Semana", None)]
    filas = []
    for t in sorted(m["tours"], key=lambda x: x["fecha"]):
        f = datetime.date.fromisoformat(t["fecha"])
        filas.append({"fecha": t["fecha"], "tour": t["tour_codigo"], "pax": t["pax"],
                      "guia": t["guia_nombre"] or "(sin asignar)",
                      "bote": t["bote_nombre"] or "(sin asignar)",
                      "semana": f"{f.isocalendar()[1]:02d}"})
    fin = volcar(ws, 4, cols, filas)
    if filas:
        tab = XTable(displayName="Salidas",
                     ref=f"A4:{get_column_letter(len(cols))}{fin}")
        tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight11", showRowStripes=True)
        ws.add_table(tab)

    ws = hoja("Léeme", "Qué significa cada número",
              "Para que dos personas no lean lo mismo de forma distinta.")
    ws["A4"], ws["B4"] = "Término", "Qué es"
    for c in ("A4", "B4"):
        ws[c].font = Font(bold=True, color="FFFFFF")
        ws[c].fill = PatternFill("solid", fgColor=VERDE)
    definiciones = [
        ("Salida", "Una reserva asignada a un tour en una fecha. Si tres habitaciones van "
                   "al mismo tour el mismo día, son tres salidas y un solo guía."),
        ("Pax", "La gente de esa reserva que va a ESE tour. Puede ser menor que la de la "
                "habitación: se edita desde la agenda."),
        ("Pax-noche", "Suma de huéspedes dormidos cada noche del periodo."),
        ("Ocupación media", "Habitaciones ocupadas sobre el total del lodge, promediado "
                            "por noche. Usa el mismo total que la pantalla de ocupación."),
        ("Ocupación de bote", "Pax promedio por viaje sobre la capacidad del bote. Los "
                              "externos y privados no tienen tope y salen en blanco."),
        ("Citas de spa activas", "Hechas y confirmadas. Una solicitud sin confirmar no es "
                                 "trabajo hecho ni comprometido."),
        ("Cortesía", "Reserva cuya nota dice CPL, complementary o cortesía. Se cuenta "
                     "CUÁNTAS, no cuánto valen."),
        ("Periodo anterior", "Un mes se compara con el mes anterior de calendario; "
                             "cualquier otro rango, con la misma cantidad de días antes."),
        ("(sin asignar)", "El sistema no tiene ese dato. No es un cero: es algo que falta."),
    ]
    for i, (t, d) in enumerate(definiciones, start=5):
        ws.cell(row=i, column=1, value=t).font = Font(bold=True)
        ws.cell(row=i, column=2, value=d).alignment = Alignment(wrap_text=True,
                                                               vertical="top")
        ws.row_dimensions[i].height = 26
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 95

    del wb["Sheet"]
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
