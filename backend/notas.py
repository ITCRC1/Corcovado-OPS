"""Qué parte de una nota de reserva sirve para operar el día, y qué parte no.

POR QUÉ EXISTE. La hoja del día se le manda al staff: recepción, cocina, guías,
transporte. Lo pidió el lodge: «en la parte de notas solo colocar notas relevantes (no
tarifas, no upgrades, no negociaciones)». Y no es manía de orden — la columna de notas
del PDF corta a 110 caracteres, así que un «FACTURAR A CXC $7.775,19 · MONTO TOTAL DE LA
RSV · SOURCE: CR SUN TOURS» por delante se come el renglón entero y tapa el «reservar el
Sunset Drinks a las 5:30pm» que venía detrás. La plata no solo sobra: desplaza.

LA REGLA DE ORO ES NO PERDER NADA OPERATIVO. Quitar de más es el fallo caro y además
invisible: la hoja sale limpia, nadie echa de menos lo que no ve, y la cuna que había que
poner no se pone. Quedarse con un pedazo de más solo hace ruido, y el ruido se lee y se
pregunta. De ahí las tres decisiones que sostienen esto:

  1. SE JUZGA PEDAZO A PEDAZO, no la nota entera. En las notas reales lo comercial y lo
     operativo vienen pegados sin un punto en medio —«ATENCION FRONT DESK COBRAR $678 POR
     EL TOUR DE MANGLAR ATENCION FRONT DESK Favor confirmar el queque de vainilla»— así
     que juzgando la nota entera habría que tirar el queque con la factura.

  2. UNA CIFRA NO BASTA PARA TIRAR UN PEDAZO. «Favor confirmar el queque ($24.6) y unas
     fresas ($28.25) con chocolate» es una instrucción para cocina con el precio metido
     dentro — y es justo la nota que el lodge pidió rescatar hace unas semanas porque no
     se estaba leyendo. Se tira el pedazo solo si además habla de cobrar, facturar,
     tarifas, upgrades, montos o comisiones. Si solo lleva la cifra, se borra la cifra y
     se queda la instrucción.

  3. LOS ENCABEZADOS NO SON NOTAS. «ATENCION FRONT DESK» a secas no dice nada en una
     columna que ya se llama NOTAS; lo que importa es lo que viene detrás.

LO QUE ESTE FILTRO NO HACE: partir por comas. «Operador Reel Time, Captain Willy
TRANSBORDO YA QUEDÓ CARGADO DESDE FIXED CHARGES» se va entero, y con él el nombre del
operador. Partir por comas arreglaría ese caso y dejaría la nota de la agencia cortada
en tres pedazos que hoy se leen de corrido; se prefirió lo segundo, y ese texto vive en
nota_en_casa, que la hoja del día no usa.

Medido sobre las notas reales antes de escribirlo: 245 reservas vivas, 9 con nota que la
hoja usa, y una de ellas con la factura de un Sirena por delante de la hora a la que el
huésped tiene que registrarse para su vuelo.
"""
import re

# Habla de PLATA, no de operación. Con esto el pedazo se va entero.
#
# Cada patrón lleva sus límites de palabra a propósito: sin ellos «Separate beds» y
# «separate fryers» —las dos de verdad, las dos de una alergia— se iban por llevar
# «rate» dentro, y una alergia es exactamente lo que no se puede perder.
_COMERCIAL = re.compile(
    r"""(?xi)
    \b(?:usd|us\$|eur|crc)\b
  | \btarifas?\b | \brates?\b | \bprecios?\b
  | \bcobr(?:ar|a|an|o|ado|arle|amos)\b | \bse\s+le\s+cobr
  | \bfactur(?:ar|a|an|ado|arle|aci[oó]n)\b | \bcxc\b | \binvoices?\b
  | \bpag(?:o|os|ar|ado|aron|arle)\b | \bdep[oó]sito\b | \banticipo\b | \bsaldo\b
  | \bcr[eé]ditos?\b | \breembols\w* | \bpenalidad\w*
  | \w*upgrades?\b                # «freeupgrade» viene pegado en las notas reales
  | \bdescuentos?\b | \bdiscounts?\b | \bcomisi[oó]n\w*\b | \bnegocia\w*
    # «PAQUETE 4N/5D+BREAKFAST» es la descripción de lo vendido, no una instrucción: los
    # tours tienen su propia columna y el régimen el suyo.
  | \bpaquete\s+\d+\s*[nd]\s*/\s*\d+\s*[nd]\b
  | \bmontos?\b | \btotal\s+booking\b | \bfixed\s+charges\b
  | \bpostear\b | \bcotiz\w*
  | \bhonor(?:ar|ó|o|aron)\s+(?:precio|tarifa|las\s+tarifa)
    """)

# Una cifra de dinero. Sola NO tira el pedazo: se borra y lo demás se queda.
_IMPORTE = re.compile(r"\(?\s*(?:US)?\$\s*\d[\d.,]*\s*\)?", re.IGNORECASE)

# Dónde se puede partir sin romper una frase: finales de oración, saltos de línea y los
# separadores que usa el propio sistema.
_CORTES = re.compile(r"[\n\r]+|\s*·\s*|\s*\|\s*|(?<=[.;:])\s+")

# Palabras que NO terminan una frase aunque la siguiente vaya en mayúscula. Sin esta
# lista, «favor indicar salida del Lodge» se partía en «salida del» y «Lodge», y
# «cumpleaños de Mr James» en «de» y «Mr James».
_CONECTORES = {
    "a", "al", "ante", "con", "contra", "de", "del", "desde", "e", "el", "ella",
    "ellos", "en", "entre", "es", "esta", "este", "hacia", "hasta", "la", "las", "lo",
    "los", "mi", "o", "para", "por", "que", "se", "segun", "según", "si", "sin",
    "sobre", "su", "sus", "tras", "un", "una", "unos", "unas", "y",
}

# Marcas que empiezan asunto aunque no haya puntuación delante.
_MARCAS = re.compile(
    r"(?=(?:ATENCI[OÓ]N\b|ATTENTION\b|SOURCE\s*:|FACTURAR\b|COBRAR\b|"
    r"MONTO\s+TOTAL\b|Incluido\s+en\s+la\s+reserva\s*:))", re.IGNORECASE)

# Un encabezado sin contenido. Se exige que NO lleve cifras, para no tragarse una nota
# de verdad que empiece igual («Salida del lodge a las 7:00»).
_ENCABEZADO = re.compile(
    r"^(?:atenci[oó]n|attention)\b[^\d]{0,45}$|"
    r"^(?:salida|llegada|entrada|nota|aviso|source)$", re.IGNORECASE)

# Un pedazo tiene que decir algo: «-», «y», «de la» no son una nota.
_PALABRA = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}")


def _frases_pegadas(texto):
    """Parte donde el PMS pegó dos frases sin puntuación: minúscula y luego mayúscula.

    Es lo que separa «...facturar a la agencia» de «Para el vuelo de salida deben estar
    registrando a las 13:45» — sin este corte esa hora se iba a la basura con la
    factura, que es el caso que destapó todo esto.

    Se hace a mano y no con una expresión regular porque hay que mirar la palabra
    ANTERIOR entera (para no partir «del Lodge»), y el re de Python no admite un
    lookbehind de ancho variable.
    """
    partes, actual = [], []
    for palabra in (texto or "").split():
        if actual:
            previa = actual[-1]
            # La palabra anterior tiene que ir en MINÚSCULA. Sin esta condición, «Dear
            # Ann Happy Birthday!» se partía en cuatro —cada palabra empieza en
            # mayúscula y acaba en minúscula— y el mensaje de la tarjeta de cumpleaños
            # llegaba a la hoja hecho pedazos. También es lo que mantiene entero un
            # «Mr James».
            corta = (palabra[:1].isupper()
                     and not previa[:1].isupper()
                     and previa[-1:].islower()
                     and previa.strip(".,;:()").lower() not in _CONECTORES)
            if corta:
                partes.append(" ".join(actual))
                actual = []
        actual.append(palabra)
    if actual:
        partes.append(" ".join(actual))
    return partes


# «SOURCE: CR SUN TOURS» es el canal de venta, y hay que quitarlo ENTERO antes de partir
# nada: el corte por dos puntos dejaría «SOURCE» por un lado —que se va como
# encabezado— y «CR SUN TOURS» por otro, que no se parece a nada comercial y se quedaba.
_CANAL = re.compile(r"\bsource\s*:[^\n\r·|]*", re.IGNORECASE)


def _grupos(texto):
    """Los pedazos agrupados por la frase de la que salieron.

    Se agrupan y no se sueltan de corrido porque hace falta saber quién venía JUNTO a
    quién: ver el arranque colgado en solo_lo_operativo.
    """
    for a in _CORTES.split(_CANAL.sub(" ", texto or "")):
        grupo = []
        for b in _MARCAS.split(a or ""):
            for c in _frases_pegadas(b):
                limpio = (c or "").strip(" \t-–—*:;,")
                if limpio:
                    grupo.append(limpio)
        if grupo:
            yield grupo


def _pedazos(texto):
    """La nota partida en unidades que se puedan juzgar por separado."""
    for grupo in _grupos(texto):
        for pedazo in grupo:
            yield pedazo


def _es_arranque_colgado(pedazo):
    """Un trozo corto que empieza en minúscula y no cierra: «se agrega adicional».

    Es el principio de la frase comercial que viene detrás —«se agrega adicional Sirena
    $772.92 facturar a la agencia»— partida por el corte de frases. Solo no dice nada y
    se come diecinueve de los ciento diez caracteres que cabían en la columna.

    Se pide MINÚSCULA al principio a propósito: un «RECOGER EL EQUIPAJE» delante de un
    cobro es corto igual, pero es una instrucción de verdad y tiene que quedarse.
    """
    return (pedazo[:1].islower()
            and len(_PALABRA.findall(pedazo)) <= 4
            and pedazo[-1:] not in ".!?")


# QUIÉN LO PIDIÓ NO ES LA PETICIÓN. Lo pidió el lodge: «colocar solo la solicitud, sin
# las notas no necesarias — ejemplo, solicitan extra pillow pero no colocar "solicitado
# por K.S"». En la columna de notas, que corta a 110 caracteres, el nombre de quien
# atendió la llamada desplaza a lo que hay que hacer.
#
# Se quita la ATRIBUCIÓN, no la instrucción: de «EXTRA PILLOWS CONTACTADO POR K.S» queda
# «EXTRA PILLOWS». Y el nombre se acota a unas pocas palabras para que no se lleve por
# delante media frase si alguien escribe «coordinado por la agencia que viaja con ellos».
_ATRIBUCION = re.compile(
    r"\s*\b(?:contactad[oa]|solicitad[oa]|coordinad[oa]|autorizad[oa]|aprobad[oa]|"
    r"gestionad[oa]|confirmad[oa]|revisad[oa]|reservad[oa])\s+por\s+"
    r"(?:[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ.]*\.?(?:\s+(?=[A-ZÁÉÍÓÚÑ]))?){1,3}",
    re.IGNORECASE)

# La firma de quien escribió la nota, al final: «DAYA 20/04/26». Son iniciales o un
# nombre corto en mayúsculas seguidos de una fecha, y no le dicen nada a quien opera.
_FIRMA = re.compile(
    r"[\s,;·|-]*\b[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ.]{1,11}\s+\d{1,2}/\d{1,2}/\d{2,4}\.?\s*$")

# Una fecha suelta al principio del pedazo, sin nada que la explique: «06/11 EXTRA
# PILLOWS». La hoja del día ya tiene su propia columna de fecha y la nota es de ESE día,
# así que repetirla ahí solo gasta renglón. Se exige que detrás venga texto de verdad
# para no vaciar un pedazo que fuera solo la fecha.
_FECHA_AL_FRENTE = re.compile(r"^\d{1,2}\s*/\s*\d{1,2}(?:\s*/\s*\d{2,4})?\s+(?=\S)")


# «SALIDA: VIA DRAKE RZ111 11:00 a.» — el muelle, el vuelo y la hora, que son
# exactamente tres columnas de la hoja: SIERPE/DRAKE, VUELO (que la hoja añade sola) y
# HORARIO. Repetirlo en notas gasta el renglón y, peor, pone una hora distinta de la de
# la columna —ahí va la del BOTE, no la del avión— al lado de la buena.
#
# Solo se va si el pedazo NO dice nada más: con «VIA DRAKE, el cliente pide salir antes»
# se queda entero, porque esa segunda mitad no está en ninguna columna.
_SOLO_EMBARQUE = re.compile(
    r"^(?:salida|entrada|llegada)?\s*:?\s*v[ií]a\s+(?:sierpe|drake)\b"
    r"(?:[\s,.:-]*(?:[A-Z]{2}\s?\d{2,5}|\d{1,2}\s*:\s*\d{2}|[ap]\.?\s*m?\.?|hrs?\.?))*"
    r"[\s.,]*$", re.IGNORECASE)


def sin_atribucion(pedazo):
    """El pedazo sin «contactado por X», sin la firma del final y sin lo que ya es una
    columna de la hoja."""
    limpio = _ATRIBUCION.sub(" ", pedazo or "")
    limpio = _FIRMA.sub("", limpio)
    limpio = _FECHA_AL_FRENTE.sub("", limpio)
    # Al sacar la atribución de en medio queda el hueco delante de la coma: «Transporte
    # , confirmar hora». Se cierra aquí y no al final porque es puntuación interior, no
    # de los extremos.
    limpio = re.sub(r"\s+([,;.])", r"\1", re.sub(r"\s{2,}", " ", limpio))
    limpio = limpio.strip(" \t-–—:;,·")
    return "" if _SOLO_EMBARQUE.match(limpio) else limpio


def es_comercial(pedazo):
    """Si este pedazo habla de plata: tarifas, cobros, upgrades, negociaciones."""
    return bool(_COMERCIAL.search(pedazo or ""))


def sin_importes(pedazo):
    """El pedazo con las cifras de dinero fuera, para dejar la instrucción limpia."""
    return re.sub(r"\s{2,}", " ", _IMPORTE.sub(" ", pedazo or "")).strip(" \t-–—:;,")


def solo_lo_operativo(texto):
    """La nota sin lo comercial, lista para la hoja del día.

    Devuelve '' si no quedó nada, que es lo correcto cuando la nota entera era la
    factura. Lo que no se entiende se queda: ver la cabecera.
    """
    quedan, vistos = [], set()
    for grupo in _grupos(texto):
        de_esta_frase = []
        for pedazo in grupo:
            if es_comercial(pedazo):
                # Y con él, el arranque colgado que lo precedía en la misma frase.
                if de_esta_frase and _es_arranque_colgado(de_esta_frase[-1]):
                    de_esta_frase.pop()
                continue
            if _ENCABEZADO.match(pedazo):
                continue
            tenia_cifra = bool(_IMPORTE.search(pedazo))
            pedazo = sin_importes(pedazo) if tenia_cifra else pedazo
            # Quién lo pidió y cuándo lo apuntaron se van; la petición se queda.
            pedazo = sin_atribucion(pedazo)
            palabras = _PALABRA.findall(pedazo)
            if not palabras:
                continue
            # Lo que era solo una cifra con una etiqueta delante —«TOTAL $1.182,51»— se
            # va: quitada la cifra no queda nota, queda la etiqueta.
            if tenia_cifra and len(palabras) < 3:
                continue
            de_esta_frase.append(pedazo)

        for pedazo in de_esta_frase:
            # El PMS repite el mismo aviso en dos campos a la vez; en la hoja ocuparía
            # el doble para decir lo mismo.
            clave = " ".join(pedazo.lower().split())
            if clave in vistos:
                continue
            vistos.add(clave)
            quedan.append(pedazo)
    return " · ".join(quedan)
