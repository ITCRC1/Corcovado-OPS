"""
La puerta por la que el portal del huésped pregunta si una reserva existe.

El portal (otro sistema, otra base, otro despliegue) necesita comprobar que quien se
está registrando es de verdad un huésped. Le manda tres datos y recibe un sí o un no.

POR QUÉ LA COMPARACIÓN SE HACE AQUÍ Y NO ALLÁ:
el portal no recibe la lista de reservas. Solo pregunta por una y solo obtiene datos si
acertó los tres campos. Así el portal nunca guarda información de huéspedes que no se
registraron, y una filtración suya no expone la operación del lodge. Además, quien sabe
en qué formato están guardados los nombres y las fechas es este sistema, no el portal.

POR QUÉ TRES DATOS Y NO SOLO EL NÚMERO:
el número de reserva no es un secreto —viaja en el voucher, lo tiene la agencia— y los
del PMS son consecutivos, así que quien conozca uno puede probar los vecinos. Pedir
además el apellido y la fecha de llegada convierte el adivinar en algo impracticable.
Es el mismo esquema que pide una aerolínea.

Este módulo NO escribe nada en la base. Solo lee.
"""
import os
import unicodedata

# Secreto compartido con el portal. Sin él la puerta queda cerrada (404), igual que
# las rutas de sincronización entre estaciones: una puerta que lee datos de huéspedes
# no debe quedar abierta en una instalación que no la necesita.
PORTAL_TOKEN = (os.environ.get("HOTEL_PORTAL_TOKEN") or "").strip()


def habilitado():
    return bool(PORTAL_TOKEN)


def token_valido(recibido):
    import secrets
    if not PORTAL_TOKEN or not recibido:
        return False
    return secrets.compare_digest(recibido, PORTAL_TOKEN)


# ---------------------------------------------------------------------------
# Fechas
# ---------------------------------------------------------------------------

def iso_a_ddmmyy(iso):
    """'2026-09-03' -> '03-09-26', que es como guarda las fechas este sistema."""
    try:
        y, m, d = iso.strip().split("-")
        if len(y) != 4:
            return None
        return f"{int(d):02d}-{int(m):02d}-{y[2:]}"
    except (ValueError, AttributeError):
        return None


def ddmmyy_a_iso(ddmmyy):
    """'03-09-26' -> '2026-09-03'. El portal trabaja en ISO."""
    try:
        d, m, y = ddmmyy.strip().split("-")
        return f"20{y}-{int(m):02d}-{int(d):02d}"
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Apellidos
# ---------------------------------------------------------------------------

def _normalizar(texto):
    """Deja el nombre comparable: sin tildes, en mayúsculas, y los separadores del
    reporte convertidos en espacios.

    El PDF del PMS escribe el nombre como 'Apellidos, Nombre', y algunos reportes usan
    'APELLIDO/NOMBRE'. Se aceptan los dos porque no vale la pena que un ingreso falle
    por el separador que usó el reporte de ese día.
    """
    base = (texto or "").replace(",", " ").replace("/", " ").replace(".", " ")
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", base)
                         if not unicodedata.combining(c))
    return " ".join(sin_tildes.upper().split())


def apellido_coincide(escrito, nombre_reserva):
    """Si el apellido que escribió el huésped corresponde al nombre de la reserva.

    Se acepta que escriba UNO de sus apellidos —'Mora' cuando la reserva dice
    'Mora Jiménez, Ana'— porque es lo que va a pasar en la práctica. Exigir el nombre
    completo y exacto generaría llamadas a recepción sin ganar seguridad real: el número
    de reserva y la fecha de llegada ya están identificando.

    Lo que NO se acepta es una coincidencia parcial de palabra: 'Mor' no vale por 'Mora'.
    """
    a = _normalizar(escrito)
    b = _normalizar(nombre_reserva)
    if not a or not b:
        return False
    palabras = set(b.split())
    return all(p in palabras for p in a.split())


# ---------------------------------------------------------------------------
# La consulta
# ---------------------------------------------------------------------------

def verificar(conn, conf_no, apellido, llegada_iso):
    """Comprueba una reserva. Devuelve el diccionario que espera el portal.

    Siempre responde lo mismo cuando falla —{"encontrada": False}— sin decir en qué
    campo falló. Distinguir 'ese número no existe' de 'el apellido no coincide' le
    confirmaría a un extraño que el número es válido, que es justo lo que no queremos.
    """
    conf_no = (conf_no or "").strip()
    dd = iso_a_ddmmyy(llegada_iso or "")
    if not conf_no or not apellido or not dd:
        return {"encontrada": False}

    fila = conn.execute(
        """SELECT conf_no, nombre_principal, room_no, arr_date, dep_date, adl, chl,
                  res_status
           FROM reserva WHERE conf_no = ?""",
        (conf_no,)).fetchone()
    if not fila:
        return {"encontrada": False}

    r = dict(fila)

    # Una reserva cancelada no da acceso al portal.
    if (r.get("res_status") or "").upper() == "CANCELADA":
        return {"encontrada": False}

    if r.get("arr_date") != dd:
        return {"encontrada": False}

    if not apellido_coincide(apellido, r.get("nombre_principal")):
        return {"encontrada": False}

    return {
        "encontrada": True,
        "reserva": {
            "conf_no": r["conf_no"],
            "nombre": r["nombre_principal"],
            "habitacion": r["room_no"],
            "llegada": ddmmyy_a_iso(r["arr_date"]),
            "salida": ddmmyy_a_iso(r["dep_date"]) if r.get("dep_date") else None,
            "adultos": r.get("adl") or 0,
            "ninos": r.get("chl") or 0,
        },
    }
