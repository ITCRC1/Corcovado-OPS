"""
Los traslados: quién entra y quién sale del lodge, con su guía y su bote.

QUÉ PROBLEMA RESUELVE
---------------------
Los tours ya tenían guía y bote asignados; los INGRESOS y SALIDAS no. Y son el momento
más delicado del día: si nadie va al muelle de Sierpe o a la pista de Drake, el huésped
se queda tirado con las maletas en un lugar sin señal. La pantalla de Transporte decía a
qué hora y por dónde, pero no quién lo lleva.

LA CORRIDA SE DERIVA, NO SE INVENTA
-----------------------------------
Una **corrida** es un viaje del bote: una fecha, una dirección (entrada o salida), un
punto (Sierpe o Drake) y una HORA. Lo que la distingue de otra corrida del mismo día y
punto es la hora, no un número de grupo: el lodge manda el MISMO bote con el MISMO guía
varias veces, sobre todo por Drake, donde cada vuelo llega a una hora distinta.

Por eso las corridas no se crean a mano: se derivan de los huéspedes. Quienes se mueven a
la misma hora, por el mismo punto y en la misma dirección van juntos, y eso es
exactamente cómo funciona en la práctica — los del vuelo de las 9 suben al mismo bote.

Lo ÚNICO que se guarda es a quién se le asignó cada corrida (`traslado`). El pax, los
huéspedes y las horas salen de las reservas cada vez que se pregunta. Así:

  · No hay nada que se pueda desincronizar. Si cambia la hora de un vuelo, el huésped
    aparece solo en la corrida que le toca.
  · Si una reserva se cancela, desaparece de su corrida sin que nadie tenga que acordarse.

El precio de esto hay que decirlo: si a un huésped le mueven el vuelo de las 9 a las 11,
su corrida de las 9 deja de existir y la de las 11 aparece SIN ASIGNAR. Es lo correcto
—cambió el viaje, hay que volver a decidir quién va—, y la pantalla lo muestra como lo
que es: una corrida sin guía. Lo contrario, arrastrar la asignación a una hora que nadie
confirmó, es lo que deja a alguien esperando en la pista.
"""
import datetime

PUNTOS = ("Sierpe", "Drake")
TIPOS = ("entrada", "salida")

# La corrida de los que todavía no tienen hora. No se esconden: son justamente los que
# hay que resolver, y una lista que solo muestre a los que ya tienen hora esconde el
# trabajo que queda. Es la misma razón por la que la lista de vuelos del portal muestra
# a los que no han contestado.
SIN_HORA = ""


def normalizar_punto(texto):
    """'sierpe', 'SIERPE', ' Sierpe ' -> 'Sierpe'. None si no es uno de los dos."""
    t = (texto or "").strip().lower()
    for p in PUNTOS:
        if p.lower() == t:
            return p
    return None


def minutos_de(hora):
    """La hora en minutos desde medianoche, o None si no se puede leer.

    Hace falta porque las horas llegan en DOS formatos y hay que poder compararlas:
    del PDF vienen como '09:00', y los horarios fijos del lodge —el bote de Sierpe, el
    cálculo de la salida por Drake— vienen escritos para leerse, como '11:30 a.m.'.

    Comparando los textos tal cual, un guía en Sierpe a las '9:00 a.m.' y en Drake a las
    '09:00' no se detectaba como choque: es el mismo momento escrito distinto, y nadie
    puede estar en los dos lugares. Se compara en minutos, no en letras.
    """
    t = str(hora or "").strip().lower().replace(".", "").replace(" ", "")
    if not t:
        return None
    tarde = t.endswith("pm")
    manana = t.endswith("am")
    if tarde or manana:
        t = t[:-2]
    try:
        partes = t.split(":")
        h = int(partes[0])
        m = int(partes[1]) if len(partes) > 1 else 0
    except (ValueError, IndexError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    if tarde and h < 12:
        h += 12
    if manana and h == 12:
        h = 0
    return h * 60 + m


def hora_de_traslado(fila, es_entrada):
    """Hora a la que de verdad se mueve el huésped, según lo ya dispuesto por el lodge.

    La pantalla de Transporte mostraba solo lo que viniera escrito en el PDF, y por eso
    salían tantas líneas en blanco: por Sierpe el bote sale a la misma hora todos los
    días y el PDF no la repite, y en las salidas por Sierpe la hora estaba fija en "—".

    El orden es: lo que diga el PDF manda; si no dice nada, se aplica la regla del punto.

      · Sierpe → horario fijo del bote (llegada y salida).
      · Drake, llegada → la hora del vuelo; sin vuelo no se puede saber.
      · Drake, salida  → el bote, calculado hacia atrás desde el vuelo, la misma cuenta
        que se le imprime al huésped en su itinerario.

    Devuelve (hora, origen). El origen sirve para que recepción distinga de un vistazo
    lo confirmado de lo que sigue pendiente de verdad.

    Vive aquí y no en main.py porque es la regla que decide en qué corrida va cada
    huésped: la asignación de guía y bote depende de ella, así que las dos tienen que
    leer lo mismo. Antes estaba en main.py y era solo para pintar una columna.
    """
    import catalogo_itinerario as cat
    import itinerario as _itin

    if es_entrada:
        punto = (fila.get("punto_entrada") or "").lower()
        if fila.get("hora_vuelo_entrada"):
            return fila["hora_vuelo_entrada"], "del PDF"
        if fila.get("arr_time"):
            return fila["arr_time"], "del PDF"
        if punto == "sierpe":
            return cat.SIERPE_BOTE_LLEGADA, "horario fijo de Sierpe"
        if punto == "drake":
            return None, "falta la hora del vuelo"
        return None, "falta el punto"

    punto = (fila.get("punto_salida") or "").lower()
    if punto == "sierpe":
        return cat.SIERPE_SALIDA["bote"], "horario fijo de Sierpe"
    if punto == "drake":
        logistica = _itin.calcular_logistica_salida(fila.get("hora_vuelo_salida"))
        if logistica:
            return logistica["bote"], "calculado del vuelo"
        return None, "falta la hora del vuelo"
    return None, "falta el punto"


# ---------------------------------------------------------------------------
# La asignación guardada
# ---------------------------------------------------------------------------

def asignaciones(conn, fechas=None):
    """Lo asignado, indexado por (fecha, tipo, punto, hora)."""
    if fechas:
        marcas = ",".join("?" * len(fechas))
        filas = conn.execute(
            f"SELECT * FROM traslado WHERE fecha IN ({marcas})", tuple(fechas)).fetchall()
    else:
        filas = conn.execute("SELECT * FROM traslado").fetchall()
    return {(f["fecha"], f["tipo"], f["punto"], f["hora"] or SIN_HORA): dict(f)
            for f in filas}


def asignar(conn, fecha, tipo, punto, hora, guia=None, bote=None, nota=None):
    """Guarda quién lleva una corrida. Devuelve (ok, problema).

    Se distingue "no me mandaron el dato" de "lo dejaron en Sin asignar", igual que en
    los tours: un parámetro ausente no toca lo que había, y uno vacío borra la
    asignación y la deja en NULL. Tiene que quedar en NULL y no en texto vacío, porque
    los avisos de «sin guía» buscan justamente NULL y una cadena vacía se les escaparía.
    """
    tipo = (tipo or "").strip().lower()
    if tipo not in TIPOS:
        return None, "El traslado es de entrada o de salida."
    p = normalizar_punto(punto)
    if not p:
        return None, "El punto tiene que ser Sierpe o Drake."
    if not (fecha or "").strip():
        return None, "Falta la fecha del traslado."
    hora = (hora or "").strip()

    fila = conn.execute(
        """SELECT id, guia_nombre, bote_nombre, nota FROM traslado
           WHERE fecha = ? AND tipo = ? AND punto = ? AND COALESCE(hora,'') = ?""",
        (fecha, tipo, p, hora)).fetchone()

    nuevo_guia = None if guia is None else (guia.strip() or None)
    nuevo_bote = None if bote is None else (bote.strip() or None)
    nueva_nota = None if nota is None else (nota.strip()[:300] or None)

    if fila:
        campos, valores = [], []
        if guia is not None:
            campos.append("guia_nombre = ?"); valores.append(nuevo_guia)
        if bote is not None:
            campos.append("bote_nombre = ?"); valores.append(nuevo_bote)
        if nota is not None:
            campos.append("nota = ?"); valores.append(nueva_nota)
        if campos:
            conn.execute(f"UPDATE traslado SET {', '.join(campos)} WHERE id = ?",
                         (*valores, fila["id"]))
        conn.commit()
        return fila["id"], None

    cur = conn.execute(
        """INSERT INTO traslado (fecha, tipo, punto, hora, guia_nombre, bote_nombre, nota)
           VALUES (?,?,?,?,?,?,?)""",
        (fecha, tipo, p, hora, nuevo_guia, nuevo_bote, nueva_nota))
    conn.commit()
    return cur.lastrowid, None


# ---------------------------------------------------------------------------
# Las corridas, derivadas de las reservas
# ---------------------------------------------------------------------------

def _iso(ddmmyy):
    """'11-09-26' -> '2026-09-11'. Las reservas guardan la fecha como la trae el PMS."""
    try:
        d, m, a = str(ddmmyy).split("-")
        return f"20{a}-{m}-{d}"
    except (ValueError, AttributeError):
        return None


def corridas(conn, desde, hasta, capacidades=None):
    """Los viajes de bote que hay que cubrir entre dos fechas (ISO), ya con su asignación.

    Devuelve una lista ordenada por fecha, dirección, punto y hora. Cada corrida trae
    los huéspedes que van en ella, el pax sumado y lo asignado, si hay algo.
    """
    filas_e = conn.execute(
        """SELECT conf_no, room_no, nombre_principal, adl, chl, arr_date AS fecha_pms,
                  punto_entrada, arr_time, hora_vuelo_entrada
           FROM reserva
           WHERE punto_entrada IS NOT NULL AND res_status != 'CANCELADA'""").fetchall()
    filas_s = conn.execute(
        """SELECT conf_no, room_no, nombre_principal, adl, chl, dep_date AS fecha_pms,
                  punto_salida, hora_vuelo_salida
           FROM reserva
           WHERE punto_salida IS NOT NULL AND res_status != 'CANCELADA'""").fetchall()

    grupos = {}
    for filas, tipo in ((filas_e, "entrada"), (filas_s, "salida")):
        for f in filas:
            d = dict(f)
            fecha = _iso(d["fecha_pms"])
            if not fecha or not (desde <= fecha <= hasta):
                continue
            punto = normalizar_punto(d.get("punto_entrada") if tipo == "entrada"
                                     else d.get("punto_salida"))
            if not punto:
                continue
            hora, origen = hora_de_traslado(d, tipo == "entrada")
            clave = (fecha, tipo, punto, hora or SIN_HORA)
            g = grupos.setdefault(clave, {
                "fecha": fecha, "tipo": tipo, "punto": punto,
                "hora": hora or SIN_HORA, "hora_origen": origen,
                "huespedes": [], "pax": 0,
            })
            g["huespedes"].append({
                "conf_no": d["conf_no"], "room_no": d["room_no"],
                "nombre": d["nombre_principal"],
                "pax": (d["adl"] or 0) + (d["chl"] or 0),
            })
            g["pax"] += (d["adl"] or 0) + (d["chl"] or 0)

    puestas = asignaciones(conn, sorted({k[0] for k in grupos}))
    caps = capacidades if capacidades is not None else capacidades_de_botes(conn)

    # Ordenadas por hora REAL, no alfabética: '9:00 a.m.' iría después de '14:30' si se
    # ordenaran como texto. Las que todavía no tienen hora van al final.
    def orden(k):
        m = minutos_de(k[3])
        return (k[0], k[1], k[2], 9999 if m is None else m)

    salida = []
    for clave in sorted(grupos, key=orden):
        g = dict(grupos[clave])
        puesta = puestas.get(clave) or {}
        g["guia_nombre"] = puesta.get("guia_nombre")
        g["bote_nombre"] = puesta.get("bote_nombre")
        g["nota"] = puesta.get("nota")
        g["falta"] = [x for x, v in (("guía", g["guia_nombre"]), ("bote", g["bote_nombre"]))
                      if not v]
        g["aviso_capacidad"] = _aviso_capacidad(g, caps)
        salida.append(g)
    return salida


def capacidades_de_botes(conn):
    """{nombre: capacidad}. Los que no gestiona el hotel van sin tope: un bote privado
    o externo lo pone la agencia y el lodge no decide cuánta gente le cabe."""
    return {r["nombre"]: r["capacidad_max"] for r in conn.execute(
        "SELECT nombre, capacidad_max, gestionado_por_hotel FROM bote "
        "WHERE gestionado_por_hotel = 1").fetchall()}


def _aviso_capacidad(corrida, capacidades):
    cap = capacidades.get(corrida.get("bote_nombre"))
    if not cap or not corrida.get("pax"):
        return None
    if corrida["pax"] <= cap:
        return None
    return (f"{corrida['bote_nombre']} lleva {cap} y en esta corrida van "
            f"{corrida['pax']}. Hacen falta {corrida['pax'] - cap} lugares más: "
            f"otro viaje a otra hora, u otro bote.")


def conflictos(lista):
    """Un guía o un bote en dos corridas a la MISMA hora el mismo día.

    A distinta hora no es conflicto: el lodge manda el mismo bote y el mismo guía varias
    veces al día, que es justamente lo normal por Drake. Solo choca si son simultáneas.

    'EXTERNO' y los botes privados se repiten a propósito y no se cuentan, igual que en
    los tours: no son un recurso del lodge.
    """
    avisos = []
    for i in range(len(lista)):
        for j in range(i + 1, len(lista)):
            a, b = lista[i], lista[j]
            if a["fecha"] != b["fecha"]:
                continue
            # En MINUTOS, no en letras: '9:00 a.m.' y '09:00' son el mismo momento
            # escrito distinto, y comparando los textos el choque se escapaba.
            ma, mb = minutos_de(a.get("hora")), minutos_de(b.get("hora"))
            if ma is None or mb is None or ma != mb:
                continue          # sin hora legible no se puede afirmar que chocan
            if (a["tipo"], a["punto"]) == (b["tipo"], b["punto"]):
                continue          # es la misma corrida
            for campo, etiqueta in (("guia_nombre", "guía"), ("bote_nombre", "bote")):
                v = a.get(campo)
                if not v or v != b.get(campo) or v.upper() in ("EXTERNO", "PRIVADO"):
                    continue
                avisos.append(
                    f"El {etiqueta} {v} está en dos traslados a la misma hora el "
                    f"{a['fecha']} a las {a['hora']}: {a['tipo']} por {a['punto']} "
                    f"y {b['tipo']} por {b['punto']}.")
    return avisos


def resumen(lista):
    """Cuántas corridas hay y cuántas están sin cubrir. Para el encabezado y los avisos."""
    sin_guia = [c for c in lista if not c["guia_nombre"]]
    sin_bote = [c for c in lista if not c["bote_nombre"]]
    return {
        "corridas": len(lista),
        "pax": sum(c["pax"] for c in lista),
        "sin_guia": len(sin_guia),
        "sin_bote": len(sin_bote),
        "sin_hora": len([c for c in lista if c["hora"] == SIN_HORA]),
    }
