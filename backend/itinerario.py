"""
Genera el PDF de bienvenida que recibe el huésped, replicando el diseño oficial
del lodge: fondo fotográfico, tarjeta blanca con ornamentos, tabla del itinerario
y la página de horarios.

El fondo y la página de horarios se toman del documento original del hotel para
que el resultado sea idéntico al que se entrega hoy a mano.
"""
import io
import os
import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.pdfgen import canvas as canvas_mod
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import catalogo_itinerario as cat

# --- Colores exactos medidos del documento original ---
VERDE = colors.Color(0.1216, 0.2275, 0.1804)   # #1F3A2E
BLANCO = colors.white

ANCHO, ALTO = letter  # 612 x 792

# --- Geometría medida del original (en puntos, origen arriba-izquierda) ---
TABLA_X = 27
TABLA_ANCHO_COLS = [116, 97, 150, 197]         # Day, Activity, Schedule, Details
TABLA_Y_ENCABEZADO = 139
ALTO_ENCABEZADO = 32
TITULO_Y = 66
SUBTITULO_Y1, SUBTITULO_Y2 = 63, 76

_base = os.environ.get("HOTEL_RESOURCE_DIR") or os.path.join(os.path.dirname(__file__), "..")
ASSETS = os.path.join(_base, "frontend", "assets")
if not os.path.isdir(ASSETS):
    ASSETS = os.path.join(os.path.dirname(__file__), "..", "frontend", "assets")
DIR_ITIN = os.path.join(ASSETS, "itinerario")
DIR_FUENTES = os.path.join(ASSETS, "fonts")

MESES_EN = ["January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"]

_fuentes_ok = False


_fuentes_por_idioma = set()


def _registrar_fuentes(idioma="en"):
    """Registra las tipografías del idioma. Se usan alternativas libres muy parecidas
    a las del diseño original (The Seasons -> Playfair, Agrandir Narrow -> Archivo
    Narrow), porque las originales vienen incrustadas solo como subconjunto de letras.
    Para el ruso se usan versiones con alfabeto cirílico."""
    global _fuentes_ok
    import traducciones as _tr
    sufijo = "Cyr" if idioma in _tr.IDIOMAS_CIRILICOS else "Lat"
    if sufijo in _fuentes_por_idioma:
        _fuentes_ok = True
        return True
    archivos = _tr.fuentes_para(idioma)
    try:
        pdfmetrics.registerFont(TTFont(f"Titulo{sufijo}", os.path.join(DIR_FUENTES, archivos["titulo"])))
        pdfmetrics.registerFont(TTFont(f"Encabezado{sufijo}", os.path.join(DIR_FUENTES, archivos["encabezado"])))
        pdfmetrics.registerFont(TTFont(f"Cuerpo{sufijo}", os.path.join(DIR_FUENTES, archivos["cuerpo"])))
        pdfmetrics.registerFont(TTFont(f"CuerpoBold{sufijo}", os.path.join(DIR_FUENTES, archivos["cuerpo_bold"])))
        pdfmetrics.registerFont(TTFont(f"Italica{sufijo}", os.path.join(DIR_FUENTES, archivos["italica"])))
        _fuentes_por_idioma.add(sufijo)
        _fuentes_ok = True
    except Exception:
        _fuentes_ok = False
    return _fuentes_ok


def _f(nombre, respaldo, sufijo="Lat"):
    return f"{nombre}{sufijo}" if _fuentes_ok else respaldo


def _fecha_larga(iso):
    try:
        d = datetime.date.fromisoformat(iso)
        return f"{MESES_EN[d.month - 1]} {d.day:02d}"
    except (ValueError, TypeError):
        return iso or ""


def nombre_bienvenida(nombre_principal, huespedes):
    """'Welcome ___' con los nombres de pila de todos los huéspedes: 'Mark & Honi'."""
    import unicodedata
    nombres, vistos = [], set()

    def sin_acentos(s):
        base = unicodedata.normalize("NFD", s)
        return "".join(ch for ch in base if unicodedata.category(ch) != "Mn").lower()

    def agregar(n):
        if not n:
            return
        limpio = n.replace("–", " ").replace("-", " ").strip()
        partes = [p for p in limpio.split() if p.isalpha() and len(p) > 1]
        if not partes:
            return
        nombre = partes[0].capitalize()
        # Se comparan sin acentos para no repetir variantes del mismo nombre
        # (ej. "Soeren" y "Sören" son la misma persona escrita distinto).
        clave = sin_acentos(nombre).replace("oe", "o").replace("ae", "a").replace("ue", "u")
        if clave not in vistos:
            vistos.add(clave)
            nombres.append(nombre)

    if nombre_principal and "," in nombre_principal:
        agregar(nombre_principal.split(",", 1)[1])
    elif nombre_principal:
        agregar(nombre_principal)
    for h in huespedes or []:
        agregar(h)

    if not nombres:
        return "Guest"
    if len(nombres) == 1:
        return nombres[0]
    if len(nombres) == 2:
        return " & ".join(nombres)
    return ", ".join(nombres[:-1]) + " & " + nombres[-1]


def calcular_logistica_salida(hora_vuelo):
    """Horarios del día de salida por Drake, calculados desde la hora del vuelo:
      · Bote: 2 horas antes del vuelo
      · Equipaje listo: 3 horas antes
      · Check-out: 20 minutos antes del bote
    Excepción: si el equipaje quedara antes de las 5:45 a.m., se deja a las 5:45 a.m.,
    porque más temprano no es razonable para el huésped."""
    if not hora_vuelo:
        return None
    try:
        texto = hora_vuelo.lower().replace(".", "").replace(" ", "")
        es_pm = "pm" in texto
        es_am = "am" in texto
        reloj = texto.replace("pm", "").replace("am", "")
        h, m = [int(x) for x in reloj.split(":")]
        if es_pm and h < 12:
            h += 12
        if es_am and h == 12:
            h = 0
    except (ValueError, AttributeError):
        return None

    vuelo = datetime.datetime(2000, 1, 1, h, m)
    bote = vuelo - datetime.timedelta(hours=2)
    equipaje = vuelo - datetime.timedelta(hours=3)

    # Excepción para vuelos muy tempranos: no se recoge equipaje antes de las 5:45 a.m.
    # ni sale el bote antes de las 6:00 a.m., aunque la resta diera más temprano.
    # (Ej. vuelo 7:30 a.m.: la regla daría equipaje 4:30 y bote 5:30, que no es razonable.)
    min_equipaje = datetime.datetime(2000, 1, 1, 5, 45)
    min_bote = datetime.datetime(2000, 1, 1, 6, 0)
    excepcion = equipaje < min_equipaje or bote < min_bote
    equipaje = max(equipaje, min_equipaje)
    bote = max(bote, min_bote)

    # El check-out va entre la recogida de equipaje y la salida del bote
    checkout = max(bote - datetime.timedelta(minutes=20),
                   equipaje + datetime.timedelta(minutes=5))

    def fmt(t):
        h12 = t.hour % 12 or 12
        return f"{h12}:{t.minute:02d} {'a' if t.hour < 12 else 'p'}.m."

    return {"equipaje": fmt(equipaje), "checkout": fmt(checkout), "bote": fmt(bote),
            "excepcion_vuelo_temprano": excepcion}


def construir_filas(datos):
    filas = []
    llegada = cat.texto_llegada(datos.get("punto_entrada"), datos.get("vuelo_entrada"),
                                datos.get("hora_vuelo_entrada"))
    filas.append((_fecha_larga(datos["arr_date_iso"]), llegada))

    for t in datos.get("tours", []):
        externo = (t.get("guia_nombre") or "").upper() == "EXTERNO"
        info = cat.texto_tour(t["tour_codigo"], guia_es_externo=externo)
        filas.append((_fecha_larga(t["fecha"]), info))

    logistica = datos.get("logistica_salida")
    if logistica is None and (datos.get("punto_salida") or "").lower() == "drake":
        logistica = calcular_logistica_salida(datos.get("hora_vuelo_salida"))
    salida = cat.texto_salida(datos.get("punto_salida"), datos.get("vuelo_salida"),
                              datos.get("hora_vuelo_salida"), logistica)
    filas.append((_fecha_larga(datos["dep_date_iso"]), salida))
    return filas


def generar_pdf(datos, idioma="en"):
    import traducciones as tr
    _registrar_fuentes(idioma)
    sufijo = "Cyr" if idioma in tr.IDIOMAS_CIRILICOS else "Lat"
    buf = io.BytesIO()
    c = canvas_mod.Canvas(buf, pagesize=letter)

    # --- Página 1: fondo con el diseño original ---
    base = os.path.join(DIR_ITIN, "pagina1_base.jpg")
    if os.path.exists(base):
        c.drawImage(base, 0, 0, width=ANCHO, height=ALTO, mask="auto")

    # Título "Welcome ___"
    c.setFillColor(colors.black)
    titulo = f"{tr.t('bienvenida', idioma)} {datos.get('nombre_bienvenida','')}"
    tam = 19.1
    fuente = _f("Titulo", "Times-Bold", sufijo)
    # Si el nombre es largo, se reduce para que no se salga de la tarjeta
    while tam > 12 and pdfmetrics.stringWidth(titulo, fuente, tam) > 430:
        tam -= 0.5
    c.setFont(fuente, tam)
    c.drawCentredString(ANCHO / 2, ALTO - TITULO_Y - tam * 0.75, titulo)

    # En inglés el subtítulo ya viene impreso en la plantilla. En los demás idiomas
    # se tapa con blanco y se escribe el texto traducido.
    if idioma != "en":
        c.setFillColor(colors.white)
        c.rect(66, ALTO - 134, ANCHO - 132, 48, stroke=0, fill=1)
        c.setFillColor(colors.black)
        c.setFont(_f("Italica", "Times-Italic", sufijo), 10.5)
        c.drawCentredString(ANCHO / 2, ALTO - 104, tr.t("sub1", idioma))
        sub2 = tr.t("sub2", idioma)
        tam2 = 10.5
        while tam2 > 7 and pdfmetrics.stringWidth(sub2, _f("Italica", "Times-Italic", sufijo), tam2) > ANCHO - 150:
            tam2 -= 0.5
        c.setFont(_f("Italica", "Times-Italic", sufijo), tam2)
        c.drawCentredString(ANCHO / 2, ALTO - 118, sub2)

    # --- Tabla del itinerario ---
    est_dia = ParagraphStyle("dia", fontName=_f("Encabezado", "Times-Roman", sufijo), fontSize=13,
                             textColor=BLANCO, alignment=TA_CENTER, leading=16)
    est_th = ParagraphStyle("th", fontName=_f("Encabezado", "Times-Roman", sufijo), fontSize=13,
                            textColor=BLANCO, alignment=TA_CENTER, leading=16)
    est_act = ParagraphStyle("act", fontName=_f("Cuerpo", "Helvetica", sufijo), fontSize=11,
                             textColor=VERDE, alignment=TA_CENTER, leading=13)
    est_cel = ParagraphStyle("cel", fontName=_f("Cuerpo", "Helvetica", sufijo), fontSize=10.5,
                             textColor=VERDE, alignment=TA_CENTER, leading=12.5)

    data = [[Paragraph(tr.t(k, idioma), est_th)
             for k in ("dia", "actividad", "horario", "detalles")]]

    # Si vienen filas ya armadas (por ejemplo editadas por recepción) se usan tal cual;
    # si no, se construyen desde los datos de la reserva.
    if datos.get("_filas_listas") is not None:
        filas_tabla = [(_fecha_en_idioma(f.get("dia", ""), idioma), {
            "nombre": f.get("actividad", ""), "duracion": f.get("duracion", ""),
            "horario": f.get("horario", ""), "detalles": f.get("detalles", ""),
        }) for f in datos["_filas_listas"]]
    else:
        filas_tabla = [(_fecha_en_idioma(fe, idioma), inf) for fe, inf in construir_filas(datos)]

    for fecha, info in filas_tabla:
        nombre_tr = tr.traducir_actividad(info["nombre"], idioma)
        nombre = nombre_tr.replace("\n", "<br/>")
        if info.get("duracion"):
            dur = tr.traducir_texto(info["duracion"], idioma)
            nombre += f'<br/><font size="8">{dur}</font>'
        horario = tr.formatear_horas(tr.traducir_texto(info["horario"], idioma), idioma)
        detalles = tr.formatear_horas(tr.traducir_texto(info["detalles"], idioma), idioma)
        data.append([
            Paragraph(fecha, est_dia),
            Paragraph(nombre, est_act),
            Paragraph(horario.replace("\n", "<br/>"), est_cel),
            Paragraph(detalles.replace("\n", "<br/>"), est_cel),
        ])

    tabla = Table(data, colWidths=TABLA_ANCHO_COLS)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VERDE),      # encabezado completo en verde
        ("BACKGROUND", (0, 1), (0, -1), VERDE),      # columna de fecha en verde
        ("BACKGROUND", (1, 1), (-1, -1), BLANCO),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.85, 0.82, 0.76)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    ancho_tabla, alto_tabla = tabla.wrapOn(c, sum(TABLA_ANCHO_COLS), ALTO)
    tabla.drawOn(c, TABLA_X, ALTO - TABLA_Y_ENCABEZADO - alto_tabla)

    # El lema del pie también viene impreso en inglés en el diseño base
    if idioma != "en":
        c.setFillColor(colors.white)
        c.rect(120, ALTO - 690, ANCHO - 240, 48, stroke=0, fill=1)
        c.setFillColor(colors.Color(0.114, 0.2, 0.165))
        lema = tr.t("lema", idioma)
        tam_l = 15
        fuente_l = _f("Titulo", "Times-Bold", sufijo)
        # Se parte en dos líneas si no cabe, como en el original
        if pdfmetrics.stringWidth(lema, fuente_l, tam_l) > ANCHO - 250:
            palabras = lema.split()
            mitad = len(palabras) // 2
            for i in range(mitad, len(palabras)):
                if pdfmetrics.stringWidth(" ".join(palabras[:i]), fuente_l, tam_l) > (ANCHO - 250) / 2:
                    mitad = i
                    break
            lineas = [" ".join(palabras[:mitad]), " ".join(palabras[mitad:])]
        else:
            lineas = [lema]
        c.setFont(fuente_l, tam_l)
        yl = ALTO - 658
        for l in lineas:
            c.drawCentredString(ANCHO / 2, yl, l)
            yl -= 18

    c.showPage()

    # --- Página 2: horarios del lodge, escritos como texto para poder traducirlos ---
    base2 = os.path.join(DIR_ITIN, "pagina2_base.jpg")
    if os.path.exists(base2):
        c.drawImage(base2, 0, 0, width=ANCHO, height=ALTO, mask="auto")

    y = ALTO - 118
    c.setFillColor(colors.Color(0.114, 0.2, 0.165))
    c.setFont(_f("Titulo", "Times-Bold", sufijo), 26)
    c.drawCentredString(ANCHO / 2, y, tr.t("titulo_horarios", idioma))
    y -= 40

    # Marco del cuadro de horarios, como en el diseño original
    alto_cuadro = 300
    c.setStrokeColor(colors.Color(0.85, 0.82, 0.76))
    c.setLineWidth(0.8)
    c.rect(96, y - alto_cuadro + 26, ANCHO - 192, alto_cuadro, stroke=1, fill=0)

    c.setFillColor(colors.black)
    for nombre, horario in cat.HORARIOS_LODGE:
        if not nombre:
            y -= 11
            continue
        etiqueta = tr.traducir_servicio(nombre, idioma)
        linea = f"{etiqueta}: {tr.formatear_horas(horario, idioma)}"
        tam = 11.5
        while tam > 8 and pdfmetrics.stringWidth(linea, _f("Cuerpo", "Helvetica", sufijo), tam) > ANCHO - 220:
            tam -= 0.5
        c.setFont(_f("Cuerpo", "Helvetica", sufijo), tam)
        c.drawCentredString(ANCHO / 2, y, linea)
        y -= 19

    y -= 16
    c.setFont(_f("Cuerpo", "Helvetica", sufijo), 11)
    c.drawCentredString(ANCHO / 2, y, tr.t("snacks", idioma))
    y -= 26
    c.drawCentredString(ANCHO / 2, y, tr.t("whatsapp", idioma))
    y -= 18
    c.setFont(_f("CuerpoBold", "Helvetica-Bold", sufijo), 13)
    c.drawCentredString(ANCHO / 2, y, cat.WHATSAPP_RECEPCION)

    y -= 44
    c.setFillColor(colors.Color(0.114, 0.2, 0.165))
    c.setFont(_f("Titulo", "Times-Bold", sufijo), 11.5)
    for linea in tr.t("cierre", idioma).split("\n"):
        c.drawCentredString(ANCHO / 2, y, linea)
        y -= 15

    c.showPage()

    c.save()
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Armado del itinerario a partir de los datos de una reserva
# ---------------------------------------------------------------------------

def datos_de_reserva(conn, conf_no):
    """Reúne de la base de datos todo lo que necesita el itinerario."""
    r = conn.execute("SELECT * FROM reserva WHERE conf_no = ?", (conf_no,)).fetchone()
    if not r:
        return None
    r = dict(r)
    huespedes = [dict(h)["nombre_completo"] for h in conn.execute(
        "SELECT nombre_completo FROM huesped WHERE conf_no = ?", (conf_no,))]
    tours = [dict(t) for t in conn.execute(
        """SELECT ta.fecha, ta.tour_codigo, ta.guia_nombre
           FROM tour_asignado ta WHERE ta.conf_no = ? ORDER BY ta.fecha""", (conf_no,))]

    def a_iso(dd):
        if not dd:
            return None
        try:
            d, m, y = dd.split("-")
            return f"20{y}-{m}-{d}"
        except ValueError:
            return dd

    return {
        "nombre_bienvenida": nombre_bienvenida(r["nombre_principal"], huespedes),
        "arr_date_iso": a_iso(r["arr_date"]), "dep_date_iso": a_iso(r["dep_date"]),
        "punto_entrada": r["punto_entrada"], "punto_salida": r["punto_salida"],
        "vuelo_entrada": r.get("vuelo_entrada"), "hora_vuelo_entrada": r.get("hora_vuelo_entrada"),
        "vuelo_salida": r.get("vuelo_salida"), "hora_vuelo_salida": r.get("hora_vuelo_salida"),
        "tours": tours,
    }


def construir_itinerario(datos):
    """Devuelve las filas del itinerario como lista de diccionarios editables,
    junto con los avisos de lo que quedó incompleto."""
    filas, avisos = [], []
    for fecha, info in construir_filas(datos):
        filas.append({
            "dia": fecha,
            "actividad": info["nombre"],
            "duracion": info.get("duracion", ""),
            "horario": info["horario"],
            "detalles": info.get("detalles", ""),
            "revisar": bool(info.get("requiere_revision")),
        })
        if info.get("requiere_revision"):
            avisos.append(f"{fecha} · {info['nombre'].replace(chr(10),' ')}: falta completar el horario")

    if not datos.get("punto_entrada"):
        avisos.append("No se sabe si la llegada es por Sierpe o Drake")
    if not datos.get("punto_salida"):
        avisos.append("No se sabe si la salida es por Sierpe o Drake")
    if (datos.get("punto_entrada") or "").lower() == "drake" and not datos.get("vuelo_entrada"):
        avisos.append("Falta el número de vuelo de llegada")
    if (datos.get("punto_salida") or "").lower() == "drake" and not datos.get("vuelo_salida"):
        avisos.append("Falta el número de vuelo de salida")
    if not datos.get("tours"):
        avisos.append("La reserva no tiene tours registrados")

    return filas, avisos


def generar_pdf_de_filas(nombre_bienvenida_txt, filas, idioma="en"):
    """Genera el PDF a partir de las filas ya armadas (incluyendo ediciones manuales)."""
    datos = {"nombre_bienvenida": nombre_bienvenida_txt, "_filas_listas": filas}
    return generar_pdf(datos, idioma)


# ---------------------------------------------------------------------------
# Detección de cambios en la reserva posteriores a una edición manual
# ---------------------------------------------------------------------------

_MES_NUM = {m: i + 1 for i, m in enumerate(MESES_EN)}


def _clave_orden(fila):
    """Permite ordenar las filas por fecha aunque el día venga como 'August 14'."""
    texto = (fila.get("dia") or "").strip()
    partes = texto.replace(",", " ").split()
    mes = dia = 0
    for p in partes:
        if p in _MES_NUM:
            mes = _MES_NUM[p]
        elif p.isdigit():
            dia = int(p)
    return (mes, dia)


def _identidad(fila):
    """Identifica una fila para comparar sin depender de mayúsculas o saltos de línea."""
    dia = (fila.get("dia") or "").strip().lower()
    act = " ".join((fila.get("actividad") or "").split()).lower()
    return f"{dia}|{act}"


def detectar_faltantes(filas_guardadas, filas_actuales):
    """Devuelve las filas que la reserva tiene hoy y no están en el itinerario guardado.
    Sirve para avisar a recepción cuando el PDF trae un tour nuevo después de que ya
    editó el itinerario a mano."""
    existentes = {_identidad(f) for f in filas_guardadas}
    return [f for f in filas_actuales if _identidad(f) not in existentes]


def incorporar_faltantes(filas_guardadas, faltantes):
    """Agrega las filas nuevas al itinerario editado, en su lugar por fecha, sin
    tocar nada de lo que recepción ya había ajustado."""
    combinadas = list(filas_guardadas) + list(faltantes)
    # Se ordena por fecha, dejando al final las filas sin fecha reconocible
    con_fecha = [f for f in combinadas if _clave_orden(f) != (0, 0)]
    sin_fecha = [f for f in combinadas if _clave_orden(f) == (0, 0)]
    con_fecha.sort(key=_clave_orden)
    return con_fecha + sin_fecha


def _fecha_en_idioma(texto_dia, idioma):
    """Convierte 'August 05' (como se guarda) al formato del idioma elegido.
    Si recepción escribió algo distinto a mano, se deja tal cual."""
    if idioma == "en" or not texto_dia:
        return texto_dia
    import traducciones as tr
    partes = texto_dia.replace(",", " ").split()
    mes = dia = None
    for p in partes:
        if p in MESES_EN:
            mes = MESES_EN.index(p) + 1
        elif p.isdigit():
            dia = int(p)
    if not mes or not dia:
        return texto_dia
    nombre_mes = tr.MESES.get(idioma, tr.MESES["en"])[mes - 1]
    return tr.FORMATO_FECHA.get(idioma, tr.FORMATO_FECHA["en"]).format(dia=dia, mes=nombre_mes)


# ---------------------------------------------------------------------------
# Reconciliación del itinerario cuando la reserva cambia de fechas
# ---------------------------------------------------------------------------

def _normalizar_actividad(texto):
    """Deja el nombre de la actividad comparable, ignorando el texto que recepción
    haya agregado (ej. 'Scuba Diving — SALIDA ESPECIAL' -> 'scuba diving')."""
    t = " ".join((texto or "").split()).lower()
    for corte in ("—", " - ", "(", "·"):
        if corte in t:
            t = t.split(corte)[0].strip()
    return t


def reconciliar_itinerario(filas_guardadas, filas_nuevas):
    """Ajusta un itinerario editado a mano cuando la reserva cambió de fechas.

    El problema que resuelve: si recepción editó el itinerario y después el PDF trae
    la estadía corrida (o el tour movido), las filas guardadas quedaban con la fecha
    vieja y el huésped recibía datos incorrectos. Antes se avisaba tratándolas como
    "faltantes", lo que al incorporarlas producía filas duplicadas.

    Ahora cada fila guardada se empareja con su equivalente en los datos nuevos por
    el nombre de la actividad, y solo se le actualiza la fecha: se conserva todo el
    texto que recepción haya escrito.

    Devuelve (filas_resultantes, movidas, faltantes).
    """
    # Se agrupan las filas nuevas por actividad, en orden de fecha
    pendientes = {}
    for f in filas_nuevas:
        pendientes.setdefault(_normalizar_actividad(f.get("actividad")), []).append(f)
    for lista in pendientes.values():
        lista.sort(key=_clave_orden)

    resultado, movidas = [], []
    for guardada in sorted(filas_guardadas, key=_clave_orden):
        clave = _normalizar_actividad(guardada.get("actividad"))
        candidatas = pendientes.get(clave)
        nueva = candidatas.pop(0) if candidatas else None
        if nueva and nueva.get("dia") != guardada.get("dia"):
            movidas.append({
                "actividad": " ".join((guardada.get("actividad") or "").split()),
                "de": guardada.get("dia"), "a": nueva.get("dia"),
            })
            guardada = {**guardada, "dia": nueva.get("dia")}
        resultado.append(guardada)

    # Lo que quedó sin emparejar en los datos nuevos es realmente nuevo
    faltantes = [f for lista in pendientes.values() for f in lista]
    resultado = incorporar_faltantes(resultado, [])   # reordena por fecha
    return resultado, movidas, faltantes
