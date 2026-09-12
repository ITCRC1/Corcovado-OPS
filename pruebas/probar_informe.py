"""El informe de operacion: que quepa en UNA hoja y que diga lo mismo que la pantalla.

Lo que se descargaba antes era una tabla plana de tres columnas, la misma para todo, sin
totales ni comparacion, y con el spa fuera aunque la pantalla si lo mostraba. Este
informe entra en una hoja a proposito.

Las dos cosas que estas pruebas fijan:

  1. UNA pagina. Es el requisito, y es facil de romper sin darse cuenta: basta con que un
     mes traiga un guia mas para que se desborde a la segunda hoja.
  2. El MISMO formato por dia y por mes. Lo unico que cambia es el bloque de tendencia y
     contra que se compara; todo lo demas tiene que verse igual.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun
from comun import cargar, reserva

import informe

HOY = datetime.date.today()


def ddmmyy(d):
    return f"{d.day:02d}-{d.month:02d}-{str(d.year)[2:]}"


def _sembrar(conn, dias=40, reservas=30, cortesias=4):
    """Un periodo con tours repartidos, para que el informe tenga que resumir."""
    import random
    random.seed(5)
    tours = ["PNC", "SIRENA", "SNORKEL", "MANGLAR", "NW", "BALLENAS", "CABALGATA"]
    inicio = HOY - datetime.timedelta(days=dias)
    lote = []
    for i in range(reservas):
        llega = inicio + datetime.timedelta(days=random.randint(0, dias - 4))
        noches = random.choice([2, 3, 4])
        lote.append(reserva(
            f"80{i:04d}", f"{(i % 20) + 1:02d}", ddmmyy(llega),
            ddmmyy(llega + datetime.timedelta(days=noches)),
            estado="EN CASA", adl=random.choice([1, 2, 2, 3]),
            punto_entrada=random.choice(["Sierpe", "Drake"]),
            punto_salida=random.choice(["Sierpe", "Drake"]),
            # La cortesia NO se pone a mano: se escribe en el texto y la detecta el
            # importador, que es como llega de Opera. Poniendola directa, el importador
            # la recalcularia del texto vacio y la prueba mediria otra cosa.
            texto_completo=("PAQUETE 3D/2N+ FULLBOARD CPL EN HOSPEDAJE"
                            if i < cortesias else ""),
            operacion=[{"dia": (llega + datetime.timedelta(days=d)).day,
                        "tour": random.choice(tours)}
                       for d in range(1, min(noches, 3))]))
    cargar(lote)
    botes = [r["nombre"] for r in conn.execute("SELECT nombre FROM bote")][:4]
    guias = [r["nombre"] for r in conn.execute("SELECT nombre FROM guia")][:6]
    for f in conn.execute("SELECT id FROM tour_asignado").fetchall():
        conn.execute("UPDATE tour_asignado SET bote_nombre=?, guia_nombre=? WHERE id=?",
                     (random.choice(botes), random.choice(guias), f["id"]))
    conn.commit()


def _paginas(buf):
    import pdfplumber
    buf.seek(0)
    with pdfplumber.open(buf) as pdf:
        return len(pdf.pages), (pdf.pages[0].extract_text() or "")


# ---------------------------------------------------------------------------
# Que quepa
# ---------------------------------------------------------------------------

def el_informe_de_un_mes_cabe_en_una_hoja(c):
    conn = comun.base_limpia()
    _sembrar(conn)
    ini = (HOY.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    fin = HOY.replace(day=1) - datetime.timedelta(days=1)
    n, texto = _paginas(informe.una_pagina(conn, ini.isoformat(), fin.isoformat()))
    c.igual(n, 1, "el informe de un mes ocupa UNA hoja")
    c.cierto("Informe de operación" in texto, "y lleva su titulo")
    conn.close()


def el_informe_de_un_dia_cabe_en_una_hoja(c):
    conn = comun.base_limpia()
    _sembrar(conn)
    n, _ = _paginas(informe.una_pagina(conn, HOY.isoformat(), HOY.isoformat()))
    c.igual(n, 1, "el de un solo dia tambien")
    conn.close()


def un_periodo_sin_nada_no_revienta(c):
    """Un dia sin movimiento tiene que dar un informe que diga que no hubo, no un error
    ni una hoja rota: recepcion lo va a pedir en temporada baja."""
    conn = comun.base_limpia()
    lejos = (HOY + datetime.timedelta(days=300)).isoformat()
    n, texto = _paginas(informe.una_pagina(conn, lejos, lejos))
    c.igual(n, 1, "sigue siendo una hoja")
    c.cierto("Informe de operación" in texto, "y sigue siendo un informe")
    conn.close()


def el_formato_es_el_mismo_por_dia_y_por_mes(c):
    """Es el pedido: mismo formato, cambie el periodo. Se compara que esten los MISMOS
    bloques, que es lo que hace que se puedan leer uno al lado del otro."""
    conn = comun.base_limpia()
    _sembrar(conn)
    _, mes = _paginas(informe.una_pagina(
        conn, (HOY - datetime.timedelta(days=27)).isoformat(), HOY.isoformat()))
    _, dia = _paginas(informe.una_pagina(conn, HOY.isoformat(), HOY.isoformat()))
    for bloque in ("TOURS POR TIPO", "GUÍAS", "BOTES", "PUNTOS DE EMBARQUE", "SPA",
                   "LECTURA DEL PERIODO", "PAX-NOCHE", "CORTESÍAS"):
        c.cierto(bloque in mes, f"«{bloque}» esta en el informe del mes")
        c.cierto(bloque in dia, f"«{bloque}» esta tambien en el del dia")
    conn.close()


# ---------------------------------------------------------------------------
# Lo que cambia entre un dia y un mes
# ---------------------------------------------------------------------------

def un_mes_se_compara_con_el_mes_anterior(c):
    """Comparar un mes contra «los 30 dias de antes» corre el corte y mezcla dos meses.
    Un mes de calendario se compara con el mes de calendario anterior."""
    c.igual(informe.periodo_anterior("2026-03-01", "2026-03-31"),
            ("2026-02-01", "2026-02-28"), "marzo se compara con febrero entero")
    c.igual(informe.periodo_anterior("2026-01-01", "2026-01-31"),
            ("2025-12-01", "2025-12-31"), "enero, con diciembre del ano anterior")
    # Un rango que NO es un mes completo usa la regla de siempre.
    c.igual(informe.periodo_anterior("2026-03-05", "2026-03-11"),
            ("2026-02-26", "2026-03-04"), "una semana, con la semana de antes")
    c.igual(informe.periodo_anterior("2026-03-10", "2026-03-10"),
            ("2026-03-09", "2026-03-09"), "un dia, con el dia anterior")


def el_mes_se_llama_por_su_nombre(c):
    c.igual(informe.titulo_del_periodo("2026-03-01", "2026-03-31"), "Marzo 2026",
            "un mes completo se dice por su nombre")
    c.igual(informe.titulo_del_periodo("2026-03-10", "2026-03-10"),
            "10 de marzo de 2026", "un dia, con su fecha")
    c.cierto("—" in informe.titulo_del_periodo("2026-03-05", "2026-03-20"),
             "un rango cualquiera, de fecha a fecha")


def la_tendencia_se_adapta_al_largo_del_periodo(c):
    """«Pax por semana» no significa nada en un informe de un dia."""
    conn = comun.base_limpia()
    _sembrar(conn)
    _, _, _, titulo_mes = informe.serie_de_tendencia(
        conn, (HOY - datetime.timedelta(days=29)).isoformat(), HOY.isoformat())
    c.cierto("semana" in titulo_mes, "un mes se grafica por semana")

    valores, _, dentro, titulo_dia = informe.serie_de_tendencia(
        conn, HOY.isoformat(), HOY.isoformat())
    c.cierto("día" in titulo_dia or "días" in titulo_dia, "un dia se grafica por dia")
    c.cierto(len(valores) >= informe.MINIMO_BARRAS,
             "y se completa hacia atras para tener con que comparar")
    c.igual(dentro.count(True), 1, "solo la barra del dia pedido es del periodo")
    c.igual(dentro[-1], True, "y es la ultima")
    conn.close()


# ---------------------------------------------------------------------------
# Que los numeros sean los de la pantalla
# ---------------------------------------------------------------------------

def las_cortesias_se_cuentan_no_se_valoran(c):
    """Se pidio la CANTIDAD, no el monto. Sale de la nota de la reserva."""
    conn = comun.base_limpia()
    _sembrar(conn, cortesias=4)
    m = informe.metricas(conn, (HOY - datetime.timedelta(days=40)).isoformat(),
                         HOY.isoformat())
    c.igual(m["cortesias"], 4, "cuenta las reservas marcadas como cortesia")
    c.cierto(m["cortesias_pax"] >= 4, "y su gente")
    conn.close()


def el_spa_si_entra_en_el_informe(c):
    """El reporte viejo dejaba el spa fuera aunque la pantalla lo mostraba."""
    conn = comun.base_limpia()
    _sembrar(conn)
    servicio = conn.execute("SELECT codigo FROM spa_servicio LIMIT 1").fetchone()
    terapeuta = conn.execute("SELECT nombre FROM spa_terapeuta LIMIT 1").fetchone()
    conf = conn.execute("SELECT conf_no FROM reserva LIMIT 1").fetchone()["conf_no"]
    for estado in ("HECHA", "CONFIRMADA", "SOLICITADA"):
        conn.execute(
            """INSERT INTO spa_cita (conf_no, fecha, servicio_codigo, minutos,
                                     terapeuta, estado, origen)
               VALUES (?,?,?,?,?,?,'HUESPED')""",
            (conf, HOY.isoformat(), servicio["codigo"], 60,
             terapeuta["nombre"] if terapeuta else None, estado))
    conn.commit()
    m = informe.metricas(conn, HOY.isoformat(), HOY.isoformat())
    c.igual(len(m["spa"]), 3, "el informe ve las tres citas")
    c.igual(m["spa_activas"], 2,
            "pero solo cuenta las hechas y confirmadas: una solicitud no es trabajo hecho")
    _, texto = _paginas(informe.una_pagina(conn, HOY.isoformat(), HOY.isoformat()))
    c.cierto("SPA" in texto, "y el spa aparece en la hoja")
    conn.close()


def la_ocupacion_usa_el_mismo_total_que_la_pantalla(c):
    """Si el informe contara las habitaciones de otra forma, diria un porcentaje distinto
    al de la pantalla de ocupacion y nadie sabria cual creer."""
    conn = comun.base_limpia()
    llega = HOY - datetime.timedelta(days=1)
    cargar([reserva(f"90{i}", f"{i:02d}", ddmmyy(llega),
                    ddmmyy(HOY + datetime.timedelta(days=2)), estado="EN CASA", adl=2)
            for i in range(1, 11)])
    m = informe.metricas(conn, HOY.isoformat(), HOY.isoformat(), habitaciones=20)
    c.igual(m["ocupacion"], 50, "10 habitaciones de 20 es 50%")
    c.igual(m["pax_noche"], 20, "y 20 pax durmiendo")
    conn.close()


def el_libro_de_excel_trae_las_hojas_y_los_numeros(c):
    conn = comun.base_limpia()
    _sembrar(conn)
    import openpyxl
    buf = informe.libro(conn, (HOY - datetime.timedelta(days=27)).isoformat(),
                        HOY.isoformat())
    wb = openpyxl.load_workbook(buf)
    for hoja in ("Resumen", "Tours", "Guías", "Botes", "Spa", "Datos", "Léeme"):
        c.cierto(hoja in wb.sheetnames, f"el libro trae la hoja «{hoja}»")
    ws = wb["Datos"]
    c.cierto("Salidas" in list(ws.tables),
             "la hoja de datos es una TABLA de Excel, para poder pivotear")
    c.cierto(ws.freeze_panes is not None, "con el encabezado fijo")
    fila = [c2.value for c2 in ws[5]]
    c.cierto(any(isinstance(v, int) for v in fila),
             "y los numeros son numeros, no texto")
    conn.close()


PRUEBAS = [
    el_informe_de_un_mes_cabe_en_una_hoja,
    el_informe_de_un_dia_cabe_en_una_hoja,
    un_periodo_sin_nada_no_revienta,
    el_formato_es_el_mismo_por_dia_y_por_mes,
    un_mes_se_compara_con_el_mes_anterior,
    el_mes_se_llama_por_su_nombre,
    la_tendencia_se_adapta_al_largo_del_periodo,
    las_cortesias_se_cuentan_no_se_valoran,
    el_spa_si_entra_en_el_informe,
    la_ocupacion_usa_el_mismo_total_que_la_pantalla,
    el_libro_de_excel_trae_las_hojas_y_los_numeros,
]


if __name__ == "__main__":
    sys.exit(comun.correr("informe de operación", PRUEBAS))
