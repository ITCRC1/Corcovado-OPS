"""La hora de un tour, escrita a mano, convertida a «HH:MM».

POR QUÉ EXISTE. El horario del catálogo se escribe en una caja de texto libre, y las
tres cosas que lo leen dan por hecho que dice «HH:MM»: la línea del día lo parte por los
dos puntos, el detector de choques de horario también, y la agenda ordena las salidas
comparando el texto tal cual. Ninguna de las tres avisa cuando recibe otra cosa.

LO QUE PASÓ. Se agregó al catálogo una cabalgata de la tarde escribiendo la hora como la
escribe cualquiera: «2:00 pm». Al partir por los dos puntos salen «2» y «00 pm», así que
la salida se leyó como las dos de la madrugada:

  · la línea del día la dibujó pegada al borde izquierdo —fuera de la ventana del día,
    recortada al borde— y el pajareo de las 6 le quedó encima. Desde la pantalla el tour
    no existía, y no hubo ningún error que mirar;
  · el detector de choques no pudo leer «00 pm», y cuando no entiende una hora supone
    que SÍ podría coincidir (mejor avisar que callar): marcó un conflicto con el PNC que
    no era tal;
  · la agenda, que ordena por el texto, la pone entre las 00 y las 06.

Así que la hora se normaliza AL GUARDARLA, que es el único sitio por donde entra —la
pantalla de Catálogo—, y este módulo es el que sabe leerla. Lo que no se entiende no se
inventa ni se borra: se devuelve None y quien llama decide. El catálogo lo rechaza y lo
dice en la pantalla; el arranque deja el texto como está y lo anota en el registro.

LO QUE NO HACE: adivinar. «2:00» a secas son las dos de la madrugada y así se guarda. No
hay forma de saber si quien lo escribió pensaba en la tarde, y una hora inventada en el
catálogo sale después en la hoja del día que el staff lee por WhatsApp.
"""
import re

# Una hora y, opcionalmente: separador, minutos y la marca de mañana o tarde.
#
# El separador acepta «:», «.», «h» o un espacio —«7:30», «7.30», «7h30», «7 30»— y
# también puede no estar: «730» y «1400» son las dos formas en que se escribe una hora
# de corrido. La marca admite «pm», «p.m.», «p. m.» y «PM».
_PATRON = re.compile(
    r"^(\d{1,2})"                       # la hora
    r"(?:\s*[:.h]\s*|\s+)?"             # separador, si lo hay
    r"(\d{2})?"                         # los minutos, si los hay
    r"\s*(?:([ap])\s*\.?\s*m?\s*\.?)?$",  # a.m. / p.m., si la hay
    re.IGNORECASE)


def esta_en_blanco(texto):
    """Un tour SIN hora es legítimo —el Claro del Bosque y el spa los coordina
    recepción—, así que el vacío no es un error y se distingue de lo ilegible."""
    return texto is None or not str(texto).strip()


def a_minutos(texto):
    """«2:00 pm» -> 840. None si está en blanco o si no se entiende."""
    if esta_en_blanco(texto):
        return None
    m = _PATRON.match(str(texto).replace(" ", " ").strip().lower())
    if not m:
        return None
    hora = int(m.group(1))
    minutos = int(m.group(2) or 0)
    marca = (m.group(3) or "").lower()
    # La marca solo manda sobre un reloj de 12: «14:00 p.m.» ya viene en 24 horas y
    # sumarle doce lo mandaría al día siguiente.
    if marca and hora <= 12:
        if marca == "p" and hora != 12:
            hora += 12
        elif marca == "a" and hora == 12:
            hora = 0
    if hora > 23 or minutos > 59:
        return None
    return hora * 60 + minutos


# Una hora escrita DENTRO DE UNA FRASE: «Be at the guide house at 6:00 a.m.». Es un
# patrón aparte del de arriba a propósito: aquel EXIGE que el texto sea la hora y nada
# más —así una hora mal escrita en el catálogo se rechaza en vez de leerse a medias—, y
# este tiene que encontrarla en medio de palabras.
#
# Lo delicado aquí es lo que NO es una hora: el número de vuelo («Flight: RZ1070»), la
# duración («(5 HOURS TOUR)») o el número de un bungalow. Por eso cada forma pide algo
# que la identifique: o la marca de mañana/tarde, o los dos puntos del reloj.
_EN_UNA_FRASE = re.compile(
    r"(\d{1,2})(?:\s*[:.]\s*(\d{2}))?\s*([ap])\s*\.?\s*m\s*\.?"   # 6:00 a.m., 6 p.m.
    r"|(\d{1,2})\s*:\s*(\d{2})",                                  # 14:00
    re.IGNORECASE)


def primera_en(texto):
    """La PRIMERA hora que aparece en un texto, en minutos. None si no hay ninguna.

    «Be at the guide house at 5:45 p.m. Dinner will be around 7:30 p.m.» -> 1065.

    La primera y no otra porque es la que manda: es la hora a la que el huésped tiene
    que estar en algún lado. Las que vienen después son consecuencia (el almuerzo, la
    cena), y ordenar por ellas pondría un tour de la mañana que almuerza tarde después
    de uno de la tarde.
    """
    m = _EN_UNA_FRASE.search(str(texto or ""))
    if not m:
        return None
    if m.group(1) is not None:
        hora, minutos = int(m.group(1)), int(m.group(2) or 0)
        marca = (m.group(3) or "").lower()
        if hora <= 12:
            if marca == "p" and hora != 12:
                hora += 12
            elif marca == "a" and hora == 12:
                hora = 0
    else:
        hora, minutos = int(m.group(4)), int(m.group(5))
    if hora > 23 or minutos > 59:
        return None
    return hora * 60 + minutos


def hhmm(minutos):
    """840 -> «14:00»."""
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def normalizar(texto):
    """La misma hora en «HH:MM». None si está en blanco o si no se entiende."""
    m = a_minutos(texto)
    return hhmm(m) if m is not None else None


def exigir(texto, como_se_llama):
    """Normaliza y, si hay algo escrito que no se entiende, lo dice.

    Devuelve None cuando el campo viene vacío: eso es un tour sin hora fija, no un
    error. Lanza ValueError cuando hay texto que no es una hora, para que la pantalla
    lo muestre en vez de guardar algo que después nadie ve.
    """
    if esta_en_blanco(texto):
        return None
    hora = normalizar(texto)
    if hora is None:
        raise ValueError(
            f"No se entiende la {como_se_llama}: «{str(texto).strip()}». "
            f"Escribila como 14:00 (24 horas) o como 2:00 pm.")
    return hora
