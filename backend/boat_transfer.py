"""El BT («boat transfer»): el viaje de bote EXTRA que pide una reserva.

QUÉ ES. Además del bote con el que el huésped llega y con el que se va, algunas
reservas piden un traslado suelto a mitad de estadía: para un tour con otro operador,
para subirse al bote de unos amigos, para ir al pueblo. En Opera se escribe «BT» en la
nota, y el código BT ya está en la tabla de traslados de opera_paquetes.

POR QUÉ HACE FALTA LEERLO. Transporte arma sus corridas con el punto de ENTRADA y el de
SALIDA de cada reserva, así que un BT no aparecía en ninguna parte: nadie le asignaba
bote ni capitán, y el día del viaje había que acordarse. Lo pidió el lodge: «cuando en
alguna reserva aparezca esta debe ser cargada en la parte de transporte para ser
asignada el capitán o ayudante correspondiente».

QUÉ NO HACE. No adivina. Si la nota no dice claramente qué día es, no se inventa una
corrida en un día cualquiera: se avisa y que recepción lo escriba. Un bote preparado el
día que no era cuesta lo mismo que no prepararlo, y además nadie lo revisa porque la
pantalla ya decía que estaba cubierto. La hora sí puede faltar —la corrida sale «sin
hora», como ya pasa con los vuelos que no se saben— porque ahí la pantalla lo señala.
"""
import datetime
import re

# «BT» con límites de palabra: así no se cuela dentro de «C-EBT», que es otra cosa (el
# aviso de cama/almohada extra) y aparece en la misma nota de la habitación 09.
BT = re.compile(r"\bBT\b", re.I)

# EL DÍA LO DA EL ITINERARIO, no el texto libre.
#
# La reserva lo escribe en su línea de operación —«08: BT»— igual que un tour, y eso es
# inequívoco. Deducirlo de una frase suelta no lo es: un número en una nota puede ser un
# precio, un vuelo o una hora, y un bote preparado el día que no era cuesta lo mismo que
# no prepararlo, con el agravante de que nadie lo revisa porque la pantalla ya decía que
# estaba cubierto.
#
# El texto libre solo aporta la HORA y el contexto («con quién se engancha»).

# Las horas del fragmento. «6:25 AM», «2:00 PM», «14:30».
_HORA = re.compile(r"\b(\d{1,2})[:.](\d{2})\s*(a\.?\s?m\.?|p\.?\s?m\.?)?", re.I)

# Que el viaje es de ida y vuelta. Si lo dice, dos horas son dos corridas.
_VUELTA = re.compile(r"roundtrip|round\s+trip|ida\s+y\s+vuelta|regresan|retorno|"
                     r"de\s+regreso|vuelven", re.I)

# Que la reserva PIDE el viaje, y no que el traslado venga incluido en la tarifa.
# «PAQUETE 3N/4D+FULL BOARD BT INCLUDED» es lo segundo: no hay nada extra que preparar.
_PIDE = re.compile(r"solicit\w*|pide[nm]?\b|requier\w*|favor\s+(?:coordinar|confirmar)",
                   re.I)

VENTANA = 260          # cuánto texto alrededor del «BT» se mira


def _normalizar_hora(h, m, sufijo):
    """'6','25','AM' -> '06:25'. Devuelve None si no es una hora válida."""
    try:
        hora, minuto = int(h), int(m)
    except (TypeError, ValueError):
        return None
    if not (0 <= minuto < 60):
        return None
    s = (sufijo or "").replace(".", "").replace(" ", "").lower()
    if s.startswith("p") and hora < 12:
        hora += 12
    elif s.startswith("a") and hora == 12:
        hora = 0
    if not (0 <= hora < 24):
        return None
    return f"{hora:02d}:{minuto:02d}"


def _fecha_del_dia(dia, llegada, salida):
    """El día suelto («el 08») convertido a fecha, SOLO si cae dentro de la estadía.

    Es la comprobación que evita el error caro. Una nota puede nombrar un número que no
    es el día del viaje —un precio, un número de vuelo, la hora— y poner un bote en una
    fecha inventada es peor que no ponerlo: la pantalla diría que está cubierto.
    """
    if not (llegada and salida):
        return None
    try:
        desde = datetime.date.fromisoformat(llegada[:10])
        hasta = datetime.date.fromisoformat(salida[:10])
    except ValueError:
        return None
    # Se prueban los meses que toca la estadía: una estadía puede cruzar de mes.
    candidatos = []
    cursor = desde.replace(day=1)
    while cursor <= hasta:
        try:
            candidatos.append(cursor.replace(day=dia))
        except ValueError:
            pass
        cursor = (cursor.replace(day=28) + datetime.timedelta(days=7)).replace(day=1)
    dentro = [f for f in candidatos if desde <= f <= hasta]
    return dentro[0].isoformat() if len(dentro) == 1 else None


def _fragmento_del_bt(texto):
    """El trozo de la nota que habla del BT, para sacar la hora y el contexto.

    La misma reserva nombra «BT» varias veces —en el paquete («+ BT»), en el itinerario
    («08: BT») y en la frase que lo pide— y solo una de ellas sirve.

    Manda la que PIDE el viaje: es la que trae la hora y el con quién. Sin esa
    preferencia, el trozo elegido acababa siendo el del rooming —que tiene números de
    pasaporte y queda al lado— y la corrida mostraba «Rooming: Donna Hoyle 644669711…»
    en vez de «solicitan BT para tour con Pacheco», que es lo que necesita quien lo
    coordina.
    """
    mejor, mejor_puntos = "", (-1, -1)
    for m in BT.finditer(texto or ""):
        ini = max(0, m.start() - VENTANA // 2)
        trozo = (texto or "")[ini:m.end() + VENTANA]
        puntos = (1 if _PIDE.search(trozo) else 0, len(_HORA.findall(trozo)))
        if puntos > mejor_puntos:
            mejor, mejor_puntos = trozo, puntos
    return mejor


def leer(dias, texto, llegada_iso, salida_iso):
    """Los BT de una reserva. Devuelve (viajes, avisos).

    `dias` son los días que trae el ITINERARIO («08: BT» -> ['08']). Cada uno es un
    viaje, y de ahí sale la fecha sin adivinar nada.

    `texto` es la reserva entera, y solo se usa para la HORA y la nota. 'hora' puede
    quedar en None: la corrida sale «sin hora» y la pantalla lo señala, que es muy
    distinto de inventarla.
    """
    texto = texto or ""
    viajes, avisos = [], []

    # Los días, sin repetir: la misma nota puede llegar por varios campos.
    limpios = []
    for d in (dias or []):
        try:
            n = int(str(d).strip())
        except (TypeError, ValueError):
            continue
        if n not in limpios:
            limpios.append(n)

    if not limpios:
        # El texto habla de un BT pero el itinerario no lo tiene. NO se inventa el día:
        # se avisa, y recepción lo escribe donde se escribe todo lo demás.
        #
        # Se exige que la frase PIDA el viaje. «PAQUETE 3N/4D+FULL BOARD BT INCLUDED»
        # dice que el traslado va incluido en la tarifa, no que haya un viaje extra que
        # preparar, y avisar de eso es un falso positivo — y los avisos falsos enseñan
        # a ignorar los de verdad.
        fragmento = _fragmento_del_bt(texto)
        # El «pide» se busca DENTRO del trozo que habla del BT, no en la reserva entera.
        # Una nota larga casi siempre dice «solicita» de algo —un tour, una mesa— y
        # buscarlo en todo el texto convertía cualquier «BT INCLUDED» del paquete en un
        # aviso. Los avisos falsos enseñan a ignorar los de verdad.
        if fragmento and _PIDE.search(fragmento):
            frase = " ".join(fragmento.split())[:150]
            avisos.append(
                "La reserva pide un BT (traslado en bote) y el itinerario no dice qué "
                f"día: «{frase}». Escríbelo en la operación de la reserva (por ejemplo "
                "«08: BT») para que salga en Transporte.")
        return viajes, avisos

    trozo = _fragmento_del_bt(texto)
    horas = []
    for h in _HORA.finditer(trozo):
        valor = _normalizar_hora(h.group(1), h.group(2), h.group(3))
        if valor and valor not in horas:
            horas.append(valor)
    nota = " ".join(trozo.split())[:200]
    ida_y_vuelta = bool(_VUELTA.search(trozo)) and len(horas) >= 2

    for dia in limpios:
        fecha = _fecha_del_dia(dia, llegada_iso, salida_iso)
        if not fecha:
            avisos.append(
                f"El itinerario de la reserva pide un BT el día {dia:02d}, que no cae "
                "dentro de la estadía. Revisa la fecha en la reserva.")
            continue
        if not horas:
            viajes.append({"fecha": fecha, "hora": None, "nota": nota})
        elif ida_y_vuelta:
            # Ida y vuelta son DOS movimientos de bote, y cada uno necesita su gente.
            viajes.append({"fecha": fecha, "hora": horas[0], "nota": nota})
            viajes.append({"fecha": fecha, "hora": horas[1], "nota": nota})
        else:
            viajes.append({"fecha": fecha, "hora": horas[0], "nota": nota})
    return viajes, avisos
