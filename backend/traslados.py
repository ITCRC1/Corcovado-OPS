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
# El BT («boat transfer») es el tercer tipo: un viaje de bote EXTRA, a mitad de estadía,
# que no es ni la llegada ni la salida del huésped. Ver boat_transfer.py.
TIPOS = ("entrada", "salida", "extra")

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

    LA REGLA, tal como la dio el lodge: «cuando sea un ingreso que se indique la misma
    hora, y cuando sea una salida dos horas antes de lo que diga la reserva; esto en el
    caso exclusivo de Drake. Para Sierpe se mantiene la hora fija».

      · Sierpe → horario fijo del bote, SIEMPRE. Llegada y salida.
      · Drake, llegada → la hora del vuelo, tal cual; sin vuelo no se puede saber.
      · Drake, salida  → el bote, dos horas antes del vuelo, la misma cuenta que se le
        imprime al huésped en su itinerario.

    EL PUNTO MANDA SOBRE LO QUE DIGA LA RESERVA, y por eso se mira primero. Antes era al
    revés —cualquier hora escrita ganaba— y por Sierpe salían horas de la tarde: la
    habitación 09 del 2 de noviembre a las 14:20, y las 21 y 13 del día 3 a las 15:13 y
    15:11. Por Sierpe el bote sale a la misma hora para todos, así que esas horas eran
    otra cosa —el check-in del PMS— y además partían en tres corridas distintas a gente
    que viaja en el mismo bote.

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
        if punto == "sierpe":
            return cat.SIERPE_BOTE_LLEGADA, "horario fijo de Sierpe"
        if punto == "drake":
            # La hora del vuelo SIN tocar: en el ingreso el bote espera al avión.
            if fila.get("hora_vuelo_entrada"):
                return fila["hora_vuelo_entrada"], "del PDF"
            if fila.get("arr_time"):
                return fila["arr_time"], "del PDF"
            return None, "falta la hora del vuelo"
        # Sin punto confirmado no hay regla que aplicar, pero si la reserva trae una
        # hora escrita vale más que nada: es lo único que se sabe.
        if fila.get("hora_vuelo_entrada"):
            return fila["hora_vuelo_entrada"], "del PDF"
        if fila.get("arr_time"):
            return fila["arr_time"], "del PDF"
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


def asignar(conn, fecha, tipo, punto, hora, guia=None, bote=None, nota=None,
            capitan=None, ayudante=None):
    """Guarda quién lleva una corrida. Devuelve (ok, problema).

    Se distingue "no me mandaron el dato" de "lo dejaron en Sin asignar", igual que en
    los tours: un parámetro ausente no toca lo que había, y uno vacío borra la
    asignación y la deja en NULL. Tiene que quedar en NULL y no en texto vacío, porque
    los avisos de «sin guía» buscan justamente NULL y una cadena vacía se les escaparía.

    El CAPITÁN y el AYUDANTE salen los dos del catálogo de capitanes: en el lodge la
    misma persona hace de una cosa o de la otra según con quién le toque el bote.
    """
    tipo = (tipo or "").strip().lower()
    if tipo not in TIPOS:
        return None, "El traslado es de entrada, de salida o un BT."
    # El BT no sale de un muelle fijo: su «punto» es la habitación que lo pidió, porque
    # es un viaje de ESA reserva y no de todos los que coinciden en hora.
    p = (punto or "").strip() if tipo == "extra" else normalizar_punto(punto)
    if not p:
        return None, ("Falta la habitación del BT." if tipo == "extra"
                      else "El punto tiene que ser Sierpe o Drake.")
    if not (fecha or "").strip():
        return None, "Falta la fecha del traslado."
    hora = (hora or "").strip()

    fila = conn.execute(
        """SELECT id, guia_nombre, bote_nombre, capitan_nombre, ayudante_nombre, nota
           FROM traslado
           WHERE fecha = ? AND tipo = ? AND punto = ? AND COALESCE(hora,'') = ?""",
        (fecha, tipo, p, hora)).fetchone()

    nuevo_guia = None if guia is None else (guia.strip() or None)
    nuevo_bote = None if bote is None else (bote.strip() or None)
    nuevo_capitan = None if capitan is None else (capitan.strip() or None)
    nuevo_ayudante = None if ayudante is None else (ayudante.strip() or None)
    nueva_nota = None if nota is None else (nota.strip()[:300] or None)

    # NADIE VA DE CAPITÁN Y DE AYUDANTE EN LA MISMA CORRIDA.
    #
    # Se comprueba contra lo que VA A QUEDAR guardado, no solo contra lo que llega en
    # esta llamada. Los dos selectores se cambian por separado: poner de ayudante a quien
    # ya era capitán llega aquí con el capitán ausente, y mirando solo los parámetros se
    # dejaría pasar. El resultado sería una corrida con una sola persona escrita dos
    # veces, y en el muelle faltaría alguien.
    final_capitan = nuevo_capitan if capitan is not None else (
        fila["capitan_nombre"] if fila else None)
    final_ayudante = nuevo_ayudante if ayudante is not None else (
        fila["ayudante_nombre"] if fila else None)
    if final_capitan and final_capitan == final_ayudante:
        return None, (f"{final_capitan} no puede ir de capitán y de ayudante "
                      f"en la misma corrida.")

    if fila:
        campos, valores = [], []
        if guia is not None:
            campos.append("guia_nombre = ?"); valores.append(nuevo_guia)
        if bote is not None:
            campos.append("bote_nombre = ?"); valores.append(nuevo_bote)
        if capitan is not None:
            campos.append("capitan_nombre = ?"); valores.append(nuevo_capitan)
        if ayudante is not None:
            campos.append("ayudante_nombre = ?"); valores.append(nuevo_ayudante)
        if nota is not None:
            campos.append("nota = ?"); valores.append(nueva_nota)
        if campos:
            conn.execute(f"UPDATE traslado SET {', '.join(campos)} WHERE id = ?",
                         (*valores, fila["id"]))
        conn.commit()
        return fila["id"], None

    cur = conn.execute(
        """INSERT INTO traslado (fecha, tipo, punto, hora, guia_nombre, bote_nombre,
                                 capitan_nombre, ayudante_nombre, nota)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (fecha, tipo, p, hora, nuevo_guia, nuevo_bote, nuevo_capitan, nuevo_ayudante,
         nueva_nota))
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

    # --- Los BT: viajes de bote EXTRA que pide una reserva ---
    #
    # Van en la MISMA lista que las demás corridas a propósito. Lo pidió el lodge: «debe
    # ser cargada en la parte de transporte para ser asignada el capitán o ayudante».
    # Tenerlos en otra tabla de la pantalla sería tener dos sitios donde mirar quién
    # maneja un bote ese día, y el que se mira menos es el que se olvida.
    #
    # Cada BT es una corrida PROPIA de su reserva, no se junta con nadie: el huésped lo
    # pidió para él, normalmente para engancharse con otro operador a una hora concreta.
    # Por eso el «punto» de la clave es su habitación.
    for f in conn.execute(
            """SELECT e.conf_no, e.fecha, e.hora, e.nota,
                      r.room_no, r.nombre_principal, r.adl, r.chl
               FROM traslado_extra e JOIN reserva r ON r.conf_no = e.conf_no
               WHERE e.fecha BETWEEN ? AND ? AND r.res_status != 'CANCELADA'
               ORDER BY e.fecha, e.hora, r.room_no""", (desde, hasta)).fetchall():
        d = dict(f)
        punto = str(d["room_no"] or d["conf_no"])
        clave = (d["fecha"], "extra", punto, d["hora"] or SIN_HORA)
        g = grupos.setdefault(clave, {
            "fecha": d["fecha"], "tipo": "extra", "punto": punto,
            "hora": d["hora"] or SIN_HORA,
            "hora_origen": "de la nota" if d["hora"] else "no dice la hora",
            "huespedes": [], "pax": 0, "nota_bt": d["nota"],
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
        g["capitan_nombre"] = puesta.get("capitan_nombre")
        g["ayudante_nombre"] = puesta.get("ayudante_nombre")
        g["nota"] = puesta.get("nota")
        # Lo que la reserva escribió del BT: con quién se engancha, a qué hora lo
        # recogen. Quien asigna el bote lo necesita y no está en ningún otro sitio.
        g.setdefault("nota_bt", None)
        # El AYUDANTE no entra en 'falta': no todas las corridas llevan uno —un bote
        # chico con dos pasajeros va solo con su capitán— así que contarlo como faltante
        # pintaría de amarillo media pantalla todos los días y el aviso dejaría de
        # significar algo.
        g["falta"] = [x for x, v in (("guía", g["guia_nombre"]),
                                     ("bote", g["bote_nombre"]),
                                     ("capitán", g["capitan_nombre"]))
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
    # El ayudante no se cuenta: no todas las corridas llevan uno. Ver 'falta'.
    sin_capitan = [c for c in lista if not c.get("capitan_nombre")]
    return {
        "corridas": len(lista),
        "pax": sum(c["pax"] for c in lista),
        "sin_guia": len(sin_guia),
        "sin_bote": len(sin_bote),
        "sin_capitan": len(sin_capitan),
        "sin_hora": len([c for c in lista if c["hora"] == SIN_HORA]),
    }


# ---------------------------------------------------------------------------
# Las salidas de TOUR que van en bote
# ---------------------------------------------------------------------------
#
# Un tour acuático es un viaje de bote igual que una corrida de muelle, y el lodge pidió
# verlos todos en la misma pantalla: «se asignan en la parte de transportes, lo que son
# tours acuáticos que necesitan bote».
#
# No son una corrida de la tabla 'traslado': viven en tour_asignado, que es donde ya
# estaban el guía y el bote, y donde la agenda valida la capacidad por grupo. Lo que
# cambia es QUIÉN escribe cada columna: el bote, el capitán y el ayudante se eligen en
# Transporte; el guía, en la Agenda. Cada pantalla enseña la mitad de la otra en solo
# lectura, así que no hay dos sitios donde se pueda escribir lo mismo.
#
# La unidad es (fecha, tour, grupo), no la reserva: el grupo es justamente lo que el
# lodge usa para partir un tour que no cabe en un guía o en un bote, y todas las
# reservas del mismo grupo suben al mismo bote.

def salidas_de_tour(conn, desde, hasta):
    """Los tours que llevan bote entre dos fechas (ISO), agrupados por fecha/tour/grupo."""
    filas = conn.execute(
        """SELECT ta.fecha, ta.tour_codigo, ta.grupo_operativo, ta.pax, ta.es_privado,
                  ta.conf_no,
                  ta.guia_nombre, ta.bote_nombre, ta.capitan_nombre, ta.ayudante_nombre,
                  r.room_no, r.nombre_principal,
                  tc.nombre AS tour_nombre, tc.horario_inicio
           FROM tour_asignado ta
           JOIN tour_catalogo tc ON tc.codigo = ta.tour_codigo
           JOIN reserva r ON r.conf_no = ta.conf_no
           WHERE tc.requiere_bote = 1 AND ta.fecha BETWEEN ? AND ?
             AND r.res_status != 'CANCELADA'
           ORDER BY ta.fecha, tc.horario_inicio, ta.tour_codigo, ta.es_privado,
                    ta.grupo_operativo, r.room_no""",
        (desde, hasta)).fetchall()

    grupos = {}
    orden = []
    for f in filas:
        d = dict(f)
        # LA MODALIDAD ENTRA EN LA CLAVE, igual que el grupo. Un PNC privado y un PNC
        # compartido el mismo día son DOS salidas: el privado lleva su propio bote y su
        # propio guía, que es justamente para lo que se vende. Juntarlos daría una sola
        # corrida, un solo bote asignado, y el día del tour habría gente esperando.
        #
        # Y UNA SALIDA PRIVADA ES POR RESERVA. Privado quiere decir «sin nadie más»: dos
        # reservas distintas que compran el mismo tour privado el mismo día son dos
        # salidas, no una. Medido en los datos reales del lodge: el 19 de noviembre el
        # PNC privado son la habitación 12 y la 11, dos familias que no se conocen —
        # juntarlas en un bote es exactamente lo que pagaron por evitar.
        #
        # Si dos habitaciones privadas sí viajan juntas —una familia en dos cuartos—, se
        # les pone EL MISMO BOTE desde Transporte. Siguen siendo dos renglones, que es lo
        # honesto, y la validación de capacidad las suma porque suma por bote.
        privado = 1 if d["es_privado"] else 0
        clave = (d["fecha"], d["tour_codigo"], privado, d["grupo_operativo"] or "A",
                 d["conf_no"] if privado else "")
        if clave not in grupos:
            grupos[clave] = {
                "fecha": d["fecha"], "tour_codigo": d["tour_codigo"],
                "tour_nombre": d["tour_nombre"], "grupo": d["grupo_operativo"] or "A",
                "privado": bool(privado),
                "conf_no": d["conf_no"] if privado else None,
                "hora": d["horario_inicio"] or "",
                "habitaciones": [], "pax": 0,
                # Se recogen los DISTINTOS valores del grupo en vez de quedarse con el
                # primero. El bote, el capitán y el ayudante se escriben a todo el grupo
                # de una vez, así que normalmente hay uno solo; pero el guía viene de la
                # Agenda fila por fila y puede quedar distinto. Enseñar solo el primero
                # escondería justamente el caso que hay que arreglar.
                "_guias": [], "_botes": [], "_capitanes": [], "_ayudantes": [],
            }
            orden.append(clave)
        g = grupos[clave]
        g["habitaciones"].append({"room_no": d["room_no"],
                                  "nombre": d["nombre_principal"],
                                  "pax": d["pax"] or 0})
        g["pax"] += d["pax"] or 0
        for campo, bolsa in (("guia_nombre", "_guias"), ("bote_nombre", "_botes"),
                             ("capitan_nombre", "_capitanes"),
                             ("ayudante_nombre", "_ayudantes")):
            v = d.get(campo)
            if v and v not in g[bolsa]:
                g[bolsa].append(v)

    salida = []
    for clave in orden:
        g = grupos[clave]
        for campo, bolsa in (("guia_nombre", "_guias"), ("bote_nombre", "_botes"),
                             ("capitan_nombre", "_capitanes"),
                             ("ayudante_nombre", "_ayudantes")):
            g[campo] = " · ".join(g.pop(bolsa)) or None
        g["falta"] = [x for x, v in (("guía", g["guia_nombre"]),
                                     ("bote", g["bote_nombre"]),
                                     ("capitán", g["capitan_nombre"]))
                      if not v]
        salida.append(g)
    return salida


def asignar_tour(conn, fecha, tour_codigo, grupo, bote=None, capitan=None,
                 ayudante=None, privado=False, conf_no=None):
    """Pone bote, capitán y ayudante a TODAS las reservas de (fecha, tour, privado, grupo).

    Devuelve (cuántas filas se tocaron, problema). Se escribe al grupo entero porque el
    grupo es el que sube al bote: dejar una reserva del grupo con otro bote sería gente
    del mismo tour esperando en dos muelles.

    La MODALIDAD es parte de la llave, no un filtro de adorno: si no estuviera, poner el
    bote del PNC compartido se lo pondría también al PNC privado del mismo día, que es
    exactamente lo que el huésped pagó por no compartir. Y si es privada se acota además
    a SU reserva, por lo mismo: dos privados del mismo día son dos salidas.

    El guía NO se toca aquí. Se elige en la Agenda y esta pantalla solo lo enseña.
    """
    fecha = (fecha or "").strip()
    tour_codigo = (tour_codigo or "").strip()
    grupo = (grupo or "A").strip() or "A"
    priv = 1 if privado else 0
    if not fecha or not tour_codigo:
        return 0, "Falta la fecha o el tour."

    donde = ("fecha = ? AND tour_codigo = ? AND COALESCE(grupo_operativo,'A') = ? "
             "AND COALESCE(es_privado,0) = ?")
    args = [fecha, tour_codigo, grupo, priv]
    if priv and conf_no:
        donde += " AND conf_no = ?"
        args.append(conf_no)

    filas = conn.execute(
        f"SELECT id, capitan_nombre, ayudante_nombre FROM tour_asignado WHERE {donde}",
        args).fetchall()
    if not filas:
        return 0, "Ese tour no está en la agenda de esa fecha."

    nuevo_bote = None if bote is None else (bote.strip() or None)
    nuevo_capitan = None if capitan is None else (capitan.strip() or None)
    nuevo_ayudante = None if ayudante is None else (ayudante.strip() or None)

    # La misma regla que en una corrida de muelle, y por la misma razón: se mira lo que
    # VA A QUEDAR guardado, no lo que llega, porque los dos selectores se cambian por
    # separado. Ver el comentario largo en asignar().
    #
    # Se revisan TODAS las filas del grupo, no solo la primera: si el grupo quedó con
    # tripulación despareja —una fila vieja de antes de dividirlo, por ejemplo—, mirar
    # una sola dejaría pasar el choque en las demás.
    for f in filas:
        a = dict(f)
        final_capitan = nuevo_capitan if capitan is not None else a["capitan_nombre"]
        final_ayudante = (nuevo_ayudante if ayudante is not None
                          else a["ayudante_nombre"])
        if final_capitan and final_capitan == final_ayudante:
            return 0, (f"{final_capitan} no puede ir de capitán y de ayudante "
                       f"en la misma salida.")

    campos, valores = [], []
    if bote is not None:
        campos.append("bote_nombre = ?"); valores.append(nuevo_bote)
    if capitan is not None:
        campos.append("capitan_nombre = ?"); valores.append(nuevo_capitan)
    if ayudante is not None:
        campos.append("ayudante_nombre = ?"); valores.append(nuevo_ayudante)
    if not campos:
        return 0, None

    conn.execute(
        f"UPDATE tour_asignado SET {', '.join(campos)} WHERE {donde}",
        (*valores, *args))
    conn.commit()
    return len(filas), None
