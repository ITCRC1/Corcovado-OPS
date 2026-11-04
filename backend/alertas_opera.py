"""Las ALERTAS de la reserva en Opera, y a dónde va cada una.

QUÉ SON. Además de las notas, Opera deja poner «alerts» en una reserva: avisos que
saltan en pantalla al abrirla. El lodge las usa de verdad —44 de 347 reservas de la
ventana— y es donde escribe lo que nadie quiere que se pase por alto: la condición
médica de un huésped, un cobro pendiente, un encargo para recepción.

POR QUÉ NO LLEGABAN. El bloque se pedía como «ReservationAlerts» y Oracle lo rechaza
con 400. El nombre que concede es «Alerts». Medido: 49 de las 53 alertas no estaban en
ninguna otra parte del sistema; solo 4 coincidían con algo ya escrito en las notas.

A DÓNDE VA CADA UNA. No todas son lo mismo y meterlas todas en el mismo sitio las
inutiliza:

  · Las de ALERGIA y DIETA —Opera les da código propio, ALG_* y DIET_*— y las que
    hablan de comida van a la hoja de cocina, con las demás restricciones.
  · Las que piden algo que se PREPARA (un queque, una cama extra) pasan por el mismo
    detector de amenidades que ya lee las notas, así que no hace falta otra regla.
  · El resto queda como AVISO de la reserva. «Avisar a reservaciones si hay más
    clientes interesados» no es una tarea que alguien pueda cerrar, y llenar Amenidades
    de cosas sin cierre enseña a ignorar esa lista.

Todas se vuelven a leer en cada ciclo, como las notas y las PM: si recepción corrige la
alerta en Opera, el módulo tiene que corregirse con ella.
"""
import re

# Los códigos que Opera ya trae clasificados. Es mejor fuente que adivinar del texto:
# aquí la alergia viene marcada, no deducida.
#
#   ALG_SFD  alergia a mariscos      ALG_NUT  alergia a frutos secos
#   DIET_VEGN  dieta vegana          AMEN_EXTB  cama extra
PREFIJOS_DE_COCINA = ("ALG_", "DIET_", "ALLERG", "FOOD")

# Los que son para que alguien lo LEA, no para preparar nada.
CODIGOS_DE_AVISO = ("FRONT_DESK", "ADDITIONAL_INFO", "GUEST_SERVICE", "RESERVATION")

# El encabezado con el que el lodge escribe a quién va dirigida. Se quita del texto
# porque se repite en casi todas y roba el sitio de lo que sí dice algo.
_ENCABEZADO = re.compile(
    r"^\s*(?:ATENCI[ÓO]N|ATENCION|ATTENTION)\s*[:\-]?\s*"
    r"(?:FRONT\s*DESK|GUEST\s*SERVICE(?:\s*&\s*OPERATIONS)?|RECEPCI[ÓO]N|COCINA)?\s*[:\-]?\s*",
    re.I)


def _limpio(texto):
    return " ".join((texto or "").split())


def leer(nodo):
    """Las alertas de un detalle de Opera, normalizadas.

    Devuelve [{codigo, texto, para_cocina}]. Las vacías se descartan: una alerta sin
    texto no dice nada y ocuparía sitio en la pantalla.
    """
    salida = []
    for a in (nodo or {}).get("alerts") or []:
        if not isinstance(a, dict):
            continue
        texto = _limpio(a.get("description"))
        if not texto:
            continue
        codigo = str(a.get("code") or "").strip().upper()
        salida.append({
            "codigo": codigo,
            "texto": texto,
            "para_cocina": es_de_cocina(codigo, texto),
        })
    return salida


# Lo que delata que una alerta habla de comida, además de lo que ya reconoce el
# detector de restricciones. Son las formas que usa el lodge en sus alertas y que NO
# aparecen en una nota normal: ahí se escribe «alergia a X», aquí se explica el caso
# entero —«seguridad alimentaria», «debe evitar los siguientes alimentos»—.
_HABLA_DE_COMIDA = re.compile(
    r"seguridad\s+aliment|higiene\s+aliment|manipulaci[óo]n\s+de\s+(?:los\s+)?aliment|"
    r"evitar\s+(?:los\s+)?(?:siguientes\s+)?aliment|interact[úu]\w*\s+con\s+(?:sus\s+)?medicam|"
    r"equipo\s+de\s+cocina|personal\s+de\s+cocina|avisar\s+a\s+cocina|"
    r"food\s+safety|avoid\s+(?:the\s+)?following\s+food|dietary",
    re.I)


def es_de_cocina(codigo, texto):
    """Si la alerta habla de comida, y por tanto le toca a cocina verla.

    Se mira PRIMERO el código, que es lo que Opera ya clasificó: ahí la alergia viene
    marcada y no deducida, y una «DIET_VEGN» cuyo texto no repita la palabra se
    perdería si se mirara el texto primero.

    OJO CON COMO SE PREGUNTA POR EL TEXTO. La primera versión le pasaba al detector de
    restricciones el NOMBRE «Restricción alimentaria / alergia» junto con el texto, y
    el detector decide también por el nombre: daba que sí SIEMPRE. Con eso las tres
    alertas de la paciente trasplantada —incluida la que pide reunirse con el gerente—
    salían como de cocina. Se pregunta solo por el texto.
    """
    codigo = (codigo or "").upper()
    if any(codigo.startswith(p) for p in PREFIJOS_DE_COCINA):
        return True
    if _HABLA_DE_COMIDA.search(texto or ""):
        return True
    import restaurantes as _rest
    return bool(_rest.es_restriccion_alimentaria(None, None, texto))


def texto_para_amenidades(alertas):
    """El texto de las alertas, para pasarlo por el detector de amenidades que ya existe.

    Así el queque, las fresas o la cama extra que estén escritos en una alerta se
    reconocen con las MISMAS reglas que si estuvieran en la nota. Una segunda lista de
    patrones acabaría diciendo cosas distintas de la primera.
    """
    return " ".join(a["texto"] for a in (alertas or []))


def sin_encabezado(texto):
    """«ATENCION FRONT DESK: COBRAR $678…» -> «COBRAR $678…»."""
    return _ENCABEZADO.sub("", texto or "").strip() or (texto or "").strip()
