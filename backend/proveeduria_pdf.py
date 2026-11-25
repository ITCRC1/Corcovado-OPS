"""El PDF de la orden de compra: el papel que recibe el proveedor.

POR QUÉ EXISTE. La orden se le manda a un proveedor que no entra a este sistema y que la
reenvía por WhatsApp o la imprime. Una pantalla no sirve para eso; un PDF sí, y es
exactamente lo que la hoja de cálculo producía.

QUÉ TIENE QUE DECIR SÍ O SÍ, y por qué cada cosa:

  · La cédula jurídica y la dirección del lodge, porque con eso el proveedor factura.
  · La DIRECCIÓN DE ENTREGA, que NO es la del lodge: la mercadería no llega aquí, llega
    al muelle de Sierpe y de ahí sube en bote. Un proveedor que lee la dirección del
    lodge intenta entregar en un sitio al que no se llega por carretera.
  · El número de orden, porque es con lo que después se cruza la factura.
  · Quién la pidió y de qué departamento, que es a quién se le reclama.

Se dibuja con reportlab, como la hoja del día y el itinerario.
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.pdfgen import canvas as canvas_mod

VERDE = colors.Color(0.1216, 0.2275, 0.1804)
GRIS = colors.Color(0.45, 0.45, 0.42)
LINEA = colors.Color(0.85, 0.82, 0.76)

ANCHO, ALTO = letter
MARGEN = 18 * mm

# Las columnas, en el orden de la hoja. Los anchos suman el ancho útil de la página.
COLUMNAS = [("cuenta", "CUENTA", 34), ("codigo", "CÓDIGO", 22),
            ("descripcion", "DESCRIPCIÓN", 62), ("unidad", "UNIDAD", 18),
            ("cantidad", "CANT.", 16), ("precio", "P. UNIT.", 22),
            ("total", "TOTAL", 24)]


def _colones(centimos):
    if centimos is None:
        return "—"
    return f"{round(centimos / 100):,}".replace(",", ".")


def generar(orden, config):
    """Devuelve el PDF de una orden de compra, ya armada por proveeduria.orden()."""
    buf = io.BytesIO()
    c = canvas_mod.Canvas(buf, pagesize=letter)
    chico = ParagraphStyle("chico", fontName="Helvetica", fontSize=7.4,
                           textColor=VERDE, leading=9)
    cabecera = ParagraphStyle("cab", fontName="Helvetica-Bold", fontSize=7.4,
                              textColor=colors.white, leading=9)

    y = ALTO - MARGEN

    # --- Quién manda la orden ---
    c.setFillColor(VERDE)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(MARGEN, y, config.get("razon_social", ""))
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(ANCHO - MARGEN, y, "ORDEN DE COMPRA")
    y -= 13

    c.setFont("Helvetica", 8)
    c.setFillColor(GRIS)
    for linea in (f"Cédula jurídica: {config.get('cedula_juridica','')}",
                  config.get("direccion", ""),
                  f"{config.get('correo','')}  ·  {config.get('telefono1','')}"
                  f"  ·  {config.get('telefono2','')}"):
        # La dirección es larga: se parte a mano para no depender de un Paragraph.
        for trozo in _partir(c, linea, ANCHO - 2 * MARGEN - 150, "Helvetica", 8):
            c.drawString(MARGEN, y, trozo)
            y -= 9.5

    # El número y la fecha, arriba a la derecha y grandes: es con lo que se cruza la
    # factura, y es lo primero que alguien busca en el papel.
    c.setFillColor(VERDE)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(ANCHO - MARGEN, ALTO - MARGEN - 20, f"N.º {orden['numero']}")
    c.setFont("Helvetica", 9)
    c.drawRightString(ANCHO - MARGEN, ALTO - MARGEN - 33, orden.get("fecha", ""))
    estado = orden.get("estado") or ""
    if estado:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 8)
        c.drawRightString(ANCHO - MARGEN, ALTO - MARGEN - 44, estado)

    y -= 8
    c.setStrokeColor(LINEA)
    c.setLineWidth(0.7)
    c.line(MARGEN, y, ANCHO - MARGEN, y)
    y -= 14

    # --- A quién se le compra y dónde se entrega ---
    mitad = (ANCHO - 2 * MARGEN) / 2
    izquierda = [
        ("Proveedor", orden.get("proveedor") or "—"),
        ("Contacto", orden.get("proveedor_contacto") or "—"),
        ("Teléfono", orden.get("proveedor_telefono") or "—"),
        ("Correo", orden.get("proveedor_correo") or "—"),
        ("Condición", (orden.get("condicion") or "—")
         + (f" · {orden['dias_credito']} días" if orden.get("dias_credito") else "")),
    ]
    derecha = [
        ("Solicitado por", orden.get("solicitado_por") or "—"),
        ("Departamento", orden.get("departamento") or "—"),
        ("Factura recibida", orden.get("factura") or "—"),
    ]
    # SE RECORTA POR ANCHO MEDIDO, no por número de letras. «CENTRO INTERNACIONAL DE
    # INVERSIONES, S.A (BELCA)» cabe en 48 caracteres y NO cabe en la media página: se
    # metía encima de «SOLICITADO POR» y las dos cosas se leían una sobre la otra.
    tope = y
    for etiqueta, valor in izquierda:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7.5)
        c.drawString(MARGEN, y, etiqueta.upper())
        c.setFillColor(VERDE)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(MARGEN + 62, y,
                     _cabe(c, valor, mitad - 70, "Helvetica-Bold", 8.5))
        y -= 12
    y2 = tope
    for etiqueta, valor in derecha:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7.5)
        c.drawString(MARGEN + mitad, y2, etiqueta.upper())
        c.setFillColor(VERDE)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(MARGEN + mitad + 88, y2,
                     _cabe(c, valor, mitad - 96, "Helvetica-Bold", 8.5))
        y2 -= 12

    # LA DIRECCIÓN DE ENTREGA, destacada. Es el dato que un proveedor nuevo se equivoca:
    # la mercadería no llega al lodge, llega al muelle.
    y2 -= 4
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGEN + mitad, y2, "ENTREGAR EN")
    y2 -= 10
    c.setFillColor(VERDE)
    c.setFont("Helvetica", 7.8)
    for trozo in _partir(c, config.get("direccion_entrega", ""), mitad - 6,
                         "Helvetica", 7.8):
        c.drawString(MARGEN + mitad, y2, trozo)
        y2 -= 9

    y = min(y, y2) - 10

    # --- Las líneas ---
    anchos = [w * mm for _, _, w in COLUMNAS]
    datos = [[Paragraph(t, cabecera) for _, t, _ in COLUMNAS]]
    for l in orden.get("lineas", []):
        datos.append([
            Paragraph(str(l.get("cuenta") or "")[:34], chico),
            Paragraph(str(l.get("codigo") or ""), chico),
            Paragraph(str(l.get("descripcion") or ""), chico),
            Paragraph(str(l.get("unidad") or ""), chico),
            Paragraph(f"{l.get('cantidad', 0):g}", chico),
            Paragraph(_colones(l.get("valor_unitario")), chico),
            Paragraph(_colones(l.get("total")), chico),
        ])
    tabla = Table(datos, colWidths=anchos, repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VERDE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINEA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    _ancho, alto_tabla = tabla.wrapOn(c, sum(anchos), ALTO)
    tabla.drawOn(c, MARGEN, y - alto_tabla)
    y = y - alto_tabla - 14

    # --- El total ---
    c.setFillColor(VERDE)
    c.setFont("Helvetica-Bold", 11)
    # «CRC» y no «₡»: Helvetica no trae el símbolo del colón y reportlab lo dibuja como
    # un cuadro negro. Lo vi en el papel. En la pantalla sí se usa ₡ —ahí la tipografía
    # lo tiene—, y en una orden que va a un proveedor «CRC» no se presta a dudas.
    c.drawRightString(ANCHO - MARGEN, y, f"TOTAL  CRC {_colones(orden.get('total'))}")
    y -= 12
    # SE DICE CUÁNTAS LÍNEAS NO TIENEN PRECIO. El total es lo que el lodge se compromete
    # a pagar: enseñarlo como completo cuando faltan tres renglones es la clase de cifra
    # que se firma sin mirar.
    if orden.get("lineas_sin_precio"):
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7.5)
        c.drawRightString(
            ANCHO - MARGEN, y,
            f"no incluye {orden['lineas_sin_precio']} línea(s) sin precio")
        y -= 12

    if orden.get("observaciones"):
        y -= 6
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7.5)
        c.drawString(MARGEN, y, "OBSERVACIONES")
        y -= 10
        c.setFillColor(VERDE)
        c.setFont("Helvetica", 8)
        for trozo in _partir(c, orden["observaciones"], ANCHO - 2 * MARGEN,
                             "Helvetica", 8):
            c.drawString(MARGEN, y, trozo)
            y -= 10

    # --- La firma ---
    y = max(y - 26, MARGEN + 26)
    c.setStrokeColor(LINEA)
    c.line(MARGEN, y, MARGEN + 70 * mm, y)
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGEN, y - 10, "Autorizado por")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def _cabe(c, texto, ancho, fuente, tam):
    """El texto recortado a lo que CABE en ese ancho, con «…» si sobra.

    Recortar por número de letras no sirve: un nombre de proveedor de 48 caracteres se
    sale igual y se dibuja encima de la columna de al lado, y lo que se lee son las dos
    cosas superpuestas.
    """
    t = str(texto if texto is not None else "")
    if c.stringWidth(t, fuente, tam) <= ancho:
        return t
    while t and c.stringWidth(t + "…", fuente, tam) > ancho:
        t = t[:-1]
    return (t + "…") if t else ""


def _partir(c, texto, ancho, fuente, tam):
    """Parte un texto en renglones que quepan. Sin esto, la dirección de entrega se sale
    de la página y el proveedor lee media dirección."""
    palabras = str(texto or "").split()
    renglones, actual = [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if c.stringWidth(prueba, fuente, tam) <= ancho:
            actual = prueba
        else:
            if actual:
                renglones.append(actual)
            actual = p
    if actual:
        renglones.append(actual)
    return renglones or [""]
