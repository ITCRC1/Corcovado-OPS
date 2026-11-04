"""A qué día pertenece cada aviso.

POR QUÉ EXISTE ESTO. El dashboard es una pantalla de UN día: se elige la fecha arriba y
todo lo de abajo —quién entra, quién sale, quién está en casa, los tours— habla de ese
día. Los avisos eran lo único que no: salían todos los abiertos, de cualquier fecha,
incluidas las ya pasadas. El lodge lo pidió así: «eliminar las alertas con fechas
vencidas y solo mostrar las alertas que el usuario filtre por fechas o aparezca por
defecto».

Y no es cosmético. Medido sobre la base de hoy había trece avisos de capacidad de guía
repartidos por toda la ventana; en la pantalla del 4 de noviembre salían los trece, y
entre ellos el que sí era de hoy. Una lista de avisos que no cabe en la pantalla es una
lista que nadie lee — y entonces tampoco se lee el que importaba.

CÓMO SE AVERIGUA LA FECHA. La tabla `alerta` no tiene columna de fecha, y no se la
agrego: las filas las escriben nueve sitios distintos y una columna nueva saldría vacía
en todas las que ya existen. La fecha ya está, solo que repartida — en el tour que
originó el aviso, en la reserva a la que apunta, o escrita en el propio mensaje. Esto
la saca de donde esté, en orden de más fiable a menos:

  1. el tour (referencia_id -> tour_asignado.fecha),
  2. la amenidad (referencia_id -> amenidad_tarea.conf_no -> la estadía),
  3. la reserva (referencia_texto, que es el conf_no),
  4. un «reserva 589711467» escrito en el mensaje -> la estadía,
  5. una fecha escrita en el mensaje (2026-11-24 o 24-11-26),
  6. nada.

EL CASO 6 NO SE ESCONDE. Un aviso sin fecha —un paquete que Opera trae y el sistema no
sabe qué es, una sincronización sospechosa— no es de ningún día, así que filtrarlo por
día lo haría desaparecer para siempre. Esos salen siempre, aparte y rotulados. Es la
diferencia entre ocultar ruido y perder trabajo pendiente.
"""
import datetime
import re

# Avisos que nacen de UN tour. Su referencia_id apunta a tour_asignado, que tiene fecha.
POR_TOUR = ("CAPACIDAD_BOTE", "CAPACIDAD_GUIA", "CAMBIO_ULTIMO_MOMENTO",
            "TOUR_FUERA_DE_ESTADIA", "TOUR_EL_DIA_QUE_SE_VA")
# Avisos que nacen de una amenidad. Su referencia_id apunta a amenidad_tarea.
POR_AMENIDAD = ("ALERGIA_NO_ALIMENTARIA",)

# «(reserva 589711467, llega 22-11-26)». Pide la palabra a propósito: el aviso de
# cancelación escribe «conf 589711467» y ese NO debe resolverse contra su reserva —ver
# más abajo, en _estadia.
_RESERVA_EN_TEXTO = re.compile(r"reserva\s+(\d{5,})", re.IGNORECASE)
_ISO = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")
_DDMMYY = re.compile(r"\b(\d\d)-(\d\d)-(\d\d)\b")

CANCELADA = "cancelada"   # la reserva del aviso ya no existe para la operación


def _fecha_valida(texto):
    """ISO que de verdad es una fecha, o None. Un '99-99-99' no cuenta."""
    try:
        datetime.date.fromisoformat(texto)
    except (ValueError, TypeError):
        return None
    return texto


def _del_mensaje(mensaje):
    """La fecha escrita en el texto del aviso, en ISO. Los dos formatos que usa la casa."""
    texto = mensaje or ""
    m = _ISO.search(texto)
    if m:
        return _fecha_valida(m.group(1))
    m = _DDMMYY.search(texto)
    if m:
        d, mes, y = m.groups()
        return _fecha_valida(f"20{y}-{mes}-{d}")
    return None


def _indice_de_estadias(conn, confs):
    """{conf_no: (llegada, salida, cancelada)} en ISO, de una sola consulta.

    De una sola consulta porque el dashboard resuelve sesenta y pico avisos a la vez y
    una consulta por aviso es una consulta por aviso: hoy no se nota y el día que haya
    mil, sí.
    """
    confs = [c for c in confs if c]
    if not confs:
        return {}
    indice = {}
    for i in range(0, len(confs), 400):          # SQLite topa los parámetros de un IN
        trozo = confs[i:i + 400]
        filas = conn.execute(
            f"""SELECT conf_no, arr_date, dep_date, res_status FROM reserva
                WHERE conf_no IN ({','.join('?' for _ in trozo)})""", trozo).fetchall()
        for f in filas:
            indice[str(f["conf_no"])] = (
                _iso_de_pms(f["arr_date"]), _iso_de_pms(f["dep_date"]),
                f["res_status"] == "CANCELADA")
    return indice


def _iso_de_pms(ddmmyy):
    """'22-11-26' -> '2026-11-22'. El PMS guarda las fechas así."""
    try:
        d, m, y = (ddmmyy or "").strip().split("-")
        return _fecha_valida(f"20{y}-{m}-{d}")
    except (ValueError, AttributeError):
        return None


def _estadia(indice, conf_no):
    """La ventana de un aviso que pertenece a una reserva: (desde, hasta) o None.

    HASTA ES EL DÍA DE SALIDA, INCLUIDO. Es a propósito distinto de la regla de «en
    casa», que cuenta cabezas y excluye al que se va —esa cuenta a quién hay que dar de
    comer y dónde dormir—. Un aviso no es una cabeza: la alergia de quien se marcha
    mañana sigue importando mañana, porque desayuna aquí.

    UNA RESERVA CANCELADA NO TIENE DÍAS. El lodge pidió que las canceladas no aparezcan
    en ningún módulo, y un aviso sobre alguien que no viene es exactamente la confusión
    que había que quitar. Devuelve 'cancelada' para que quien llame lo esconda.
    """
    datos = indice.get(str(conf_no or ""))
    if not datos:
        return None
    llegada, salida, cancelada = datos
    if cancelada:
        return CANCELADA
    if not llegada:
        return None
    return (llegada, salida or llegada)


def con_fecha(conn, filas):
    """Devuelve los avisos como dicts con 'desde' y 'hasta' (ISO), o None los dos.

    Y con 'cancelada', que marca el aviso de una reserva que ya no existe para la
    operación. No se devuelve filtrado: quien llama decide qué hacer con él, y así esta
    función se puede probar viendo TODO lo que decidió, no solo lo que sobrevivió.
    """
    filas = [dict(f) for f in filas]

    ids_tour = {f["referencia_id"] for f in filas
                if f["tipo"] in POR_TOUR and f["referencia_id"]}
    ids_amenidad = {f["referencia_id"] for f in filas
                    if f["tipo"] in POR_AMENIDAD and f["referencia_id"]}

    fecha_del_tour, conf_de_la_amenidad = {}, {}
    if ids_tour:
        for t in conn.execute(
                f"""SELECT id, fecha FROM tour_asignado
                    WHERE id IN ({','.join('?' for _ in ids_tour)})""", list(ids_tour)):
            fecha_del_tour[t["id"]] = _fecha_valida(t["fecha"])
    if ids_amenidad:
        for a in conn.execute(
                f"""SELECT id, conf_no FROM amenidad_tarea
                    WHERE id IN ({','.join('?' for _ in ids_amenidad)})""",
                list(ids_amenidad)):
            conf_de_la_amenidad[a["id"]] = str(a["conf_no"] or "")

    # Todos los conf_no que van a hacer falta, en una sola pasada a la tabla de reservas.
    confs = set(conf_de_la_amenidad.values())
    for f in filas:
        if f.get("referencia_texto"):
            confs.add(str(f["referencia_texto"]))
        m = _RESERVA_EN_TEXTO.search(f.get("mensaje") or "")
        if m:
            confs.add(m.group(1))
    indice = _indice_de_estadias(conn, confs)

    salida = []
    for f in filas:
        ventana, cancelada = None, False

        # 1. El tour, que es el dato más firme: una fecha guardada, no deducida.
        if f["tipo"] in POR_TOUR:
            dia = fecha_del_tour.get(f["referencia_id"])
            if dia:
                ventana = (dia, dia)

        # 2. y 3. La reserva: por referencia o, en último lugar, por el número escrito
        # en el mensaje. Se para en la primera que resuelve.
        if not ventana:
            for conf in _confs_del_aviso(f, conf_de_la_amenidad):
                v = _estadia(indice, conf)
                if v == CANCELADA:
                    cancelada = True
                    break
                if v:
                    ventana = v
                    break

        # 4. Una fecha suelta en el texto. Es la que salva a los avisos que no apuntan
        # a nada —el de cancelación, el del punto de embarque sin confirmar—, donde la
        # única fecha que hay es la que alguien escribió en la frase.
        if not cancelada and not ventana:
            dia = _del_mensaje(f.get("mensaje"))
            if dia:
                ventana = (dia, dia)

        f["cancelada"] = cancelada
        f["desde"], f["hasta"] = ventana if ventana else (None, None)
        salida.append(f)
    return salida


def _confs_del_aviso(fila, conf_de_la_amenidad):
    """Las reservas a las que un aviso apunta, de la referencia más firme a la más floja."""
    confs = []
    if fila["tipo"] in POR_AMENIDAD and fila.get("referencia_id"):
        confs.append(conf_de_la_amenidad.get(fila["referencia_id"], ""))
    if fila.get("referencia_texto"):
        confs.append(str(fila["referencia_texto"]))
    m = _RESERVA_EN_TEXTO.search(fila.get("mensaje") or "")
    if m:
        confs.append(m.group(1))
    return [c for c in confs if c]


def repartir(conn, filas, fecha, hoy=None):
    """Reparte los avisos abiertos en los tres montones del dashboard.

      · 'del_dia'   — su ventana cubre la fecha que se está mirando.
      · 'sin_fecha' — no pertenecen a ningún día; salen siempre (ver la cabecera).
      · 'otros'     — cuántos quedan vivos en otras fechas, solo para no perderlos
                      de vista. No se enseña el texto: si se enseñara, volveríamos
                      a la lista larga que nadie lee.

    Lo vencido —ventana terminada antes de HOY— no está en ninguno de los tres. Esa es
    la parte que se pidió quitar.

    OJO CON MIRAR UN DÍA PASADO. Si se navega al 20 de octubre, los avisos de ese día sí
    salen: ahí el usuario pidió ver ese día a propósito, igual que ve sus entradas y sus
    tours. «Vencido» quiere decir que se cuela en la pantalla de hoy sin que nadie lo
    pida, no que no se pueda ir a buscarlo.

    Y 'hoy' NO decide qué se enseña, solo qué se cuenta en 'otros'. Es a propósito: el
    servidor corre en UTC y el lodge está seis horas atrás, así que entre las seis de la
    tarde y la medianoche el «hoy» del servidor ya es mañana. Si de ese dato dependiera
    lo que se ve, los avisos de la tarde desaparecerían justo cuando recepción prepara
    el día siguiente. Dependiendo solo el contador, lo peor que pasa es que el número de
    «otras fechas» se quede corto unas horas.
    """
    hoy = hoy or datetime.date.today().isoformat()
    del_dia, sin_fecha, otros = [], [], 0
    for a in con_fecha(conn, filas):
        if a["cancelada"]:
            continue
        if not a["desde"]:
            sin_fecha.append(a)
            continue
        if a["desde"] <= fecha <= a["hasta"]:
            del_dia.append(a)
        elif a["hasta"] >= hoy:
            otros += 1
    return del_dia, sin_fecha, otros
