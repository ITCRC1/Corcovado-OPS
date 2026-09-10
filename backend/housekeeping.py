"""
Housekeeping: la lavandería.

CÓMO FUNCIONA, Y POR QUÉ ASÍ
----------------------------
Igual que el spa, y a propósito: el huésped **pide** por un enlace que ya sabe quién es, y
housekeeping **confirma**. Reemplaza al formulario de Google que hoy se le manda por
WhatsApp.

Lo que ese formulario no podía hacer, y esto sí:

  · No le pregunta el nombre ni la habitación. Eran dos de sus seis preguntas y las dos
    eran el error fácil: quien escribía mal su cuarto no recibía su ropa. Y si el huésped
    se cambia de habitación, la pantalla muestra dónde está AHORA.
  · Solo le ofrece días de su estadía, y el enlace deja de servir cuando la reserva
    termina.
  · Le dice si su ropa VUELVE EL MISMO DÍA. El formulario le preguntaba a qué hora quería
    la recolección y no le contestaba nada; el reclamo llegaba al día siguiente. Este es
    el aviso que le da valor al huésped, igual que el de choques en el spa: sin algo a
    cambio, un formulario que solo le sirve al hotel no se llena.
  · Las cantidades son un número. La cuadrícula del formulario llegaba hasta 6 porque es
    lo que da Google Forms, no porque el hotel lave de a seis.

  · Le dice CUÁNTO va a pagar antes de mandar la ropa: subtotal, IVA y total, calculados
    con el precio de cada prenda y la cantidad que eligió. El formulario no tenía precios,
    así que el número aparecía por primera vez en la cuenta del cuarto.

LA CUENTA
---------
Todo en CENTAVOS enteros, nunca en decimales: sumando floats, doce veces 2.10 da
25.199999999999996 y ese número acabaría impreso en la cuenta de un huésped. El impuesto
se saca una vez sobre el subtotal, con `Decimal` y ROUND_HALF_UP, porque el `round()` de
Python redondea al par y se llevaría un céntimo por pedido.

Y la cuenta se CONGELA en el pedido —precio, porcentaje y total—, igual que el nombre de
la prenda y el plazo del mismo día: cambiar la lista o el IVA afecta a los pedidos nuevos,
nunca a los ya cotizados.
"""
import os
import json
import secrets
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CONFIG_PATH = os.path.join(
    os.environ.get("HOTEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data"),
    "config_housekeeping.json",
)

# Los valores del lodge. Se cambian desde la pantalla de Housekeeping.
CONFIG_POR_DEFECTO = {
    # Entre qué horas pasa housekeeping a recoger.
    "abre": "07:00",
    "cierra": "18:00",
    # Cada cuántos minutos se le ofrecen horas al huésped. 30 da opciones sin marear.
    "paso_minutos": 30,
    # La hora TOPE para que la ropa vuelva el mismo día. Lo recogido después vuelve al día
    # siguiente, y al huésped se le dice en el momento de pedirlo, no después.
    #
    # Este valor es una suposición razonable puesta para arrancar: hay que ajustarlo con
    # housekeeping. Cambiarlo NO altera lo que ya se le prometió a un huésped — eso queda
    # guardado en cada pedido.
    "hora_tope_mismo_dia": "09:00",
    # Tope por prenda. No es una regla del hotel: ataja el dedazo de quien teclea 111 en
    # vez de 11 y deja a housekeeping esperando un bulto que no existe.
    "max_por_prenda": 99,
    # El impuesto que se le suma al subtotal. Va aquí y no escrito en el código porque el
    # IVA ya cambió antes en Costa Rica y va a volver a cambiar; el día que pase, es un
    # campo de la pantalla y no un despliegue.
    #
    # Los precios del catálogo se cargan SIN impuesto: esto se les suma al final.
    "iva_porcentaje": 13,
    # El código del ÚNICO enlace que se le manda al huésped. Vacío hasta que alguien
    # abre la pantalla la primera vez; ver token_general().
    "token_general": "",
}

# La moneda en que se le cotiza al huésped. Está aquí, en un solo sitio, para que
# cambiarla sea una línea: los huéspedes del lodge son internacionales y la página abre en
# inglés, así que se cotiza en dólares.
MONEDA = "$"

ESTADOS = ("SOLICITADO", "CONFIRMADO", "RECOGIDO", "ENTREGADO", "CANCELADO")

# El camino normal de un pedido. Se usa para no dejar saltar pasos hacia atrás sin querer:
# de ENTREGADO no se vuelve a RECOGIDO por un toque de más en el teléfono.
ORDEN_ESTADOS = {"SOLICITADO": 0, "CONFIRMADO": 1, "RECOGIDO": 2, "ENTREGADO": 3}

# Los que siguen vivos: los que housekeeping tiene que atender.
ESTADOS_ABIERTOS = ("SOLICITADO", "CONFIRMADO", "RECOGIDO")


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def cargar_config():
    cfg = dict(CONFIG_POR_DEFECTO)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8-sig") as f:
                guardada = json.load(f)
            if isinstance(guardada, dict):
                cfg.update({k: v for k, v in guardada.items() if k in CONFIG_POR_DEFECTO})
        except (OSError, ValueError):
            # Un archivo torcido no puede dejar a housekeeping sin horario: se siguen
            # usando los valores por defecto.
            pass
    return cfg


def _escribir_config(cfg):
    """Escribe la configuración tal cual, sin validar horarios.

    La usa el enlace general: cambiarlo no tiene nada que ver con el horario, y pasarlo
    por guardar_config() lo obligaría a revalidar horas que nadie tocó.
    """
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in cfg.items() if k in CONFIG_POR_DEFECTO},
                  f, ensure_ascii=False, indent=2)
    return cfg


def guardar_config(cfg):
    limpia = dict(CONFIG_POR_DEFECTO)
    # El enlace general NO se toca al guardar el horario. `limpia` arranca de los
    # valores por defecto, así que sin esto guardar el horario borraría el enlace y
    # todos los que ya se mandaron dejarían de abrir, sin que nadie lo pidiera.
    limpia["token_general"] = cargar_config().get("token_general", "")
    for clave in ("abre", "cierra", "hora_tope_mismo_dia"):
        if cfg.get(clave) is not None:
            valor = str(cfg[clave]).strip()
            if valor == "":
                # La hora tope se puede dejar vacía: es decir "aquí no prometemos plazo".
                if clave == "hora_tope_mismo_dia":
                    limpia[clave] = ""
                    continue
            if _minutos(valor) is None:
                raise ValueError(f"«{valor}» no es una hora válida (va como 09:00).")
            limpia[clave] = _hhmm(_minutos(valor))

    for clave, minimo, maximo in (("paso_minutos", 5, 120), ("max_por_prenda", 1, 999)):
        try:
            limpia[clave] = max(minimo, min(int(cfg[clave]), maximo))
        except (TypeError, ValueError, KeyError):
            pass

    if "iva_porcentaje" in cfg:
        crudo = str(cfg["iva_porcentaje"]).strip().replace("%", "").replace(",", ".")
        if crudo == "":
            limpia["iva_porcentaje"] = 0      # sin impuesto: no se le suma nada
        else:
            try:
                valor = Decimal(crudo)
            except InvalidOperation:
                raise ValueError("El IVA va como 13 (el número, sin el signo).")
            # Un «nan» o un «inf» pasan por Decimal sin quejarse, y comparar un nan con
            # <= no da False: revienta con InvalidOperation. Se descartan antes.
            if not valor.is_finite() or not 0 <= valor <= 100:
                raise ValueError("El IVA tiene que estar entre 0 y 100.")
            # Dos decimales como máximo. No es un capricho de formato: la página del
            # huésped calcula el impuesto con este mismo número, y para que le dé al
            # centavo lo mismo que al servidor los dos tienen que partir de un número
            # corto.
            valor = valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            # Entero cuando lo es, para que la pantalla diga «IVA 13%» y no «IVA 13.0%».
            limpia["iva_porcentaje"] = (int(valor) if valor == valor.to_integral_value()
                                        else float(valor))

    if _minutos(limpia["cierra"]) <= _minutos(limpia["abre"]):
        raise ValueError("La hora de cierre tiene que ser después de la de apertura.")

    tope = limpia.get("hora_tope_mismo_dia")
    if tope and not (_minutos(limpia["abre"]) <= _minutos(tope) <= _minutos(limpia["cierra"])):
        raise ValueError(
            "La hora tope tiene que caer dentro del horario de recolección: si está "
            "fuera, o no la alcanza nadie o la alcanzan todos.")

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(limpia, f, ensure_ascii=False, indent=2)
    return limpia


# ---------------------------------------------------------------------------
# Horas
# ---------------------------------------------------------------------------

def _minutos(hhmm):
    """'09:30' -> 570. None si no es una hora."""
    try:
        h, m = str(hhmm).strip().split(":")[:2]
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h * 60 + m
    except (ValueError, AttributeError, TypeError):
        pass
    return None


def _hhmm(minutos):
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def normalizar_hora(hhmm):
    m = _minutos(hhmm)
    return _hhmm(m) if m is not None else None


def horas_de_recoleccion(cfg=None):
    """Las horas que se le ofrecen al huésped, dentro del horario de housekeeping.

    A diferencia del spa, aquí NO se descuentan las ya tomadas: recoger ropa de dos
    habitaciones a la misma hora no es un choque, es el mismo recorrido. Housekeeping
    pasa por el pasillo una vez.
    """
    cfg = cfg or cargar_config()
    abre, cierra = _minutos(cfg["abre"]), _minutos(cfg["cierra"])
    paso = max(5, int(cfg.get("paso_minutos", 30)))
    horas, h = [], abre
    while h <= cierra:
        horas.append(_hhmm(h))
        h += paso
    return horas


def vuelve_mismo_dia(hora, cfg=None):
    """¿La ropa recogida a esa hora vuelve hoy? None si el hotel no promete plazo.

    Devuelve None —y no False— cuando no hay hora tope configurada, porque son cosas
    distintas: 'vuelve mañana' es una promesa, 'no prometemos' es otra. La página del
    huésped no debe decir la primera cuando el hotel quiso decir la segunda.
    """
    cfg = cfg or cargar_config()
    tope = cfg.get("hora_tope_mismo_dia")
    m_hora, m_tope = _minutos(hora), _minutos(tope)
    if m_hora is None or m_tope is None:
        return None
    return m_hora <= m_tope


# ---------------------------------------------------------------------------
# Precios
# ---------------------------------------------------------------------------
# Todo en CENTAVOS enteros. En coma flotante, sumar doce veces 2.10 da
# 25.199999999999996, y ese número acabaría impreso en la cuenta de un huésped.

def centavos_de(texto):
    """'2.50', '2,50', '$2.50' o 2.5 -> 250. None si está vacío, False si no es un precio.

    Se aceptan la coma y el símbolo porque quien carga la lista escribe como escribe, y
    rechazarle '2,50' por la coma sería hacerle perder el tiempo con algo que se entiende
    perfectamente.
    """
    if texto is None:
        return None
    t = str(texto).strip().replace(MONEDA, "").replace(" ", "").replace(",", ".")
    if t == "":
        return None
    try:
        valor = float(t)
    except ValueError:
        return False
    if valor < 0:
        return False
    # round() antes de int(): int(2.99*100) da 298 porque 2.99 no es exacto en binario.
    return int(round(valor * 100))


def formato_precio(centavos):
    """250 -> '$2.50'. Cadena vacía si no hay precio puesto."""
    if centavos is None:
        return ""
    return f"{MONEDA}{centavos / 100:,.2f}"


def total_de(items):
    """(centavos, completo) del SUBTOTAL, sin impuesto.

    Se devuelven los dos porque un total al que le falta una prenda no es un total: al
    huésped hay que decirle que está incompleto, no darle un número que no va a coincidir
    con su cuenta.
    """
    total, completo = 0, True
    for i in items:
        precio = i.get("precio_centavos")
        if precio is None:
            completo = False
            continue
        total += int(precio) * int(i.get("cantidad") or 0)
    return total, completo


def iva_de(subtotal_centavos, porcentaje):
    """El impuesto sobre un subtotal, en centavos, redondeado COMERCIALMENTE.

    Media unidad se sube, que es lo que hace una factura. El round() de Python redondea
    al par —round(136.5) da 136— así que sobre un subtotal de $10.50 el hotel cobraría un
    céntimo de menos, y la suma de la pantalla no cuadraría con la del sistema contable.
    """
    if not porcentaje or subtotal_centavos <= 0:
        return 0
    bruto = Decimal(int(subtotal_centavos)) * Decimal(str(porcentaje)) / Decimal(100)
    return int(bruto.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def cuenta_de(items, cfg=None):
    """La cuenta completa de un pedido: subtotal, impuesto y total.

    El impuesto se calcula UNA vez sobre el subtotal y no línea por línea. Sumando el
    redondeo de cada línea, un pedido de doce prendas puede quedar dos o tres céntimos
    lejos del 13% del subtotal, y entonces el desglose que ve el huésped no suma el total
    que ve debajo.
    """
    cfg = cfg or cargar_config()
    porcentaje = cfg.get("iva_porcentaje") or 0
    subtotal, completo = total_de(items)
    impuesto = iva_de(subtotal, porcentaje)
    return {
        "subtotal_centavos": subtotal,
        "iva_centavos": impuesto,
        "iva_porcentaje": porcentaje,
        "total_centavos": subtotal + impuesto,
        "completo": completo,
    }


# ---------------------------------------------------------------------------
# El pedido
# ---------------------------------------------------------------------------

def limpiar_items(items, prendas_validas, cfg=None):
    """Normaliza lo que llega del formulario. Devuelve (lista, problema).

    `prendas_validas` es {codigo: nombre} o {codigo: {'nombre':…, 'precio_centavos':…}}
    del catálogo activo. Se copian al pedido el NOMBRE y el PRECIO: si housekeeping
    renombra la prenda o sube la lista mañana, el pedido de hoy tiene que seguir diciendo
    qué se recogió y cuánto se cotizó.

    El precio sale del CATÁLOGO, nunca de lo que mande el formulario. La página es
    pública: si el precio viajara en la petición, cualquiera podría mandarse un pedido de
    veinte camisas a cero.
    """
    cfg = cfg or cargar_config()
    tope = int(cfg.get("max_por_prenda", 99))
    limpios, vistos = [], set()

    for it in (items or []):
        codigo = str((it or {}).get("codigo") or "").strip()
        if not codigo or codigo not in prendas_validas:
            continue
        if codigo in vistos:
            return None, "Llegó la misma prenda dos veces."
        try:
            cantidad = int((it or {}).get("cantidad") or 0)
        except (TypeError, ValueError):
            return None, "Las cantidades tienen que ser números."

        prenda = prendas_validas[codigo]
        nombre = prenda if isinstance(prenda, str) else prenda.get("nombre")
        precio = None if isinstance(prenda, str) else prenda.get("precio_centavos")

        if cantidad <= 0:
            continue                      # marcó la prenda y la dejó en cero: no va
        if cantidad > tope:
            return None, (f"{nombre}: {cantidad} es demasiado. "
                          f"El tope por prenda es {tope}.")
        vistos.add(codigo)
        limpios.append({"codigo": codigo, "nombre": nombre, "cantidad": cantidad,
                        "precio_centavos": precio})

    if not limpios:
        return None, "Marcá al menos una prenda con su cantidad."
    return limpios, None


def resumen_items(items):
    """'3 camisetas · 2 pantalones largos', para el aviso y las listas."""
    return " · ".join(f"{i['cantidad']} {i['nombre'].lower()}" for i in items)


def total_prendas(items):
    return sum(int(i.get("cantidad") or 0) for i in items)


def siguiente_estado(actual):
    """El paso natural desde donde está. None si ya terminó."""
    orden = {v: k for k, v in ORDEN_ESTADOS.items()}
    n = ORDEN_ESTADOS.get(actual)
    if n is None:
        return None
    return orden.get(n + 1)


def puede_pasar_a(actual, nuevo):
    """¿Es un cambio de estado razonable? Devuelve (sí/no, motivo).

    Se permite avanzar, cancelar, y volver UN paso atrás —housekeeping marca 'recogido'
    por error y lo deshace—. Lo que no se permite es saltar del final al principio, que
    solo pasa por un toque de más y borraría las horas ya anotadas.
    """
    if nuevo not in ESTADOS:
        return False, "Ese estado no existe."
    if actual == nuevo:
        return False, "Ya está en ese estado."
    if actual == "CANCELADO":
        return False, "Ese pedido está cancelado."
    if nuevo == "CANCELADO":
        return True, None
    a, b = ORDEN_ESTADOS.get(actual), ORDEN_ESTADOS.get(nuevo)
    if a is None or b is None:
        return False, "Ese cambio no tiene sentido."
    if b < a - 1:
        return False, ("De ahí no se puede volver tan atrás. Cancelá el pedido si hay "
                       "que rehacerlo.")
    return True, None


# ---------------------------------------------------------------------------
# El enlace personal del huésped
# ---------------------------------------------------------------------------

def token_general(crear=True):
    """El código del ÚNICO enlace que se manda a todo el mundo.

    POR QUÉ UN SOLO ENLACE. El de cada reserva sabía quién era el huésped y por eso el
    formulario no le preguntaba el nombre ni la habitación —que eran justamente las dos
    preguntas que se contestaban mal en el formulario de Google—. Pero significaba
    copiar un enlace distinto por habitación, y eso no se sostiene: el hotel lo manda
    por WhatsApp, muchas veces a un grupo, y necesita UNO que sirva para todos.

    Se decidió por logística interna, sabiendo lo que cuesta: el huésped vuelve a
    escribir su habitación y puede equivocarse. Lo que se hace para que cueste menos
    está en `buscar_reserva`: el sistema intenta emparejar lo que escribió con una
    reserva de verdad, y si no lo consigue el pedido entra igual, marcado, en vez de
    perderse.

    El enlace por reserva NO se quita: sigue funcionando para quien ya lo tenga y para
    mandarlo a una habitación concreta cuando haga falta.

    El código va en la configuración y no en una tabla porque es UNO solo. Se puede
    cambiar desde la pantalla, y al cambiarlo el anterior deja de servir — que es lo que
    hace falta si el enlace se filtra fuera del hotel.
    """
    cfg = cargar_config()
    actual = (cfg.get("token_general") or "").strip()
    if actual:
        return actual
    if not crear:
        return None
    nuevo = secrets.token_urlsafe(9)
    cfg["token_general"] = nuevo
    _escribir_config(cfg)
    return nuevo


def rehacer_token_general():
    """Cambia el enlace general. El anterior deja de abrir."""
    cfg = cargar_config()
    cfg["token_general"] = secrets.token_urlsafe(9)
    _escribir_config(cfg)
    return cfg["token_general"]


def token_general_valido(token):
    esperado = token_general(crear=False)
    if not esperado or not token:
        return False
    return secrets.compare_digest(str(token), str(esperado))


def buscar_reserva(conn, nombre, room_no, fecha=None):
    """Intenta emparejar lo que escribió el huésped con una reserva que esté en casa.

    Devuelve (reserva o None, motivo). Es BEST EFFORT a propósito: si no se encuentra,
    el pedido se guarda igual con lo que la persona escribió. Rechazarlo sería repetir
    el fallo del formulario de Google, donde quien ponía 23 en vez de 32 simplemente no
    recibía su ropa —y no se enteraba nadie—.

    Se busca por habitación entre las reservas que están en casa hoy, que es el dato que
    de verdad importa para ir a recoger. El nombre solo se usa para desempatar cuando
    dos reservas comparten habitación, cosa que pasa el día del cambio.
    """
    room = (room_no or "").strip().lstrip("0") or (room_no or "").strip()
    if not room:
        return None, "no escribió la habitación"

    filas = conn.execute(
        """SELECT conf_no, room_no, nombre_principal, arr_date, dep_date
           FROM reserva
           WHERE res_status NOT IN ('CANCELADA','SALIO')
             AND REPLACE(LTRIM(room_no,'0'),' ','') = ?""",
        (room.replace(" ", ""),)).fetchall()
    if not filas:
        return None, f"no hay ninguna habitación {room} en casa"
    if len(filas) == 1:
        return dict(filas[0]), None

    # Dos reservas en el mismo cuarto: se desempata por apellido.
    apellido = (nombre or "").strip().lower().split()
    for f in filas:
        completo = (f["nombre_principal"] or "").lower()
        if any(p and p in completo for p in apellido):
            return dict(f), None
    return dict(filas[0]), "varias reservas en esa habitación; se tomó la primera"


def token_de_reserva(conn, conf_no, crear=True):
    """El código del enlace que se le manda al huésped. Se crea la primera vez.

    Va por RESERVA y no por habitación, por lo mismo que en el spa: el código del QR de
    la puerta no cambia nunca —se imprime y se pega— así que le serviría al huésped
    siguiente. Este solo vale mientras esa reserva exista.
    """
    fila = conn.execute("SELECT token FROM hk_enlace WHERE conf_no = ?",
                        (conf_no,)).fetchone()
    if fila and dict(fila).get("token"):
        return dict(fila)["token"]
    if not crear:
        return None
    token = secrets.token_urlsafe(9)
    conn.execute(
        "INSERT INTO hk_enlace (conf_no, token) VALUES (?,?) "
        "ON CONFLICT(conf_no) DO UPDATE SET token = excluded.token",
        (conf_no, token))
    conn.commit()
    return token


def reserva_de_token(conn, conf_no, token):
    """La reserva si el código coincide, o None. Nunca dice cuál de los dos falló."""
    if not conf_no or not token:
        return None
    fila = conn.execute("SELECT token FROM hk_enlace WHERE conf_no = ?",
                        (conf_no,)).fetchone()
    if not fila:
        return None
    if not secrets.compare_digest(str(dict(fila)["token"]), str(token)):
        return None
    r = conn.execute(
        """SELECT conf_no, room_no, nombre_principal, arr_date, dep_date, res_status
           FROM reserva WHERE conf_no = ?""", (conf_no,)).fetchone()
    if not r or (dict(r)["res_status"] or "").upper() == "CANCELADA":
        return None
    return dict(r)
