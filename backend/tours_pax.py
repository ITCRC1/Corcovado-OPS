"""
Cuánta gente de una reserva va a un tour.

QUÉ PROBLEMA RESUELVE
---------------------
El reporte solo sabe cuánta gente hay en la HABITACIÓN, así que hasta ahora todos los
tours de una reserva se contaban con ese número. En la práctica no es así: de dos
huéspedes, uno se queda y el otro va al manglar. Antes había dos salidas y las dos
mienten — dejarlo en 2 compra una entrada de parque de más y llena un cupo de bote que
está libre; quitar el tour entero borra al que SÍ va.

Ahora el pax es de cada tour y se puede escribir a mano desde la agenda.

POR QUÉ LLEVA UNA MARCA
-----------------------
Cada importación borra y rehace los tours de la reserva desde la fuente. Sin una marca,
el número escrito a mano volvería a ser «la habitación entera» en el siguiente ciclo, sin
avisar. `pax_editado_a_mano` es lo que lo protege, igual que `origen='MANUAL'` protege a
los tours agregados a mano y `editado_a_mano` a las amenidades. El cargador lo respeta y
lo arrastra si el tour se mueve de día.

VACÍO NO ES CERO
----------------
Mandar el campo vacío QUITA la corrección y devuelve el tour a lo que diga la reserva.
Sin esa distinción no habría forma de deshacer: el número quedaría clavado para siempre
aunque cambiara la habitación. Es la misma regla que la hora de mesa en restaurantes.

Cero no se acepta. Un tour al que no va nadie se quita con la papelera: así deja de
ocupar cupo de guía y de bote y sale de la entrada del parque, que es lo que de verdad
hace falta que pase.
"""


class PaxInvalido(ValueError):
    """Lo que escribió la persona no se puede usar. El mensaje es para ella."""


def decidir_pax(texto, en_la_habitacion):
    """Qué pax queda y si cuenta como puesto a mano. (pax, a_mano).

    `texto` es lo que vino del formulario, tal cual —una cadena, posiblemente vacía—,
    porque la diferencia entre «vacío» y «0» es justo la que hay que conservar y se
    pierde en cuanto se convierte a número antes de mirarla.
    """
    tope = int(en_la_habitacion or 0)
    texto = (texto or "").strip()
    if not texto:
        # Sin corrección: vale lo que diga la reserva. El máximo con 1 es para la
        # reserva que llega sin adultos ni niños cargados, que existe: un tour con pax 0
        # desaparecería de las cuentas sin que nadie lo haya pedido.
        return max(1, tope), 0
    try:
        pax = int(texto)
    except ValueError:
        raise PaxInvalido("El pax tiene que ser un número.")
    if pax < 1:
        raise PaxInvalido(
            "Si no va nadie, quita el tour con la papelera en vez de dejarlo en cero: "
            "así deja de ocupar cupo de guía y de bote, y sale de la entrada del parque.")
    if tope and pax > tope:
        raise PaxInvalido(
            f"En la habitación hay {tope} persona(s) y no pueden ir {pax} al tour. "
            f"Si de verdad son {pax}, primero hay que corregir la reserva.")
    return pax, 1


def pax_sinac_pendiente(conn, codigo, fecha):
    """Cuántas entradas al parque hacen falta para ese tour ese día, guía incluido.

    Se recalcula SUMANDO en vez de llevar una cuenta que se va corrigiendo: así queda
    bien aunque antes hubiera quedado mal. Está en un solo sitio porque lo usan las tres
    cosas que mueven el total —agregar un tour, quitarlo y editar el pax— y tres copias
    de la misma consulta es donde una se queda vieja.

    EL GUÍA CUENTA. La importación suma +1 por salida (una entrada para el guía, no una
    por familia: si varias reservas van al mismo tour el mismo día salen con un guía
    solo). Este recálculo NO lo hacía, así que agregar o quitar un tour desde la agenda
    bajaba el total en uno y se compraba una entrada de menos para el guía — sin aviso, y
    con quince días de plazo para descubrirlo. Ahora las cuatro vías dicen lo mismo.

    Si no va nadie el total es cero, sin entrada de guía: una salida que no existe no
    lleva guía, y quitar el último tour tiene que poder dejar la entrada en cero para que
    la pantalla del SINAC la borre o la marque como sobrante.
    """
    pax = conn.execute(
        """SELECT COALESCE(SUM(ta.pax), 0) t FROM tour_asignado ta
           JOIN reserva r2 ON r2.conf_no = ta.conf_no
           WHERE ta.tour_codigo = ? AND ta.fecha = ?
             AND IFNULL(ta.conf_entrada_sinac,'') = ''
             AND r2.res_status != 'CANCELADA'""",
        (codigo, fecha)).fetchone()["t"]
    return pax + 1 if pax else 0


def cambiar_pax(conn, tour_id, texto):
    """Escribe el pax de un tour y deja el resto cuadrado. No hace commit.

    Devuelve un diccionario con lo que pasó, o None si el tour ya no existe. Lanza
    PaxInvalido si el número no sirve, y en ese caso no escribe nada.
    """
    ta = conn.execute(
        """SELECT ta.id, ta.tour_codigo, ta.fecha, ta.pax, r.adl, r.chl
           FROM tour_asignado ta JOIN reserva r ON r.conf_no = ta.conf_no
           WHERE ta.id = ?""", (tour_id,)).fetchone()
    if not ta:
        return None
    en_la_habitacion = (ta["adl"] or 0) + (ta["chl"] or 0)
    pax, a_mano = decidir_pax(texto, en_la_habitacion)

    conn.execute("UPDATE tour_asignado SET pax = ?, pax_editado_a_mano = ? WHERE id = ?",
                 (pax, a_mano, tour_id))

    # Las alertas viejas de capacidad son de otro escenario: con menos gente, el bote que
    # no alcanzaba puede alcanzar. Se dan por resueltas y se vuelve a validar fuera.
    conn.execute(
        "UPDATE alerta SET resuelto = 1 WHERE referencia_id = ? "
        "AND tipo IN ('CAPACIDAD_GUIA','CAPACIDAD_BOTE')", (tour_id,))

    # La entrada del parque se compra por cabeza. Si cambia el pax y no se recalcula, se
    # compran tiquetes de más o de menos y se descubre con 15 días de plazo encima.
    sinac = None
    entrada = conn.execute(
        """SELECT id FROM entrada_sinac
           WHERE tour_codigo = ? AND fecha = ? AND IFNULL(conf_entrada,'') = ''""",
        (ta["tour_codigo"], ta["fecha"])).fetchone()
    if entrada:
        total = pax_sinac_pendiente(conn, ta["tour_codigo"], ta["fecha"])
        conn.execute("UPDATE entrada_sinac SET pax_total_grupo = ? WHERE id = ?",
                     (total, entrada["id"]))
        sinac = {"pax_total": total}

    return {"pax": pax, "editado_a_mano": bool(a_mano),
            "pax_habitacion": en_la_habitacion, "sinac": sinac,
            "tour_codigo": ta["tour_codigo"], "fecha": ta["fecha"]}
