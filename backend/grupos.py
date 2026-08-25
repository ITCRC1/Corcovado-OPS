"""Qué reservas viajan juntas, en un solo lugar.

El sistema sabe de dos maneras que varias habitaciones van juntas, y no son iguales:

  · El CÓDIGO DE BLOQUE del PMS (ej. 2608RUSSTI). Lo pone el sistema del hotel, es el
    dato más confiable, y es lo que ata a los grupos de agencia: los ocho cuartos de
    Russ Tico lo comparten. No necesita que nadie lo confirme.
  · El VÍNCULO detectado en las notas, cuando el PDF dice "Viene con rsv 594008465".
    Se guarda en la tabla grupo con un nivel de confianza y espera que recepción lo
    confirme, porque sale de un texto escrito a mano.

El reparto de restaurantes ya usaba las dos para no separar nunca a un grupo, pero la
pantalla de Reservas solo mostraba la segunda. O sea que esas ocho habitaciones se
movían juntas en el comedor y en Reservas aparecían como ocho reservas sin relación.

Este módulo existe para que haya UNA definición y todas las pantallas digan lo mismo.
"""


import unicodedata


def apellido_de(nombre_principal):
    """'Lopez Martinez, Ana' -> 'LOPEZ MARTINEZ'.

    El reporte escribe el nombre como 'Apellidos, Nombre'. Se compara sin tildes y sin
    espacios de más porque el mismo apellido llega escrito de las dos formas. Vive aquí
    porque es parte de reconocer quién viaja con quién.
    """
    base = (nombre_principal or "").split(",")[0]
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", base)
                         if not unicodedata.combining(c))
    return " ".join(sin_tildes.upper().split())


def clave_de(reserva):
    """Identifica el grupo de una reserva. Las que comparten clave viajan juntas.

    El vínculo de notas manda sobre el código de bloque: es más específico (une dos
    familias concretas dentro de un bloque grande de agencia).
    """
    if reserva.get("grupo_id"):
        return f"g{reserva['grupo_id']}"
    if reserva.get("block_code"):
        return f"b{reserva['block_code']}"
    return f"r{reserva.get('conf_no')}"


def _nombre_agencia(reserva):
    """El nombre legible de la agencia, para no mostrarle '2608RUSSTI' a nadie.

    El PDF escribe la columna como 'C- RUSS TICO TRAVEL D' —con un prefijo de tipo y a
    veces cortada por el ancho de la columna—. Se le quita el prefijo y se deja el resto
    tal cual: cortado es reconocible, inventado no.
    """
    texto = (reserva.get("company_travel_agent") or "").strip()
    for prefijo in ("C- ", "T- ", "C-", "T-"):
        if texto.startswith(prefijo):
            texto = texto[len(prefijo):].strip()
            break
    return texto


def resumen(conn, conf_nos=None):
    """Los grupos de 2 o más habitaciones, listos para mostrar.

    Devuelve un diccionario por número de reserva, para que cualquier pantalla pueda
    preguntar "¿esta reserva va con otras?" sin repetir la lógica.

    Las reservas solas no aparecen: un grupo de una habitación no es un grupo.
    """
    filas = [dict(r) for r in conn.execute(
        """SELECT r.conf_no, r.room_no, r.nombre_principal, r.adl, r.chl, r.arr_date,
                  r.dep_date, r.grupo_id, r.block_code, r.company_travel_agent,
                  g.confianza, g.confirmado_por_recepcion
           FROM reserva r LEFT JOIN grupo g ON g.id = r.grupo_id
           WHERE r.res_status != 'CANCELADA'""").fetchall()]

    porclave = {}
    for r in filas:
        porclave.setdefault(clave_de(r), []).append(r)

    por_reserva = {}
    for clave, miembros in porclave.items():
        if len(miembros) < 2:
            continue
        miembros.sort(key=lambda x: int(x["room_no"]) if (x["room_no"] or "").isdigit() else 999)
        primero = miembros[0]

        if clave.startswith("b"):
            origen = "bloque"
            etiqueta = _nombre_agencia(primero) or primero["block_code"]
            # El código de bloque no necesita confirmación: lo pone el PMS.
            confirmado, confianza = True, None
        else:
            origen = "vinculo"
            # Si todas comparten apellido es una familia y se dice así: al salonero le
            # sirve más "Familia Mora" que "Vinculadas con hab. 21".
            apellidos = {apellido_de(m["nombre_principal"]) for m in miembros}
            etiqueta = (f"Familia {next(iter(apellidos)).title()}"
                        if len(apellidos) == 1 and next(iter(apellidos))
                        else f"Vinculadas con hab. {primero['room_no']}")
            confirmado = bool(primero.get("confirmado_por_recepcion"))
            confianza = primero.get("confianza")

        grupo = {
            "clave": clave,
            "etiqueta": etiqueta,
            "origen": origen,          # 'bloque' = agencia según el PMS; 'vinculo' = nota
            "confirmado": confirmado,
            "confianza": confianza,
            "habitaciones": len(miembros),
            "pax": sum((m["adl"] or 0) + (m["chl"] or 0) for m in miembros),
            "miembros": [{
                "conf_no": m["conf_no"], "room_no": m["room_no"],
                "nombre": m["nombre_principal"],
                "pax": (m["adl"] or 0) + (m["chl"] or 0),
                "arr_date": m["arr_date"], "dep_date": m["dep_date"],
            } for m in miembros],
            # Sirve para confirmar el vínculo desde donde se muestra la etiqueta.
            "grupo_id": primero.get("grupo_id"),
        }
        for m in miembros:
            if conf_nos is None or m["conf_no"] in conf_nos:
                por_reserva[m["conf_no"]] = grupo
    return por_reserva
