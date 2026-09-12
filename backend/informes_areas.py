"""
Qué lleva el informe de cada área. Una definición por botón; el marco la dibuja.

CÓMO SE LEE ESTE ARCHIVO
------------------------
Cada área devuelve un diccionario con lo mismo: las cifras de cabecera, los bloques de
tabla, la tendencia, el párrafo de lectura y la tabla plana para el Excel. De ahí salen
el PDF y el libro, así que no pueden decir cosas distintas.

Las columnas se declaran una sola vez, en la forma (clave, encabezado, alineación,
formato_excel): 'i' alinea a la izquierda y 'd' a la derecha en el PDF; el formato es el
de Excel, y va vacío cuando la columna es texto.

Los informes se imprimen EN INGLÉS (ver informe.py). Los nombres que vienen de los datos
—Sierpe, Drake, Terra Kitchen, los códigos de tour, los tratamientos del spa— se dejan
como están: son nombres, no texto traducible.

EL PARRAFO DE LECTURA
---------------------
Se redacta con los MISMOS datos de las tablas, no aparte. Escrito a mano, tarde o
temprano diría algo que las tablas desmienten, y en un informe que se manda afuera eso
cuesta más que no tenerlo.
"""
import datetime

import informe as inf

LODGE = "Corcovado Wilderness Lodge"

# El ancho de las columnas del PDF, en milímetros, por familia de tabla. Explícito y no
# calculado: una tabla que se reacomoda sola termina desbordando la hoja sin avisar.
A_NOMBRE_N_PAX_BARRA = [26 * inf.mm, 12 * inf.mm, 13 * inf.mm, 38 * inf.mm]
A_TRES = [37 * inf.mm, 26 * inf.mm, 26 * inf.mm]
A_CUATRO = [34 * inf.mm, 18 * inf.mm, 18 * inf.mm, 19 * inf.mm]


def _bloque(lado, titulo, columnas, filas, anchos, **extra):
    b = {"lado": lado, "titulo": titulo, "columnas": columnas, "filas": filas,
         "anchos": anchos}
    b.update(extra)
    return b


def _n_pax(nombre_clave, etiqueta):
    """La tabla de siempre: nombre, cuántas, pax y una barra."""
    return [(nombre_clave, etiqueta, "i", None), ("n", "Count", "d", "#,##0"),
            ("pax", "Pax", "d", "#,##0"), ("bar", "", "i", None)]


def _con_barra(filas, tope):
    return [dict(f, bar=f.get("pax") or 0) for f in filas], tope


def _totales(filas, clave_nombre):
    return {clave_nombre: inf.TOTAL, "n": sum(f["n"] for f in filas),
            "pax": sum(f["pax"] for f in filas)}


# ---------------------------------------------------------------------------
# Analítica — el informe a inversionistas
# ---------------------------------------------------------------------------

def analitica(conn, desde, hasta):
    m = inf.metricas(conn, desde, hasta)
    ant = inf.metricas(conn, *inf.periodo_anterior(desde, hasta))
    pct = round(100 * m["reservas_con_tour"] / m["reservas_periodo"]) if m["reservas_periodo"] else 0
    pct_a = round(100 * ant["reservas_con_tour"] / ant["reservas_periodo"]) if ant["reservas_periodo"] else 0

    por_tour = inf.agrupar(m["tours"], "tour_codigo")
    filas_t = inf.top_y_otros(por_tour, 7, "tour")
    por_guia = inf.agrupar(m["tours"], "guia_nombre")
    filas_g = inf.top_y_otros(por_guia, 6, "guia")

    caps = {r["nombre"]: r["capacidad_max"]
            for r in conn.execute("SELECT nombre, capacidad_max FROM bote")}
    por_bote = inf.agrupar(m["tours"], "bote_nombre")
    filas_b, ocupaciones = [], []
    for k, v in sorted(por_bote.items(), key=lambda x: -x[1]["pax"])[:6]:
        cap, prom = caps.get(k), (v["pax"] / v["n"] if v["n"] else 0)
        if cap:
            ocupaciones.append(100 * prom / cap)
        filas_b.append({"bote": k, "n": v["n"], "prom": round(prom, 1),
                        "ocup": f"{100 * prom / cap:.0f}%" if cap else "no cap",
                        "bar": round(100 * prom / cap) if cap else 0})

    puntos = _puntos(conn, desde, hasta)
    filas_p = [{"punto": k, "e": v["e"], "s": v["s"]} for k, v in sorted(puntos.items())]

    trat = {}
    for c in m["spa"]:
        if c["estado"] in ("HECHA", "CONFIRMADA"):
            d = trat.setdefault(c["tratamiento"] or SIN_CODIGO, {"n": 0, "pax": 0})
            d["n"] += 1
            d["pax"] += c["minutos"] or 0
    filas_s = inf.top_y_otros(trat, 5, "trat")
    estados = _conteo(m["spa"], "estado")

    flota = round(sum(ocupaciones) / len(ocupaciones)) if ocupaciones else 0
    mejor = max(por_tour.items(), key=lambda x: x[1]["pax"], default=(None, None))[0]

    return {
        "titulo": "Operations Report", "subtitulo": "Investor report",
        "desde": desde, "hasta": hasta,
        "kpis": [
            ("Pax-nights", m["pax_noche"], ant["pax_noche"], "", None),
            ("Occupancy", m["ocupacion"], ant["ocupacion"], "%", None),
            ("Tour departures", m["salidas"], ant["salidas"], "", None),
            ("Tour pax", m["pax_tours"], ant["pax_tours"], "", None),
            ("Take a tour", pct, pct_a, "%",
             f"{m['reservas_con_tour']} of {m['reservas_periodo']}"),
            ("Spa bookings", m["spa_activas"], ant["spa_activas"], "", None),
            ("Complimentary", m["cortesias"], ant["cortesias"], "",
             f"{m['cortesias_pax']} pax"),
        ],
        "neutrales": ("Complimentary",),
        "bloques": [
            _bloque("izq", "Tours by type", _n_pax("tour", "Tour"),
                    *_barra_y_anchos(filas_t), total=_totales(filas_t, "tour"),
                    barra_en="bar", tope=_tope(por_tour), grafico="pax",
                    nota="A departure is one reservation on one tour on one date. "
                         "Pax is the tour's own, which can be fewer than the room's."),
            _bloque("izq", "Guides", _n_pax("guia", "Guide"),
                    *_barra_y_anchos(filas_g), total=_totales(filas_g, "guia"),
                    barra_en="bar", tope=_tope(por_guia),
                    nota="Departures handled and pax carried per guide."),
            _bloque("der", "Boats · utilization",
                    [("bote", "Boat", "i", None), ("n", "Trips", "d", "#,##0"),
                     ("prom", "Pax/trip", "d", "0.0"),
                     ("ocup", "Util.", "d", None), ("bar", "", "i", None)],
                    filas_b,
                    [23 * inf.mm, 13 * inf.mm, 18 * inf.mm, 13 * inf.mm, 22 * inf.mm],
                    barra_en="bar", tope=100,
                    nota="Average pax per trip against the boat's capacity. This is the "
                         "figure that says whether there is too much or too little fleet."),
            _bloque("der", "Embarkation points",
                    [("punto", "Point", "i", None), ("e", "Pax in", "d", "#,##0"),
                     ("s", "Pax out", "d", "#,##0")],
                    filas_p, A_TRES,
                    total={"punto": inf.TOTAL, "e": sum(f["e"] for f in filas_p),
                           "s": sum(f["s"] for f in filas_p)},
                    nota="Pax arriving and departing through each point."),
            _bloque("der", "Spa",
                    [("trat", "Treatment", "i", None), ("n", "Bookings", "d", "#,##0"),
                     ("horas", "Hours", "d", "0.0")],
                    [dict(f, horas=round(f["pax"] / 60, 1)) for f in filas_s],
                    [45 * inf.mm, 20 * inf.mm, 24 * inf.mm],
                    total={"trat": inf.TOTAL, "n": sum(f["n"] for f in filas_s),
                           "horas": round(sum(f["pax"] for f in filas_s) / 60, 1)},
                    nota="Completed and confirmed bookings in the period.",
                    pie=(f"Of the {len(m['spa'])} bookings in the period: "
                         + " · ".join(f"{_ingles_estado(k)} {v}"
                                      for k, v in sorted(estados.items()))
                         ) if m["spa"] else None),
        ],
        "tendencia": _tendencia(conn, desde, hasta),
        "lectura": _lectura_analitica(m, ant, pct, mejor, flota),
        "datos": {
            "titulo": "One row per tour departure",
            "columnas": [("fecha", "Date", "i", None), ("tour", "Tour", "i", None),
                         ("pax", "Pax", "d", "#,##0"), ("guia", "Guide", "i", None),
                         ("bote", "Boat", "i", None), ("hab", "Room", "i", None),
                         ("semana", "Week", "i", None)],
            "filas": [_fila_tour(t) for t in sorted(m["tours"], key=lambda x: x["fecha"])],
        },
        "definiciones": [
            ("Departure", "One reservation assigned to one tour on one date. If three "
                          "rooms join the same tour the same day, that is three "
                          "departures and one guide."),
            ("Pax", "The people from that reservation who join THAT tour. It can be "
                    "fewer than the room's, and is edited from the tour agenda."),
            ("Pax-nights", "Sum of guests sleeping at the lodge each night of the period."),
            ("Occupancy", "Rooms occupied over the lodge total, averaged per night. Uses "
                          "the same room total as the occupancy screen."),
            ("Boat utilization", "Average pax per trip over the boat's capacity. External "
                                 "and private boats have no cap and are left blank."),
            ("Spa bookings", "Completed and confirmed. A request that is not yet "
                             "confirmed is neither work done nor work committed."),
            ("Complimentary", "A reservation whose note says CPL, complementary or "
                              "cortesía. Counted as HOW MANY, never as an amount."),
        ],
    }


SIN_CODIGO = "(no code)"
_ESTADOS_ES_EN = {"HECHA": "completed", "CONFIRMADA": "confirmed",
                  "SOLICITADA": "requested", "CANCELADA": "cancelled",
                  "PENDIENTE": "pending", "LISTA": "done", "EN_CURSO": "in progress"}


def _ingles_estado(estado):
    return _ESTADOS_ES_EN.get((estado or "").upper(), (estado or "").lower())


def _conteo(filas, clave):
    salida = {}
    for f in filas:
        salida[f.get(clave)] = salida.get(f.get(clave), 0) + 1
    return salida


def _tope(pares):
    return max((v["pax"] for v in pares.values()), default=1)


def _barra_y_anchos(filas):
    """Las filas con su barra, y el ancho de la tabla de siempre."""
    return [dict(f, bar=f.get("pax") or 0) for f in filas], A_NOMBRE_N_PAX_BARRA


def _fila_tour(t):
    f = datetime.date.fromisoformat(t["fecha"])
    return {"fecha": t["fecha"], "tour": t["tour_codigo"], "pax": t["pax"],
            "guia": t["guia_nombre"] or inf.SIN_ASIGNAR,
            "bote": t["bote_nombre"] or inf.SIN_ASIGNAR,
            "hab": t.get("room_no"), "semana": f"{f.isocalendar()[1]:02d}"}


def _puntos(conn, desde, hasta):
    """Pax que entra y sale por cada punto de embarque."""
    d0i, d1i = inf.yymmdd(desde), inf.yymmdd(hasta)
    puntos = {}
    for col, lado, fecha in (("punto_entrada", "e", "arr_date"),
                             ("punto_salida", "s", "dep_date")):
        for r in conn.execute(
                f"""SELECT {col} p, SUM(adl+chl) pax FROM reserva
                    WHERE {col} IS NOT NULL AND res_status != 'CANCELADA'
                      AND {inf.sql_fecha(fecha)} BETWEEN ? AND ?
                    GROUP BY {col}""", (d0i, d1i)):
            puntos.setdefault(r["p"], {"e": 0, "s": 0})[lado] = r["pax"] or 0
    return puntos


def _tendencia(conn, desde, hasta, **kw):
    valores, etiquetas, dentro, titulo = inf.serie_de_tendencia(conn, desde, hasta, **kw)
    return {"valores": valores, "etiquetas": etiquetas, "dentro": dentro,
            "titulo": titulo}


def _lectura_analitica(m, ant, pct, mejor, flota):
    var = inf._delta(m["pax_noche"], ant["pax_noche"])[0]
    # Con cero reservas entrando, «0% took a tour» es cierto y se lee mal: parece un mal
    # resultado cuando no hubo a quién ofrecerle nada.
    entrada = (f"<b>{pct}%</b> of arriving reservations joined at least one activity"
               if m["reservas_periodo"] else "No new reservations arrived")
    frases = [
        f"The lodge hosted <b>{m['pax_noche']} pax-nights</b> at an average occupancy of "
        f"<b>{m['ocupacion']}%</b> ({var} against the previous period).",
        f"{entrada}; <b>{inf.plural(m['salidas'], 'departure', 'departures')}</b> "
        f"carried <b>{m['pax_tours']} pax</b>."
        + (f" The most requested activity was <b>{mejor}</b>." if mejor else ""),
    ]
    if flota:
        frases.append(f"The owned fleet ran at <b>{flota}%</b> of its average capacity "
                      f"per trip.")
    if m["cortesias"] or ant["cortesias"]:
        frases.append(
            f"<b>{inf.plural(m['cortesias'], 'complimentary reservation', 'complimentary reservations')}</b> "
            f"were recorded ({m['cortesias_pax']} pax), against {ant['cortesias']} in the "
            f"previous period.")
    return " ".join(frases)


# ---------------------------------------------------------------------------
# Agenda de tours
# ---------------------------------------------------------------------------

def agenda(conn, desde, hasta):
    m = inf.metricas(conn, desde, hasta)
    ant = inf.metricas(conn, *inf.periodo_anterior(desde, hasta))
    tours = m["tours"]
    sin_guia = len([t for t in tours if not t["guia_nombre"]])
    sin_bote = len([t for t in tours if not t["bote_nombre"]])
    guias = len({t["guia_nombre"] for t in tours if t["guia_nombre"]})
    botes = len({t["bote_nombre"] for t in tours if t["bote_nombre"]})
    ant_sin_guia = len([t for t in ant["tours"] if not t["guia_nombre"]])

    por_tour = inf.agrupar(tours, "tour_codigo")
    filas_t = inf.top_y_otros(por_tour, 8, "tour")
    por_guia = inf.agrupar(tours, "guia_nombre")
    filas_g = inf.top_y_otros(por_guia, 7, "guia")
    por_bote = inf.agrupar(tours, "bote_nombre")
    filas_b = inf.top_y_otros(por_bote, 6, "bote")

    por_dia = {}
    for t in tours:
        d = por_dia.setdefault(t["fecha"], {"n": 0, "pax": 0})
        d["n"] += 1
        d["pax"] += t["pax"] or 0
    filas_d = [{"dia": k, "n": v["n"], "pax": v["pax"]}
               for k, v in sorted(por_dia.items())][-7:]

    return {
        "titulo": "Tour Agenda", "subtitulo": f"{LODGE} · operations",
        "desde": desde, "hasta": hasta,
        "kpis": [
            ("Departures", len(tours), len(ant["tours"]), "", None),
            ("Tour pax", m["pax_tours"], ant["pax_tours"], "", None),
            ("Tour types", len(por_tour), len(inf.agrupar(ant["tours"], "tour_codigo")),
             "", None),
            ("Guides used", guias, None, "", None),
            ("Boats used", botes, None, "", None),
            ("No guide", sin_guia, ant_sin_guia, "", "to be assigned"),
            ("No boat", sin_bote, None, "", "to be assigned"),
        ],
        "neutrales": ("Guides used", "Boats used"),
        "bloques": [
            _bloque("izq", "Tours by type", _n_pax("tour", "Tour"),
                    *_barra_y_anchos(filas_t), total=_totales(filas_t, "tour"),
                    barra_en="bar", tope=_tope(por_tour), grafico="pax"),
            _bloque("izq", "Guides", _n_pax("guia", "Guide"),
                    *_barra_y_anchos(filas_g), total=_totales(filas_g, "guia"),
                    barra_en="bar", tope=_tope(por_guia)),
            _bloque("der", "Boats", _n_pax("bote", "Boat"),
                    *_barra_y_anchos(filas_b), total=_totales(filas_b, "bote"),
                    barra_en="bar", tope=_tope(por_bote)),
            _bloque("der", "Last days",
                    [("dia", "Date", "i", None), ("n", "Departures", "d", "#,##0"),
                     ("pax", "Pax", "d", "#,##0")],
                    filas_d, A_TRES,
                    nota="The final days of the period, day by day."),
        ],
        "tendencia": _tendencia(conn, desde, hasta),
        "lectura": _lectura_agenda(m, ant, por_tour, sin_guia, sin_bote),
        "datos": {
            "titulo": "One row per tour departure",
            "columnas": [("fecha", "Date", "i", None), ("tour", "Tour", "i", None),
                         ("hab", "Room", "i", None), ("pax", "Pax", "d", "#,##0"),
                         ("guia", "Guide", "i", None), ("bote", "Boat", "i", None),
                         ("semana", "Week", "i", None)],
            "filas": [_fila_tour(t) for t in sorted(tours, key=lambda x: x["fecha"])],
        },
        "definiciones": [
            ("Departure", "One reservation assigned to one tour on one date."),
            ("Without guide / boat", "Departures still unassigned. Each one is a tour "
                                     "that would leave without someone responsible."),
        ],
    }


def _lectura_agenda(m, ant, por_tour, sin_guia, sin_bote):
    var = inf._delta(len(m["tours"]), len(ant["tours"]))[0]
    frases = [
        f"<b>{inf.plural(len(m['tours']), 'departure', 'departures')}</b> across "
        f"<b>{len(por_tour)}</b> tour types carried <b>{m['pax_tours']} pax</b> "
        f"({var} against the previous period)."]
    pendientes = []
    if sin_guia:
        pendientes.append(inf.plural(sin_guia, "departure", "departures") + " without a guide")
    if sin_bote:
        pendientes.append(inf.plural(sin_bote, "departure", "departures") + " without a boat")
    frases.append(
        f"Still to assign: {' and '.join(pendientes)}." if pendientes
        else "Every departure has a guide and a boat assigned.")
    return " ".join(frases)


# ---------------------------------------------------------------------------
# Transporte — entradas y salidas del lodge
# ---------------------------------------------------------------------------

def transporte(conn, desde, hasta):
    m = inf.metricas(conn, desde, hasta)
    ant = inf.metricas(conn, *inf.periodo_anterior(desde, hasta))

    def pax(rs):
        return sum((r["adl"] or 0) + (r["chl"] or 0) for r in rs)

    entra, sale = m["entraron"], m["salieron"]
    sin_punto_e = len([r for r in entra if not r["punto_entrada"]])
    sin_punto_s = len([r for r in sale if not r["punto_salida"]])

    por_e = inf.agrupar([dict(r, pax=(r["adl"] or 0) + (r["chl"] or 0))
                         for r in entra], "punto_entrada")
    por_s = inf.agrupar([dict(r, pax=(r["adl"] or 0) + (r["chl"] or 0))
                         for r in sale], "punto_salida")
    filas_e = inf.top_y_otros(por_e, 5, "punto")
    filas_s = inf.top_y_otros(por_s, 5, "punto")

    por_dia = {}
    for r in entra:
        d = por_dia.setdefault(r["arr_date"], {"e": 0, "s": 0})
        d["e"] += (r["adl"] or 0) + (r["chl"] or 0)
    for r in sale:
        d = por_dia.setdefault(r["dep_date"], {"e": 0, "s": 0})
        d["s"] += (r["adl"] or 0) + (r["chl"] or 0)
    filas_d = sorted(({"dia": k, "e": v["e"], "s": v["s"]}
                      for k, v in por_dia.items()),
                     key=lambda x: inf.a_fecha(x["dia"]) or datetime.date.min)[-7:]

    return {
        "titulo": "Arrivals & Departures", "subtitulo": f"{LODGE} · transfers",
        "desde": desde, "hasta": hasta,
        "kpis": [
            ("Arrivals", len(entra), len(ant["entraron"]), "", None),
            ("Pax in", pax(entra), pax(ant["entraron"]), "", None),
            ("Departures", len(sale), len(ant["salieron"]), "", None),
            ("Pax out", pax(sale), pax(ant["salieron"]), "", None),
            ("In · no point", sin_punto_e, None, "", "to be confirmed"),
            ("Out · no point", sin_punto_s, None, "", "to be confirmed"),
        ],
        "neutrales": (),
        "bloques": [
            _bloque("izq", "Arrivals by point",
                    [("punto", "Point", "i", None), ("n", "Rsv.", "d", "#,##0"),
                     ("pax", "Pax", "d", "#,##0"), ("bar", "", "i", None)],
                    *_barra_y_anchos(filas_e), total=_totales(filas_e, "punto"),
                    barra_en="bar", tope=_tope(por_e), grafico="pax",
                    nota="Where guests come into the lodge from."),
            _bloque("izq", "Departures by point",
                    [("punto", "Point", "i", None), ("n", "Rsv.", "d", "#,##0"),
                     ("pax", "Pax", "d", "#,##0"), ("bar", "", "i", None)],
                    *_barra_y_anchos(filas_s), total=_totales(filas_s, "punto"),
                    barra_en="bar", tope=_tope(por_s)),
            _bloque("der", "Movement by day",
                    [("dia", "Date", "i", None), ("e", "Pax in", "d", "#,##0"),
                     ("s", "Pax out", "d", "#,##0")],
                    filas_d, A_TRES,
                    nota="The final days of the period. Peaks are the days that need "
                         "more than one boat run."),
        ],
        "tendencia": _tendencia(
            conn, desde, hasta,
            consulta=_por_dia_de_reserva("arr_date", "SUM(adl+chl)"),
            titulo_dia="Pax arriving by day", titulo_semana="Pax arriving by week"),
        "lectura": _lectura_transporte(entra, sale, pax, por_e, sin_punto_e, sin_punto_s),
        "datos": {
            "titulo": "One row per movement",
            "columnas": [("fecha", "Date", "i", None), ("tipo", "Type", "i", None),
                         ("hab", "Room", "i", None), ("nombre", "Guest", "i", None),
                         ("punto", "Point", "i", None), ("pax", "Pax", "d", "#,##0")],
            "filas": (
                [{"fecha": r["arr_date"], "tipo": "Arrival", "hab": r["room_no"],
                  "nombre": r.get("nombre_principal"),
                  "punto": r["punto_entrada"] or inf.SIN_ASIGNAR,
                  "pax": (r["adl"] or 0) + (r["chl"] or 0)} for r in entra]
                + [{"fecha": r["dep_date"], "tipo": "Departure", "hab": r["room_no"],
                    "nombre": r.get("nombre_principal"),
                    "punto": r["punto_salida"] or inf.SIN_ASIGNAR,
                    "pax": (r["adl"] or 0) + (r["chl"] or 0)} for r in sale]),
        },
        "definiciones": [
            ("Point", "Sierpe or Drake. Anything the system cannot confirm is left "
                      "unassigned on purpose: sending a boat to the wrong place is an "
                      "expensive mistake and is not decided by guessing."),
            ("Pax in / out", "Adults plus children on the reservations arriving or "
                             "departing that day."),
        ],
    }


def _iso_de_yy(valor):
    """'26-08-05' -> '2026-08-05'. None si no tiene forma de fecha.

    Las consultas que agrupan por la expresión de fecha de la reserva devuelven la clave
    en YY-MM-DD, y la serie de tendencia busca por fecha ISO. Sin convertirla, la búsqueda
    no encontraba NADA y el gráfico salía entero en cero — sin dar ningún error, que es
    la peor forma de fallar: un cero se lee como «no hubo nadie».
    """
    try:
        y, m, d = (valor or "").split("-")
        return datetime.date(2000 + int(y), int(m), int(d)).isoformat()
    except (ValueError, AttributeError):
        return None


def _por_dia_de_reserva(columna, agregado):
    """Una serie diaria sacada de la tabla de reservas, con la clave ya en ISO."""
    def consulta(c, ini, fin):
        expr = inf.sql_fecha(columna)
        filas = c.execute(
            f"""SELECT {expr} f, {agregado} v FROM reserva
                WHERE res_status != 'CANCELADA' AND {expr} BETWEEN ? AND ?
                GROUP BY f""", (inf.yymmdd(ini), inf.yymmdd(fin)))
        salida = {}
        for r in filas:
            iso = _iso_de_yy(r["f"])
            if iso:
                salida[iso] = r["v"] or 0
        return salida
    return consulta


def _lectura_transporte(entra, sale, pax, por_e, sin_e, sin_s):
    principal = max(por_e.items(), key=lambda x: x[1]["pax"], default=(None, None))[0]
    frases = [
        f"<b>{pax(entra)} pax</b> arrived across "
        f"<b>{inf.plural(len(entra), 'reservation', 'reservations')}</b> and "
        f"<b>{pax(sale)} pax</b> departed across "
        f"<b>{inf.plural(len(sale), 'reservation', 'reservations')}</b>."]
    if principal and principal != inf.SIN_ASIGNAR:
        frases.append(f"Most arrivals came through <b>{principal}</b>.")
    if sin_e or sin_s:
        frases.append(f"<b>{sin_e + sin_s}</b> movements still have no confirmed "
                      f"embarkation point and need reception to resolve them.")
    else:
        frases.append("Every movement has a confirmed embarkation point.")
    return " ".join(frases)


# ---------------------------------------------------------------------------
# Restaurantes
# ---------------------------------------------------------------------------

_REGIMEN_EN = {
    "PENSION_COMPLETA": "Full board", "DESAYUNO_CENA": "Breakfast & dinner",
    "SOLO_DESAYUNO": "Breakfast only", "TODO_INCLUIDO": "All inclusive",
    "SIN_COMIDAS": "No meals",
}


def restaurantes(conn, desde, hasta):
    import restaurantes as rest
    m = inf.metricas(conn, desde, hasta)
    ant = inf.metricas(conn, *inf.periodo_anterior(desde, hasta))

    # Se recorre día por día: la distribución se calcula por fecha y un rango es la suma
    # de sus días, no una consulta aparte que podría no coincidir con la pantalla.
    d0 = datetime.date.fromisoformat(desde)
    dias = (datetime.date.fromisoformat(hasta) - d0).days + 1
    comidas = {"Dinner": {}, "Lunch": {}}
    privadas = 0
    manuales = 0
    filas_datos = []
    for i in range(dias):
        dia = (d0 + datetime.timedelta(days=i)).isoformat()
        d = rest.distribuir(conn, dia)
        for etiqueta, bloque in (("Dinner", d["cena"]), ("Lunch", d["almuerzo"])):
            for restaurante, clave in ((rest.TERRA, "terra_kitchen"),
                                       (rest.BOSQUE, "bar_el_bosque")):
                for x in bloque.get(clave) or []:
                    c = comidas[etiqueta].setdefault(restaurante, {"n": 0, "pax": 0})
                    c["n"] += 1
                    c["pax"] += x["pax"]
                    if x.get("fijo") and "privada" in str(x["fijo"]):
                        privadas += 1
                    if x.get("manual"):
                        manuales += 1
                    filas_datos.append({
                        "fecha": dia, "comida": etiqueta, "restaurante": restaurante,
                        "hab": x["room_no"], "nombre": x["nombre"], "pax": x["pax"],
                        "situacion": "Arriving" if x["tipo"] == "ENTRA" else "In house",
                        "hora": x.get("hora") or "",
                        "nota": x.get("fijo") or ("manual change" if x.get("manual") else "")})

    def filas_de(etiqueta):
        return [{"sitio": k, "n": v["n"], "pax": v["pax"]}
                for k, v in sorted(comidas[etiqueta].items(), key=lambda x: -x[1]["pax"])]

    cena, almuerzo = filas_de("Dinner"), filas_de("Lunch")
    pax_cena = sum(f["pax"] for f in cena)
    pax_alm = sum(f["pax"] for f in almuerzo)

    regimen = inf.agrupar(
        [dict(r, pax=(r["adl"] or 0) + (r["chl"] or 0)) for r in m["reservas"]
         if r.get("regimen")], "regimen")
    filas_r = [{"reg": _REGIMEN_EN.get(k, k), "n": v["n"], "pax": v["pax"]}
               for k, v in sorted(regimen.items(), key=lambda x: -x[1]["pax"])][:6]

    return {
        "titulo": "Restaurant Report", "subtitulo": f"{LODGE} · food & beverage",
        "desde": desde, "hasta": hasta,
        "kpis": [
            ("Dinner covers", pax_cena, None, "", None),
            ("Lunch covers", pax_alm, None, "", None),
            ("Pax-nights", m["pax_noche"], ant["pax_noche"], "", None),
            ("Occupancy", m["ocupacion"], ant["ocupacion"], "%", None),
            ("Private dinners", privadas, None, "", None),
            ("Manual changes", manuales, None, "", None),
        ],
        "neutrales": ("Private dinners", "Manual changes"),
        "bloques": [
            _bloque("izq", "Dinner by restaurant",
                    [("sitio", "Restaurant", "i", None), ("n", "Rooms", "d", "#,##0"),
                     ("pax", "Covers", "d", "#,##0"), ("bar", "", "i", None)],
                    *_barra_y_anchos(cena), total=_totales(cena, "sitio"),
                    barra_en="bar", tope=max([f["pax"] for f in cena] or [1]),
                    grafico="pax",
                    nota="Covers served at each restaurant across the period."),
            _bloque("izq", "Lunch by restaurant",
                    [("sitio", "Restaurant", "i", None), ("n", "Rooms", "d", "#,##0"),
                     ("pax", "Covers", "d", "#,##0"), ("bar", "", "i", None)],
                    *_barra_y_anchos(almuerzo), total=_totales(almuerzo, "sitio"),
                    barra_en="bar", tope=max([f["pax"] for f in almuerzo] or [1])),
            _bloque("der", "Meal plan",
                    [("reg", "Plan", "i", None), ("n", "Rsv.", "d", "#,##0"),
                     ("pax", "Pax", "d", "#,##0")],
                    filas_r, A_TRES,
                    nota="What each reservation has paid for, from its rate plan."),
        ],
        "tendencia": _tendencia(conn, desde, hasta),
        "lectura": _lectura_restaurantes(pax_cena, pax_alm, cena, privadas, manuales),
        "datos": {
            "titulo": "One row per guest and meal",
            "columnas": [("fecha", "Date", "i", None), ("comida", "Meal", "i", None),
                         ("restaurante", "Restaurant", "i", None),
                         ("hab", "Room", "i", None), ("nombre", "Guest", "i", None),
                         ("pax", "Pax", "d", "#,##0"),
                         ("situacion", "Status", "i", None),
                         ("hora", "Table time", "i", None),
                         ("nota", "Note", "i", None)],
            "filas": filas_datos,
        },
        "definiciones": [
            ("Cover", "One guest seated for one meal. A room of three counts three."),
            ("Private dinner", "Served away from the dining room but still taking a "
                               "seat at Bar el Bosque: it occupies service."),
            ("Manual change", "A room moved between restaurants by reception. Groups "
                              "move together."),
        ],
    }


def _lectura_restaurantes(pax_cena, pax_alm, cena, privadas, manuales):
    frases = [f"<b>{pax_cena} dinner covers</b> and <b>{pax_alm} lunch covers</b> were "
              f"served in the period."]
    if len(cena) >= 2:
        a, b = cena[0], cena[1]
        frases.append(f"Dinner split <b>{a['pax']}</b> at {a['sitio']} against "
                      f"<b>{b['pax']}</b> at {b['sitio']}.")
    if privadas:
        frases.append(f"<b>{inf.plural(privadas, 'private dinner', 'private dinners')}</b> "
                      f"were served.")
    if manuales:
        frases.append(f"<b>{manuales}</b> rooms were moved between restaurants by hand.")
    return " ".join(frases)


# ---------------------------------------------------------------------------
# Entradas al parque (SINAC)
# ---------------------------------------------------------------------------

def sinac(conn, desde, hasta):
    filas = [dict(r) for r in conn.execute(
        "SELECT * FROM entrada_sinac WHERE fecha BETWEEN ? AND ? ORDER BY fecha",
        (desde, hasta))]
    hoy = datetime.date.today()
    compradas = [f for f in filas if f["estado"] == "COMPRADA"]
    pendientes = [f for f in filas if f["estado"] != "COMPRADA"]
    por_vencer = [f for f in pendientes
                  if (datetime.date.fromisoformat(f["fecha"]) - hoy).days <= 15]

    por_tour = {}
    for f in filas:
        d = por_tour.setdefault(f["tour_codigo"], {"n": 0, "pax": 0})
        d["n"] += 1
        d["pax"] += f["pax_total_grupo"] or 0
    filas_t = inf.top_y_otros(por_tour, 7, "tour")

    por_estado = {}
    for f in filas:
        d = por_estado.setdefault(_ingles_estado(f["estado"]), {"n": 0, "pax": 0})
        d["n"] += 1
        d["pax"] += f["pax_total_grupo"] or 0
    filas_e = [{"estado": k, "n": v["n"], "pax": v["pax"]}
               for k, v in sorted(por_estado.items(), key=lambda x: -x[1]["pax"])]

    return {
        "titulo": "National Park Entries", "subtitulo": f"{LODGE} · SINAC",
        "desde": desde, "hasta": hasta,
        "kpis": [
            ("Entries", len(filas), None, "", None),
            ("Pax + guide", sum(f["pax_total_grupo"] or 0 for f in filas), None, "", None),
            ("Purchased", len(compradas), None, "", None),
            ("Outstanding", len(pendientes), None, "", None),
            ("Due < 15 days", len(por_vencer), None, "", "buy now"),
        ],
        "neutrales": ("Entries", "Pax + guide"),
        "bloques": [
            _bloque("izq", "Entries by activity",
                    [("tour", "Activity", "i", None), ("n", "Entries", "d", "#,##0"),
                     ("pax", "Pax + guide", "d", "#,##0"), ("bar", "", "i", None)],
                    *_barra_y_anchos(filas_t), total=_totales(filas_t, "tour"),
                    barra_en="bar", tope=_tope(por_tour), grafico="pax",
                    nota="One entry covers everyone on that activity that day, guide "
                         "included."),
            _bloque("der", "Entries by status",
                    [("estado", "Status", "i", None), ("n", "Entries", "d", "#,##0"),
                     ("pax", "Pax + guide", "d", "#,##0")],
                    filas_e, A_TRES,
                    total={"estado": inf.TOTAL, "n": sum(f["n"] for f in filas_e),
                           "pax": sum(f["pax"] for f in filas_e)},
                    nota="Park entries must be bought 15 days ahead."),
        ],
        "tendencia": _tendencia(
            conn, desde, hasta,
            consulta=lambda c, ini, fin: {
                r["f"]: r["v"] or 0 for r in c.execute(
                    """SELECT fecha f, SUM(pax_total_grupo) v FROM entrada_sinac
                       WHERE fecha BETWEEN ? AND ? GROUP BY fecha""", (ini, fin))},
            titulo_dia="Park pax by day", titulo_semana="Park pax by week"),
        "lectura": _lectura_sinac(filas, compradas, pendientes, por_vencer),
        "datos": {
            "titulo": "One row per park entry",
            "columnas": [("fecha", "Date", "i", None), ("tour", "Activity", "i", None),
                         ("pax", "Pax + guide", "d", "#,##0"),
                         ("conf", "Confirmation", "i", None),
                         ("estado", "Status", "i", None)],
            "filas": [{"fecha": f["fecha"], "tour": f["tour_codigo"],
                       "pax": f["pax_total_grupo"], "conf": f["conf_entrada"] or "",
                       "estado": _ingles_estado(f["estado"])} for f in filas],
        },
        "definiciones": [
            ("Pax + guide", "Park entries are bought per head and include one entry for "
                            "the guide on each departure."),
            ("Due within 15 days", "Entries must be purchased 15 days ahead. These are "
                                   "the ones that cannot wait."),
        ],
    }


def _lectura_sinac(filas, compradas, pendientes, por_vencer):
    total_pax = sum(f["pax_total_grupo"] or 0 for f in filas)
    frases = [f"<b>{inf.plural(len(filas), 'park entry', 'park entries')}</b> covering "
              f"<b>{total_pax} pax</b> fall in this period."]
    frases.append(
        f"<b>{len(compradas)}</b> are already purchased and <b>{len(pendientes)}</b> "
        f"remain outstanding." if filas else "No park entries fall in this period.")
    if por_vencer:
        frases.append(f"<b>{len(por_vencer)}</b> of them are due within the 15-day "
                      f"purchase window and cannot wait.")
    return " ".join(frases)


# ---------------------------------------------------------------------------
# Amenidades / requerimientos del huésped
# ---------------------------------------------------------------------------

def amenidades(conn, desde, hasta):
    d0i, d1i = inf.yymmdd(desde), inf.yymmdd(hasta)
    filas = [dict(r) for r in conn.execute(
        f"""SELECT a.*, r.room_no, r.nombre_principal, r.arr_date
            FROM amenidad_tarea a LEFT JOIN reserva r ON r.conf_no = a.conf_no
            WHERE (a.fecha BETWEEN ? AND ?)
               OR (a.fecha IS NULL AND {inf.sql_fecha('r.arr_date')} BETWEEN ? AND ?)
            ORDER BY a.fecha""", (desde, hasta, d0i, d1i))]

    def cuenta(clave, traducir=False):
        salida = {}
        for f in filas:
            k = f.get(clave) or inf.SIN_ASIGNAR
            if traducir:
                k = _ingles_estado(k)
            d = salida.setdefault(k, {"n": 0, "pax": 0})
            d["n"] += 1
            d["pax"] += 1
        return salida

    por_amenidad = cuenta("amenidad")
    por_area = cuenta("area_responsable")
    por_estado = cuenta("estado", traducir=True)
    filas_a = inf.top_y_otros(por_amenidad, 8, "amenidad")
    filas_ar = [{"area": k, "n": v["n"]} for k, v in
                sorted(por_area.items(), key=lambda x: -x[1]["n"])][:6]
    filas_e = [{"estado": k, "n": v["n"]} for k, v in
               sorted(por_estado.items(), key=lambda x: -x[1]["n"])]
    a_mano = len([f for f in filas if f.get("editado_a_mano")])

    return {
        "titulo": "Guest Requirements", "subtitulo": f"{LODGE} · amenities & requests",
        "desde": desde, "hasta": hasta,
        "kpis": [
            ("Requirements", len(filas), None, "", None),
            ("Types", len(por_amenidad), None, "", None),
            ("Departments", len(por_area), None, "", None),
            ("By hand", a_mano, None, "", "reception added"),
        ],
        "neutrales": ("Requirements", "Types", "Departments", "By hand"),
        "bloques": [
            _bloque("izq", "By requirement",
                    [("amenidad", "Requirement", "i", None),
                     ("n", "Count", "d", "#,##0"), ("bar", "", "i", None)],
                    [dict(f, bar=f["n"]) for f in filas_a],
                    [40 * inf.mm, 16 * inf.mm, 33 * inf.mm],
                    total={"amenidad": inf.TOTAL, "n": sum(f["n"] for f in filas_a)},
                    barra_en="bar",
                    tope=max([f["n"] for f in filas_a] or [1]), grafico="n",
                    nota="What guests asked for, or what their reservation requires."),
            _bloque("der", "By department",
                    [("area", "Department", "i", None), ("n", "Count", "d", "#,##0")],
                    filas_ar, [58 * inf.mm, 31 * inf.mm],
                    total={"area": inf.TOTAL, "n": sum(f["n"] for f in filas_ar)},
                    nota="Who has to act on each requirement."),
            _bloque("der", "By status",
                    [("estado", "Status", "i", None), ("n", "Count", "d", "#,##0")],
                    filas_e, [58 * inf.mm, 31 * inf.mm],
                    total={"estado": inf.TOTAL, "n": sum(f["n"] for f in filas_e)}),
        ],
        "tendencia": _tendencia(
            conn, desde, hasta,
            consulta=lambda c, ini, fin: {
                r["f"]: r["v"] for r in c.execute(
                    """SELECT fecha f, COUNT(*) v FROM amenidad_tarea
                       WHERE fecha BETWEEN ? AND ? GROUP BY fecha""", (ini, fin))},
            titulo_dia="Requirements by day", titulo_semana="Requirements by week"),
        "lectura": _lectura_amenidades(filas, por_amenidad, por_area),
        "datos": {
            "titulo": "One row per requirement",
            "columnas": [("fecha", "Date", "i", None), ("hab", "Room", "i", None),
                         ("nombre", "Guest", "i", None),
                         ("amenidad", "Requirement", "i", None),
                         ("detalle", "Detail", "i", None),
                         ("area", "Department", "i", None),
                         ("estado", "Status", "i", None)],
            "filas": [{"fecha": f.get("fecha") or "", "hab": f.get("room_no"),
                       "nombre": f.get("nombre_principal"),
                       "amenidad": f.get("amenidad"), "detalle": f.get("detalle") or "",
                       "area": f.get("area_responsable"),
                       "estado": _ingles_estado(f.get("estado"))} for f in filas],
        },
        "definiciones": [
            ("Requirement", "Anything the guest needs that is not the standard service: "
                            "allergies, celebrations, special requests."),
            ("Edited by hand", "Added or corrected by reception. It is protected from "
                               "being overwritten by the next import."),
        ],
    }


def _lectura_amenidades(filas, por_amenidad, por_area):
    if not filas:
        return "No guest requirements were recorded in this period."
    top = max(por_amenidad.items(), key=lambda x: x[1]["n"])[0]
    area = max(por_area.items(), key=lambda x: x[1]["n"])[0]
    return (f"<b>{inf.plural(len(filas), 'requirement', 'requirements')}</b> were "
            f"recorded across <b>{len(por_amenidad)}</b> types. The most frequent was "
            f"<b>{top}</b>, and <b>{area}</b> is the department carrying the most.")


# ---------------------------------------------------------------------------
# Reservas
# ---------------------------------------------------------------------------

def reservas(conn, desde, hasta):
    m = inf.metricas(conn, desde, hasta)
    ant = inf.metricas(conn, *inf.periodo_anterior(desde, hasta))
    entra = m["entraron"]

    def con_pax(rs):
        return [dict(r, pax=(r["adl"] or 0) + (r["chl"] or 0)) for r in rs]

    pax_total = sum((r["adl"] or 0) + (r["chl"] or 0) for r in entra)
    noches = [
        ((inf.a_fecha(r["dep_date"]) - inf.a_fecha(r["arr_date"])).days)
        for r in entra if inf.a_fecha(r["arr_date"]) and inf.a_fecha(r["dep_date"])]
    estancia = round(sum(noches) / len(noches), 1) if noches else 0

    por_regimen = inf.agrupar(con_pax([r for r in entra if r.get("regimen")]), "regimen")
    filas_r = [{"reg": _REGIMEN_EN.get(k, k), "n": v["n"], "pax": v["pax"]}
               for k, v in sorted(por_regimen.items(), key=lambda x: -x[1]["pax"])][:6]
    por_punto = inf.agrupar(con_pax(entra), "punto_entrada")
    filas_p = inf.top_y_otros(por_punto, 5, "punto")
    por_noches = {}
    for n in noches:
        d = por_noches.setdefault(f"{n} {'night' if n == 1 else 'nights'}",
                                  {"n": 0, "pax": 0})
        d["n"] += 1
        d["pax"] += 1
    filas_n = [{"est": k, "n": v["n"]} for k, v in
               sorted(por_noches.items(), key=lambda x: -x[1]["n"])][:6]

    return {
        "titulo": "Reservations Report", "subtitulo": f"{LODGE} · front desk",
        "desde": desde, "hasta": hasta,
        "kpis": [
            ("Arrivals", len(entra), len(ant["entraron"]), "", None),
            ("Pax in", pax_total, None, "", None),
            ("Average stay", estancia, None, "nights", None),
            ("Pax-nights", m["pax_noche"], ant["pax_noche"], "", None),
            ("Occupancy", m["ocupacion"], ant["ocupacion"], "%", None),
            ("Complimentary", m["cortesias"], ant["cortesias"], "",
             f"{m['cortesias_pax']} pax"),
        ],
        "neutrales": ("Complimentary",),
        "bloques": [
            _bloque("izq", "Meal plan",
                    [("reg", "Plan", "i", None), ("n", "Rsv.", "d", "#,##0"),
                     ("pax", "Pax", "d", "#,##0"), ("bar", "", "i", None)],
                    *_barra_y_anchos(filas_r), total=_totales(filas_r, "reg"),
                    barra_en="bar", tope=max([f["pax"] for f in filas_r] or [1]),
                    grafico="pax", nota="What each reservation has paid for."),
            _bloque("der", "Arrival point",
                    [("punto", "Point", "i", None), ("n", "Rsv.", "d", "#,##0"),
                     ("pax", "Pax", "d", "#,##0"), ("bar", "", "i", None)],
                    *_barra_y_anchos(filas_p), total=_totales(filas_p, "punto"),
                    barra_en="bar", tope=_tope(por_punto)),
            _bloque("der", "Length of stay",
                    [("est", "Stay", "i", None), ("n", "Rsv.", "d", "#,##0")],
                    filas_n, [58 * inf.mm, 31 * inf.mm],
                    total={"est": inf.TOTAL, "n": sum(f["n"] for f in filas_n)}),
        ],
        "tendencia": _tendencia(
            conn, desde, hasta,
            consulta=_por_dia_de_reserva("arr_date", "COUNT(*)"),
            titulo_dia="Arrivals by day", titulo_semana="Arrivals by week"),
        "lectura": _lectura_reservas(m, ant, entra, pax_total, estancia),
        "datos": {
            "titulo": "One row per arriving reservation",
            "columnas": [("conf", "Reservation", "i", None), ("hab", "Room", "i", None),
                         ("nombre", "Guest", "i", None), ("entra", "In", "i", None),
                         ("sale", "Out", "i", None), ("pax", "Pax", "d", "#,##0"),
                         ("punto", "Arrival point", "i", None),
                         ("reg", "Meal plan", "i", None),
                         ("cpl", "Complimentary", "i", None)],
            "filas": [{"conf": r["conf_no"], "hab": r["room_no"],
                       "nombre": r.get("nombre_principal"), "entra": r["arr_date"],
                       "sale": r["dep_date"],
                       "pax": (r["adl"] or 0) + (r["chl"] or 0),
                       "punto": r["punto_entrada"] or inf.SIN_ASIGNAR,
                       "reg": _REGIMEN_EN.get(r.get("regimen"), r.get("regimen") or ""),
                       "cpl": "yes" if r.get("cortesia") else ""} for r in entra],
        },
        "definiciones": [
            ("Average stay", "Nights between arrival and departure, averaged over the "
                             "reservations arriving in the period."),
            ("Complimentary", "A reservation whose note says CPL, complementary or "
                              "cortesía. Counted as HOW MANY, never as an amount."),
        ],
    }


def _lectura_reservas(m, ant, entra, pax_total, estancia):
    var = inf._delta(len(entra), len(ant["entraron"]))[0]
    frases = [
        f"<b>{inf.plural(len(entra), 'reservation', 'reservations')}</b> arrived with "
        f"<b>{pax_total} pax</b> ({var} against the previous period), for an average "
        f"stay of <b>{estancia} nights</b>.",
        f"Occupancy averaged <b>{m['ocupacion']}%</b> over the period."]
    if m["cortesias"]:
        frases.append(f"<b>{inf.plural(m['cortesias'], 'arrival was', 'arrivals were')}</b> "
                      f"complimentary ({m['cortesias_pax']} pax).")
    return " ".join(frases)


# ---------------------------------------------------------------------------
# Resumen de operación de un día
# ---------------------------------------------------------------------------

def resumen(conn, desde, hasta):
    """El día completo: quién entra, quién sale, qué tours y qué comidas."""
    spec = analitica(conn, desde, hasta)
    spec["titulo"] = "Daily Operations Summary"
    spec["subtitulo"] = f"{LODGE} · operations"
    puntos = _puntos(conn, desde, hasta)
    m = inf.metricas(conn, desde, hasta)
    spec["kpis"] = [
        ("Pax in house", m["pax_noche"], None, "", None),
        ("Occupancy", m["ocupacion"], None, "%", None),
        ("Arrivals", len(m["entraron"]), None, "", None),
        ("Departures", len(m["salieron"]), None, "", None),
        ("Tour departures", m["salidas"], None, "", None),
        ("Tour pax", m["pax_tours"], None, "", None),
        ("Spa bookings", m["spa_activas"], None, "", None),
    ]
    spec["neutrales"] = tuple(k[0] for k in spec["kpis"])
    return spec


# ---------------------------------------------------------------------------
# La puerta de entrada
# ---------------------------------------------------------------------------

AREAS = {
    "analitica": analitica,
    "agenda": agenda,
    "transporte": transporte,
    "restaurantes": restaurantes,
    "sinac": sinac,
    "amenidades": amenidades,
    "reservas": reservas,
    "resumen": resumen,
}


def construir(area, conn, desde, hasta, formato="pdf"):
    """El informe de un área, en el formato pedido. Un archivo, una definición."""
    constructor = AREAS.get(area)
    if constructor is None:
        raise ValueError(f"Área de informe desconocida: {area}")
    spec = constructor(conn, desde, hasta)
    return inf.libro(spec) if formato == "xlsx" else inf.documento(spec)
