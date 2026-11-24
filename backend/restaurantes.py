"""
Distribución de huéspedes entre los dos restaurantes del lodge.

Reglas de la operación (definidas con el hotel):

  Capacidades      Terra Kitchen   Bar el Bosque
    Cena                30            45      (75 es el techo de la propiedad)
    Almuerzo            35            —

  1. Asignación base
       · Quien entra hoy: almuerza en Bar el Bosque y cena en Terra Kitchen
       · Quien está en casa: almuerza en Terra Kitchen y cena en Bar el Bosque
       · Quien sale hoy no cuenta para ninguna comida (el bote sale de madrugada)

  2. La cena en Terra Kitchen se llena por prioridad
       1º rezagados  — quienes no alcanzaron su cena de bienvenida, empezando por
                       el que se va antes (si no, se irían sin recibirla nunca)
       2º entradas de hoy
       3º en casa     — los que entren por rotación para equilibrar
     Se genera un rezagado tanto por capacidad como por balanceo.

  3. Los grupos y familias no se separan nunca, aunque no quepan.

  4. Balanceo (solo cena): diferencia máxima de 4 pax entre restaurantes.
     Por encima de 64 pax es imposible cumplirlo (Terra Kitchen topa en 30) y el
     sistema lo informa en vez de fallar en silencio.

  5. La cena privada queda fija en Bar el Bosque y cuenta para sus 45 lugares: aunque
     se sirva en la piscina, ocupa servicio.

  6. El cambio manual afecta una sola fecha, pero se lleva al GRUPO entero: la regla 3
     vale también cuando mueve una persona y no el reparto. Antes no era así, y mover
     una habitación dejaba a las otras siete de la agencia en el otro restaurante.
     Quien esté separado a propósito —con su propio cambio manual— o tenga cena privada
     se queda donde está y se informa. Queda en el historial para que la rotación de los
     días siguientes lo tome en cuenta.

La rotación no alterna de forma rígida: se mide por proporción de cenas en cada
restaurante, así se autocorrige cuando una noche no se pudo cumplir.
"""

import datetime

import grupos
import habitaciones

TERRA = "Terra Kitchen"
# Antes se llamaba "Vitrales". El nombre viejo quedó guardado en los cambios manuales,
# en el histórico de rotación y en los restaurantes fijos de estadía, así que init_db
# lo renombra en la base al arrancar (ver _renombrar_bar_el_bosque).
BOSQUE = "Bar el Bosque"
NOMBRE_ANTERIOR_BOSQUE = "Vitrales"

# El comedor del staff. NO es un tercer restaurante del huésped: es donde come quien no
# come en los principales —personal de mantenimiento, proveedores, un guía alojado—, y lo
# que importa de él es justo lo contrario que de los otros dos: que NO cuente.
#
# Lo pidió el lodge: «un botón que se llame Comedor staff, ya que hay reservas que no
# comen en los restaurantes principales y se deben mover de forma manual, con el fin de
# que no afecte la distribución real de los restaurantes principales». Antes esas
# habitaciones se quedaban en Terra o en el Bosque ocupando un sitio que nadie iba a usar:
# el reparto equilibraba contándolas y la cocina preparaba de más.
#
# Va por el MISMO camino que los otros dos —un cambio manual de esa fecha y esa comida—
# así que se mueve, se deshace y se ve con lo que ya existe. Lo único que cambia es que
# quien está aquí sale de los totales y del equilibrio.
STAFF = "Comedor staff"
RESTAURANTES = (TERRA, BOSQUE, STAFF)

CAP_CENA_TK = 30
CAP_CENA_BOSQUE = 45
CAP_ALMUERZO_TK = 35
MARGEN_BALANCE = 4

# Por encima de este total es imposible respetar el margen, porque Terra Kitchen
# no puede tomar la mitad: 30 es su tope y (total - 4) / 2 debe caber ahí.
TOTAL_MAX_BALANCEABLE = CAP_CENA_TK * 2 + MARGEN_BALANCE


def _a_fecha(ddmmyy):
    """'13-08-26' -> date(2026, 8, 13)"""
    try:
        d, m, y = ddmmyy.split("-")
        return datetime.date(2000 + int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def _iso(f):
    return f.isoformat() if hasattr(f, "isoformat") else str(f)


# ---------------------------------------------------------------------------
# Lectura de los datos que ya tiene el sistema
# ---------------------------------------------------------------------------

def _reservas_base(conn, cache=None):
    """Las reservas vivas, ya con su fecha convertida y su clave de grupo calculada.

    Esto es lo que costaba caro: cada día que se quería repartir volvía a leer la tabla
    de reservas COMPLETA y a convertir de texto a fecha las dos fechas de cada una. Mirar
    un mes en la pantalla de régimen eran 30 lecturas de toda la tabla; la página que ve
    el huésped al escanear su QR hacía una por cada noche de su estadía.

    Con `cache` (un diccionario cualquiera que pase el llamante) se lee UNA vez y se
    reutiliza. El alcance lo decide quien llama, a propósito: así nadie se queda con datos
    viejos sin haberlo pedido. Se guardan solo las reservas —nunca el histórico ni los
    cambios manuales— porque congelar_dias_pasados() escribe en el histórico mientras
    recorre los días, y una copia de eso sí quedaría desactualizada.

    Las filas se devuelven como plantillas de solo lectura: quien las use hace su propia
    copia, porque _reservas_del_dia() les agrega campos distintos según el día.
    """
    if cache is not None and "base" in cache:
        return cache["base"]

    base = []
    for fila in conn.execute(
        """SELECT conf_no, room_no, nombre_principal, adl, chl, arr_date, dep_date,
                  grupo_id, block_code, forzar_restaurante, regimen,
                  bebidas_incluidas, cortesia
           FROM reserva WHERE res_status != 'CANCELADA'""").fetchall():
        r = dict(fila)
        llega, sale = _a_fecha(r["arr_date"]), _a_fecha(r["dep_date"])
        if not llega:
            continue          # sin fecha de llegada no se puede ubicar: se descarta
        r["pax"] = (r["adl"] or 0) + (r["chl"] or 0)
        r["noches"] = (sale - llega).days if sale else 1
        # La clave de grupo vive en grupos.py: es la MISMA que usan las pantallas para
        # mostrar que varias habitaciones viajan juntas. Si aquí se separaran de otra
        # forma, el comedor y la pantalla se contradirían.
        r["clave_grupo"] = grupos.clave_de(r)
        base.append((r, llega, sale))

    if cache is not None:
        cache["base"] = base
    return base


def _reservas_del_dia(conn, fecha, cache=None):
    """Clasifica las reservas de esa fecha en entradas, en casa y salidas.

    Se apoya en los datos que el sistema ya carga del PDF: no hay que llenar
    ninguna hoja aparte.
    """
    entradas, en_casa, salidas = [], [], []
    for plantilla, llega, sale in _reservas_base(conn, cache):
        # Solo se copia lo que este día usa. Los campos que se agregan abajo dependen de
        # la fecha, así que cada día necesita su propia copia y no se puede tocar la
        # plantilla compartida.
        if llega == fecha:
            r = dict(plantilla)
            r["tipo"] = "ENTRA"
            r["noche_estadia"] = 1
            r["noches_restantes"] = (sale - fecha).days if sale else 1
            entradas.append(r)
        elif sale and llega < fecha < sale:
            r = dict(plantilla)
            r["tipo"] = "EN_CASA"
            r["noche_estadia"] = (fecha - llega).days + 1
            r["noches_restantes"] = (sale - fecha).days
            en_casa.append(r)
        elif sale == fecha:
            r = dict(plantilla)
            r["tipo"] = "SALE"
            salidas.append(r)
    return entradas, en_casa, salidas


def _historial(conn, hasta_fecha):
    """Cuántas cenas tuvo cada reserva en cada restaurante hasta esa fecha.

    Se lee del histórico congelado, que es la única fuente confiable: recalcular
    el pasado daría resultados distintos si entre medio cambió la ocupación.
    """
    conteo = {}
    for r in conn.execute(
        "SELECT conf_no, cena, era_entrada, fecha FROM restaurante_historico WHERE fecha < ?",
        (_iso(hasta_fecha),),
    ).fetchall():
        d = dict(r)
        c = conteo.setdefault(d["conf_no"], {"tk": 0, "bosque": 0, "noches": 0,
                                             "debe_bienvenida": False})
        if d["cena"] == TERRA:
            c["tk"] += 1
        elif d["cena"] == BOSQUE:
            c["bosque"] += 1
        if d["cena"]:
            c["noches"] += 1
        # Si el día que entró no cenó en Terra Kitchen, quedó debiendo su
        # cena de bienvenida, sin importar si fue por capacidad o por balanceo.
        if d["era_entrada"] and d["cena"] and d["cena"] != TERRA:
            c["debe_bienvenida"] = True
    return conteo


def _cambios_manuales(conn, fecha):
    """Las filas fijadas de ese día: las que puso una persona y las congeladas.

    Las dos clavan a una reserva en un restaurante y por eso se leen juntas. Lo que las
    distingue es 'congelado': una la decidió alguien y se enseña como tal; la otra solo
    sostiene la foto del día (ver fijar_el_resto) y en pantalla no se muestra como un
    cambio, porque nadie lo pidió.
    """
    return {(dict(r)["conf_no"], dict(r)["comida"]): dict(r)
            for r in conn.execute(
                "SELECT conf_no, comida, restaurante, motivo, congelado "
                "FROM restaurante_cambio WHERE fecha = ?",
                (_iso(fecha),)).fetchall()}


# ---------------------------------------------------------------------------
# Régimen de comidas, para el salonero
# ---------------------------------------------------------------------------

TEXTO_REGIMEN = {
    "PENSION_COMPLETA":     "comidas incluidas",
    "DESAYUNO_CENA":        "solo desayuno y cena",
    "SOLO_DESAYUNO":        "solo desayuno",
    "COMEDOR_TRABAJADORES": "come en el comedor de trabajadores",
}


def texto_regimen(regimen):
    """Cómo se le dice al salonero. Sin dato se deja vacío: no es lo mismo que no tener."""
    return TEXTO_REGIMEN.get(regimen or "", "")


def incluye_comida(regimen, comida):
    """Si esta comida en concreto le corresponde al huésped.

    Devuelve None cuando el PDF no dijo el régimen, que no es lo mismo que un "no":
    es "no se sabe", y en pantalla se muestra distinto para que nadie le niegue el
    almuerzo a alguien por un dato que el reporte no traía.
    """
    from importer import COMIDAS_DE_REGIMEN
    if not regimen or regimen not in COMIDAS_DE_REGIMEN:
        return None
    clave = "almuerzo" if comida == "almuerzo" else "cena"
    return COMIDAS_DE_REGIMEN[regimen][clave]


def _filtro_privada(prefijo=""):
    """Cómo se reconoce una cena privada entre las amenidades.

    En un solo lugar porque se consulta desde varios sitios y tiene que coincidir
    siempre: si aquí se reconoce y allá no, la mesa se cuenta mal.
    """
    p = f"{prefijo}." if prefijo else ""
    return (f"({p}amenidad LIKE '%privada%' OR {p}tarea LIKE '%privada%' "
            f"OR {p}amenidad LIKE '%private%dinner%')")


def es_cena_privada(amenidad, tarea=None):
    """La MISMA regla que _filtro_privada, pero en Python.

    Hace falta porque al importar el PDF hay que decidir en Python si una amenidad es
    cena privada, y ahí no se puede usar SQL. Las dos versiones tienen que decir lo
    mismo: si esta reconociera algo que la de SQL no —o al revés—, una cena privada
    quedaría fechada sola sin aparecer en el comedor, o al contrario.

    Por eso están pegadas una a la otra: quien cambie una ve la otra.
    """
    a = (amenidad or "").lower()
    t = (tarea or "").lower()
    if "privada" in a or "privada" in t:
        return True
    # 'private dinner', 'private  dinner', 'private in-villa dinner'...
    if "private" in a and "dinner" in a and a.index("private") < a.index("dinner"):
        return True
    return False


# Palabras por las que se reconoce una restricción alimentaria.
#
# La lista es GENEROSA a propósito, y esa es la decisión importante: una alergia que no
# se muestra puede mandar a alguien al hospital; una fila de más solo estorba un poco.
# Ante la duda, se muestra.
#
# Van en español y en inglés porque el reporte del PMS llega en inglés y recepción
# escribe en español, así que las dos formas conviven en la misma tabla.
PALABRAS_RESTRICCION = (
    "alergi", "alérgi", "alerg", "allerg",
    "restricc", "restrict", "dietary", "diet",
    "intoleran", "celia", "celíac", "gluten",
    "vegan", "vegetarian", "vegetarian",
    "lactosa", "lactose", "marisco", "shellfish", "nuez", "nuts", "maní", "peanut",
    "kosher", "halal", "sin azúcar", "sugar free", "diabet",
    # Faltaban, y son de las que más se escriben: «no seafood» y «Dietary Restrictions:
    # No Pork» aparecen tal cual en las notas de Opera. Se salvaban solo porque el
    # NOMBRE de la amenidad ya dice «alergia»; una escrita a mano con otro nombre se
    # habría perdido, que es justo lo que esta lista existe para evitar.
    #
    # No se pone «fish» a secas: cazaría «Sport Fishing», que es un tour.
    "seafood", "pork", "cerdo", "camarón", "camaron", "shrimp", "dairy",
    "lácteo", "lacteo", "pescatarian",
)


# Palabras que dicen que HAY una restricción pero no de qué. Sirven para encontrarla; no
# sirven para saber si es de comida.
_GENERICAS = ("alergi", "alérgi", "alerg", "allerg",
              "restricc", "restrict", "dietary", "diet", "intoleran")

# Las que sí nombran una comida. Se derivan de la lista de arriba en vez de escribirse
# otra vez: así, el día que alguien agregue «mostaza» a PALABRAS_RESTRICCION, cuenta como
# comida sola. Dos listas a mano se desincronizan, y la que se quedara corta mandaría una
# alergia de comida al departamento equivocado.
PALABRAS_COMIDA = tuple(p for p in PALABRAS_RESTRICCION if p not in _GENERICAS)

# Alergias que NO son de comida. Cocina no puede hacer nada con ellas y housekeeping sí:
# una almohada de plumas se cambia, un desayuno no arregla nada.
#
# Medido sobre las 24 restricciones de la ventana: dos son de este tipo —«Down Feather
# Allergy» y «Ambos tiene alergía a las plumas», las dos del 22 de noviembre— y las otras
# veintidós son de comida.
PALABRAS_NO_ALIMENTARIAS = (
    "pluma", "feather", "ácaro", "acaro", "dust mite", "polen", "pollen",
    "látex", "latex", "penicilin", "abeja", "bee sting", "picadura de",
)


def es_alergia_no_alimentaria(amenidad, tarea=None, detalle=None):
    """Si es una alergia que NO tiene que ver con la comida.

    Se exige que nombre un alérgeno no alimentario Y que NO nombre ninguna comida. Ese
    «y» es lo importante: «allergic to feathers and peanuts» es las dos cosas, y tratarla
    como no alimentaria le escondería el maní a cocina. Ante la duda, es de comida — que
    es el lado seguro.
    """
    texto = " ".join(str(x or "") for x in (amenidad, tarea, detalle)).lower()
    if not any(p in texto for p in PALABRAS_NO_ALIMENTARIAS):
        return False
    return not any(p in texto for p in PALABRAS_COMIDA)


def es_restriccion_alimentaria(amenidad, tarea=None, detalle=None):
    """Si esta amenidad es algo que la cocina TIENE que saber antes de servir.

    Mira el nombre, la tarea y el detalle: recepción a veces escribe la amenidad como
    "Preferencia del huésped" y pone "alérgico a mariscos" en el detalle, y esa también
    tiene que aparecer.

    La cena privada queda fuera aunque sea de cocina: tiene su propio sitio en la
    pantalla y mezclarlas escondería lo que aquí importa.

    Y «NO tiene alergias» tampoco entra. El importador ya no crea esa amenidad, pero
    recepción puede escribirla a mano —«sin alergias», «no dietary restrictions»— y
    entonces llegaría aquí por la palabra «alergia» y ocuparía una fila de la pestaña
    diciendo lo contrario de lo que parece.
    """
    if es_cena_privada(amenidad, tarea):
        return False
    # Y la alergia que no es de comida tampoco: cocina no puede hacer nada con una
    # alergia a las plumas, y ocupando una fila de esta pestaña solo consigue que se lea
    # con menos atención la de al lado, que sí puede mandar a alguien al hospital.
    if es_alergia_no_alimentaria(amenidad, tarea, detalle):
        return False
    texto = " ".join(str(x or "") for x in (amenidad, tarea, detalle))
    import importer
    if importer.sin_restricciones(texto):
        return False
    return any(p in texto.lower() for p in PALABRAS_RESTRICCION)


def restricciones_del_dia(conn, fecha, distribucion=None, cache=None,
                          solo_quitadas=False):
    """Las restricciones alimentarias de todo el que come ese día.

    NO se filtra por la fecha de la amenidad, y es deliberado: una alergia no es de un
    día, es de toda la estadía. Filtrarla por fecha la mostraría solo el día que el
    huésped llega, que es justo cuando menos falta hace — lo que la cocina necesita es
    saberla cada noche que esa persona se sienta a comer.

    Quien sale ese día no aparece: el bote se va de madrugada y no desayuna aquí. Es el
    mismo criterio que usa el reparto de mesas.

    `solo_quitadas` devuelve las que alguien quitó a mano en vez de las vigentes, para
    poder enseñarlas y devolverlas. Es la MISMA función a propósito: las dos listas
    tienen que decidir con la misma regla quién come esa noche, o una alergia quitada
    podría no aparecer en ninguna de las dos y quedarse perdida sin que nadie lo note.
    """
    if isinstance(fecha, str):
        fecha = datetime.date.fromisoformat(fecha)
    if distribucion is None:
        entradas, en_casa, _ = _reservas_del_dia(conn, fecha, cache)
        comen = entradas + en_casa
    else:
        # Se reutiliza lo que ya calculó distribuir(), para no releer las reservas.
        comen = distribucion
    por_conf = {r["conf_no"]: r for r in comen}
    if not por_conf:
        return []

    salida = []
    for i in range(0, len(por_conf), 400):
        lote = list(por_conf)[i:i + 400]
        marcas = ",".join("?" * len(lote))
        for f in conn.execute(
            f"""SELECT a.id, a.conf_no, a.amenidad, a.tarea, a.detalle, a.estado,
                       a.area_responsable, a.origen, a.editado_a_mano
                FROM amenidad_tarea a
                WHERE a.conf_no IN ({marcas})
                  AND COALESCE(a.oculta, 0) = {1 if solo_quitadas else 0}
                ORDER BY a.id""", lote).fetchall():
            d = dict(f)
            if not es_restriccion_alimentaria(d["amenidad"], d["tarea"], d["detalle"]):
                continue
            r = por_conf[d["conf_no"]]
            salida.append({
                # El id viene para que la pantalla pueda marcarla como avisada sin tener
                # que ir a buscarla a Amenidades.
                "id": d["id"],
                "conf_no": d["conf_no"],
                "room_no": r.get("room_no"),
                # Los dos nombres del campo conviven: las filas crudas de
                # _reservas_del_dia() traen 'nombre_principal', y las que ya pasaron por
                # distribuir() traen 'nombre'. Esta función se llama con las dos.
                "nombre": r.get("nombre_principal") or r.get("nombre"),
                "pax": r.get("pax"),
                "amenidad": d["amenidad"],
                "detalle": d["detalle"],
                "tarea": d["tarea"],
                "estado": d["estado"],
                "tipo": r.get("tipo"),
                # Para que la pantalla pueda ofrecer lo que de verdad se puede hacer:
                # una restricción que vino de Opera NO se puede borrar —volvería en la
                # siguiente sincronización— pero sí se puede corregir, y al corregirla
                # queda marcada y el cargador ya no la pisa.
                "origen": d["origen"],
                "editado_a_mano": bool(d["editado_a_mano"]),
            })
    salida.sort(key=lambda x: int(x["room_no"]) if (x["room_no"] or "").isdigit() else 999)
    return juntar_las_repetidas(salida)


def _clave_de_texto(detalle):
    """El mismo texto escrito igual, para poder reconocerlo repetido.

    Se normaliza poco a propósito —espacios y mayúsculas— y nada más: dos textos que
    solo se PAREZCAN son dos restricciones distintas hasta que alguien diga lo contrario.
    Juntar por parecido escondería una alergia de verdad, que es el error caro aquí.
    """
    return " ".join((detalle or "").split()).lower()


def juntar_las_repetidas(filas):
    """Una línea por restricción, aunque esté escrita en varias reservas.

    POR QUÉ EXISTE. El lodge lo vio como «las alergias se están duplicando». No era la
    base: medido sobre las 331 reservas cargadas, no hay una sola reserva con la misma
    restricción dos veces. Lo que pasa es que una familia que toma DOS habitaciones lleva
    la misma nota copiada en las dos —el agente la escribe igual en ambas reservas de
    Opera— y la hoja de cocina enseñaba el mismo texto dos veces, como si fueran dos
    personas distintas con la misma alergia.

    Se juntan SOLO las de texto idéntico, y las habitaciones se listan todas: la cocina
    sirve por mesa y necesita saber en cuáles está. Se quita la línea repetida, no la
    información.

    Una restricción SIN detalle no se junta con otra sin detalle: no hay texto que
    comparar, y dos vacías pueden ser dos cosas distintas que alguien no escribió.
    """
    grupos, orden = {}, []
    for f in filas:
        texto = _clave_de_texto(f.get("detalle"))
        clave = (texto, f.get("amenidad")) if texto else ("", f["id"])
        if clave not in grupos:
            g = dict(f)
            g["ids"], g["habitaciones"], g["nombres"] = [], [], []
            g["estados"] = []
            grupos[clave] = g
            orden.append(clave)
        g = grupos[clave]
        g["ids"].append(f["id"])
        g["estados"].append(f.get("estado"))
        if f.get("room_no") and f["room_no"] not in g["habitaciones"]:
            g["habitaciones"].append(f["room_no"])
        if f.get("nombre") and f["nombre"] not in g["nombres"]:
            g["nombres"].append(f["nombre"])

    salida = []
    for clave in orden:
        g = grupos[clave]
        # Solo está avisada si lo están TODAS. Con una pendiente la línea sigue en rojo:
        # esa es la mitad que nadie revisó.
        g["estado"] = "HECHA" if all(e == "HECHA" for e in g.pop("estados")) else "PENDIENTE"
        g["en_cuantas_reservas"] = len(g["ids"])
        salida.append(g)
    return salida


def _cenas_privadas(conn, fecha):
    """Reservas con cena privada declarada esa noche. Van fijas a Bar el Bosque."""
    return {dict(r)["conf_no"] for r in conn.execute(
        f"""SELECT conf_no FROM amenidad_tarea
            WHERE fecha = ? AND {_filtro_privada()}""",
        (_iso(fecha),)).fetchall()}


def info_cenas_privadas(conn, fecha):
    """Las cenas privadas de esa noche CON su información, no solo el número.

    La pantalla mostraba únicamente el conteo ("2 declaradas para esta fecha"), así que
    para saber de quién eran había que ir a buscarlas a Amenidades. El salonero necesita
    la habitación y el detalle —si es aniversario hay decoración, si hay alergia la
    cocina la tiene que saber—, y eso es lo que se sirve aquí.

    La NOCHE no se elige desde esta pantalla: se asigna en Amenidades, que es donde vive
    la amenidad. Antes se podía hacer en los dos sitios y era el mismo dato escrito desde
    dos puertas distintas.
    """
    filas = conn.execute(
        f"""SELECT a.id, a.conf_no, a.amenidad, a.detalle, a.tarea, a.estado,
                   r.room_no, r.nombre_principal, (r.adl + r.chl) AS pax,
                   r.arr_date, r.dep_date
            FROM amenidad_tarea a JOIN reserva r ON r.conf_no = a.conf_no
            WHERE a.fecha = ? AND {_filtro_privada('a')}
              AND r.res_status != 'CANCELADA'
            ORDER BY """ + habitaciones.ORDEN_R,
        (_iso(fecha),)).fetchall()

    # ¿El huésped CENA esa noche? La noche de salida no: ese día desayuna y se va. Una
    # cena privada puesta ahí se acepta —el selector de fecha abarca toda la estadía
    # porque el desayuno del día de salida también es una tarea— pero no ocupa mesa ni
    # entra en el reparto de Bar el Bosque. Sin decirlo, la pantalla mostraría una cena
    # que nadie va a servir y en la cocina se enterarían esa noche.
    noche = fecha if hasattr(fecha, "isoformat") else datetime.date.fromisoformat(str(fecha))
    salida = []
    for f in filas:
        d = dict(f)
        llegada = _fecha_de_ddmmyy(d.pop("arr_date", None))
        se_va = _fecha_de_ddmmyy(d.pop("dep_date", None))
        d["cena_esa_noche"] = bool(llegada and se_va and llegada <= noche < se_va)
        salida.append(d)
    return salida


def _fecha_de_ddmmyy(valor):
    """'05-08-26' -> date(2026, 8, 5). None si no tiene esa forma."""
    try:
        d, m, y = str(valor).strip().split("-")
        return datetime.date(2000 + int(y), int(m), int(d))
    except (ValueError, AttributeError, TypeError):
        return None


def _privadas_sin_noche(conn, conf_nos):
    """Cenas privadas contratadas a las que todavía nadie les puso noche.

    El PDF avisa que el huésped la tiene contratada, pero casi nunca dice el día, así
    que la amenidad entra sin fecha. Y mientras no tenga fecha no entra en el reparto:
    Bar el Bosque no le guarda la mesa, no cuenta para sus 45 lugares y cocina no la ve
    venir. Antes eso no se mostraba en ninguna parte y la pantalla decía "sin cenas
    privadas esta noche", que es justo lo contrario de lo que pasaba.

    Se devuelven las de los huéspedes que están en casa esa noche, para que la pantalla
    las reclame mientras el huésped todavía está en el lodge.
    """
    if not conf_nos:
        return []
    marcas = ",".join("?" * len(conf_nos))
    # NO se reclama una reserva que YA tiene una cena privada con noche puesta.
    #
    # Pasa así: el reporte del PMS anuncia la cena sin decir el día, y además queda otra
    # amenidad de cena privada con la noche ya asignada —porque recepción la agregó a
    # mano, o porque el reporte la trae dos veces—. Son la misma cena escrita dos veces,
    # y sin este filtro la pantalla mostraba la habitación en las DOS listas a la vez:
    # arriba con su noche y su detalle, y abajo como "contratada sin noche asignada".
    # Comprobado sobre las 104 reservas con cena privada de la base: le pasa a 1.
    #
    # No se pierde nada: la amenidad sin día sigue señalada en Amenidades, en la columna
    # «Para el día», con el aviso "sin noche no llega al comedor". Lo que se calla aquí es
    # el reclamo repetido — y un aviso que sale cuando no toca es un aviso que la gente
    # aprende a ignorar, incluido el día que sí importa.
    # UNA LINEA POR HABITACION, no una por amenidad. Si la misma reserva trae dos veces
    # la cena privada sin fecha —el reporte la repite, o alguien la agregó a mano además
    # de la del reporte— antes salía dos veces en el aviso y parecía que el huésped tenía
    # dos cenas contratadas. 'cuantas' dice si de verdad hay más de una.
    filas = conn.execute(
        f"""SELECT a.conf_no, r.room_no, r.nombre_principal,
                   r.arr_date, r.dep_date, COUNT(*) AS cuantas,
                   GROUP_CONCAT(a.detalle, ' · ') AS detalle
            FROM amenidad_tarea a JOIN reserva r ON r.conf_no = a.conf_no
            WHERE a.fecha IS NULL AND {_filtro_privada('a')}
              AND a.conf_no IN ({marcas})
              AND NOT EXISTS (
                    SELECT 1 FROM amenidad_tarea b
                    WHERE b.conf_no = a.conf_no AND b.fecha IS NOT NULL
                      AND {_filtro_privada('b')})
            GROUP BY a.conf_no, r.room_no, r.nombre_principal, r.arr_date, r.dep_date
            ORDER BY """ + habitaciones.ORDEN_R,
        tuple(conf_nos)).fetchall()
    return [dict(f) for f in filas]


# ---------------------------------------------------------------------------
# Cálculo de la distribución
# ---------------------------------------------------------------------------

def _agrupar(reservas):
    """Junta las reservas que no se pueden separar. Cada bloque se mueve completo."""
    bloques = {}
    for r in reservas:
        b = bloques.setdefault(r["clave_grupo"], {"clave": r["clave_grupo"],
                                                  "reservas": [], "pax": 0})
        b["reservas"].append(r)
        b["pax"] += r["pax"]
    return list(bloques.values())


def _pax(bloques):
    return sum(b["pax"] for b in bloques)


def companeros_de_mesa(conn, fecha, conf_no):
    """Las otras reservas que esa noche se sientan con esta por ser del mismo grupo.

    El reparto nunca separa a un grupo ni a una familia (ver _agrupar): las ocho
    habitaciones de una agencia caen siempre en el mismo restaurante. Si comparten
    mesa, comparten hora, así que el salonero pone la hora una vez y le sirve para
    todas. Se usa la MISMA clave de grupo que el reparto, para que no pueda pasar que
    la hora se copie a un conjunto de habitaciones distinto del que se sienta junto.

    Solo se devuelve a quien cena esa noche: un compañero de grupo que salió en la
    mañana no tiene mesa que reservar, y el que llega mañana tampoco.
    """
    if isinstance(fecha, str):
        fecha = datetime.date.fromisoformat(fecha)
    entradas, en_casa, _ = _reservas_del_dia(conn, fecha)
    cenan = entradas + en_casa
    yo = next((r for r in cenan if r["conf_no"] == conf_no), None)
    # Clave que empieza con 'r' = la reserva va sola, no hay grupo que sincronizar.
    if not yo or yo["clave_grupo"].startswith("r"):
        return []
    return [{"conf_no": r["conf_no"], "room_no": r["room_no"],
             "nombre": r["nombre_principal"]}
            for r in cenan
            if r["clave_grupo"] == yo["clave_grupo"] and r["conf_no"] != conf_no]


# ---------------------------------------------------------------------------
# El control del salón: quién ya vino a comer
# ---------------------------------------------------------------------------

# Las comidas que el salón marca. El desayuno fue la primera; la cena la pidió después el
# lodge: «para los botones de cenas de ambos restaurantes colocquemos la función de los
# check al igual que en los total de desayunos, para llevar el control de quién ya vino a
# cenar y las reservas faltantes».
#
# ALMUERZO no está porque nadie lo ha pedido, no porque no quepa: agregarlo aquí lo
# habilita entero —tabla, endpoint y lista— sin tocar nada más.
COMIDAS_CON_CONTROL = ("DESAYUNO", "CENA")


def _comida_valida(comida):
    """Normaliza el nombre de la comida, o lanza ValueError.

    Se comprueba y no se confía: una comida escrita de otra forma —«cena», «Cena»,
    «CENA2»— guardaría una marca que después ninguna lista lee, y el salón vería la
    casilla destildarse sola sin ningún error de por medio.
    """
    limpia = str(comida or "").strip().upper()
    if limpia not in COMIDAS_CON_CONTROL:
        raise ValueError(
            f"«{comida}» no es una comida con control. Son: "
            + ", ".join(COMIDAS_CON_CONTROL))
    return limpia


def servidos_del_dia(conn, fecha, comida):
    """{conf_no} de las reservas que ya vinieron a esa comida ese día.

    EN UNA SOLA FUNCIÓN para las dos comidas y para las tres listas que la miran —los
    desayunos, la cena de Terra Kitchen y la del Bar el Bosque—, por la misma razón de
    siempre en este sistema: con una consulta copiada en cada sitio, el día que una
    aprendiera algo las otras se quedarían atrás y la misma habitación saldría servida en
    una pantalla y pendiente en otra.
    """
    import sqlite3 as _sq
    try:
        return {r[0] for r in conn.execute(
            "SELECT conf_no FROM comida_servida WHERE fecha = ? AND comida = ?",
            (_iso(fecha), _comida_valida(comida)))}
    except _sq.OperationalError:
        # Una base que todavía no migró no puede dejar sin lista al salón.
        return set()


def marcar_servido(conn, fecha, conf_no, comida, servido, usuario=None):
    """Marca (o desmarca) que una reserva ya vino a esa comida. Devuelve los conf_no
    que quedan marcados para esa comida ese día.

    SE PUEDE DESMARCAR. Un check es un gesto de una sola pulsación que se hace de pie en
    la puerta del comedor con el salón lleno, y se pone en la fila de al lado sin querer;
    si no se pudiera quitar, la única salida sería dejar el error puesto y dejar de
    confiar en la lista entera.

    Destildar BORRA la fila: ver el comentario de la tabla en schema.sql.
    """
    comida = _comida_valida(comida)
    fecha = _iso(fecha)
    conf_no = str(conf_no)
    if servido:
        conn.execute(
            """INSERT INTO comida_servida (fecha, conf_no, comida, servido_en, servido_por)
               VALUES (?,?,?,datetime('now'),?)
               ON CONFLICT(fecha, conf_no, comida) DO UPDATE SET
                 servido_en = excluded.servido_en, servido_por = excluded.servido_por""",
            (fecha, conf_no, comida, usuario))
    else:
        conn.execute(
            "DELETE FROM comida_servida WHERE fecha = ? AND conf_no = ? AND comida = ?",
            (fecha, conf_no, comida))
    conn.commit()
    return sorted(servidos_del_dia(conn, fecha, comida))


def marcar_quien_ya_vino(conn, fecha, listas, comida):
    """Le pone `servido` a cada comensal de esas listas. Devuelve cuántos van servidos.

    Las listas son las que devuelve distribuir(): se les añade la marca EN EL SERVIDOR y
    no en la pantalla, para que el número del botón y la casilla de la fila salgan del
    mismo sitio. Contándolo en dos lados, uno acabaría diciendo otra cosa.
    """
    servidos = servidos_del_dia(conn, fecha, comida)
    cuantos = 0
    for lista in listas:
        for x in lista or []:
            x["servido"] = str(x.get("conf_no")) in servidos
            cuantos += bool(x["servido"])
    return cuantos


# CUÁNTAS MESAS A LA MISMA HORA EMPIEZAN A APRETAR.
#
# Lo pidió el lodge: «al momento de tratar de ingresar la tercera reserva a la misma hora
# en el mismo restaurante, emitir una advertencia de que ya existen 2 reservas a esa hora
# y debe ser tomada en cuenta, para poder colocarla a otra hora o bien dejar la hora
# solicitada pero ya queda indicado el tema».
#
# O sea: a la TERCERA se avisa. Con dos ya puestas, la siguiente lo dispara.
MESAS_QUE_APRIETAN = 2


def mesas_a_esa_hora(conn, fecha, hora, conf_no, cache=None):
    """Qué otras mesas tienen reservada esa hora, en el restaurante de esa reserva.

    Devuelve {'restaurante': …, 'mesas': [{'habitaciones': [...], 'pax': n, 'nombre': …}]}
    o None si esa reserva no cena esa noche.

    SE CUENTAN MESAS, NO HABITACIONES, y es la decisión que hace que el aviso sirva. El
    reparto nunca separa a un grupo: las tres habitaciones de una familia se sientan
    juntas y comparten hora, así que contándolas por separado el aviso saltaría SIEMPRE
    que se le pone la hora a un grupo —justo cuando no hay nada que avisar, porque es una
    sola mesa—. Y un aviso que salta siempre se deja de mirar.

    LA MESA QUE SE ESTÁ PONIENDO NO SE CUENTA A SÍ MISMA, ni a sus compañeras de grupo:
    la pregunta es cuántas OTRAS mesas tendría que atender el salón a esa hora.
    """
    if not hora:
        return None
    datos = distribuir(conn, fecha, cache)
    cena = datos["cena"]
    for nombre, lista in ((TERRA, cena["terra_kitchen"]),
                          (BOSQUE, cena["bar_el_bosque"])):
        yo = next((x for x in lista if str(x.get("conf_no")) == str(conf_no)), None)
        if yo is None:
            continue
        # 'grupo' es la clave del grupo, o None cuando la reserva va sola: lo que
        # devuelve distribuir(). Una reserva sola es una mesa de una.
        mia = yo.get("grupo") or f"r{conf_no}"
        mesas = {}
        for x in lista:
            if (x.get("hora") or "") != hora:
                continue
            clave = x.get("grupo") or f"r{x.get('conf_no')}"
            if clave == mia:
                continue
            m = mesas.setdefault(clave, {"habitaciones": [], "pax": 0,
                                         "nombre": x.get("nombre")})
            if x.get("room_no"):
                m["habitaciones"].append(x["room_no"])
            m["pax"] += x.get("pax") or 0
        return {"restaurante": nombre, "mesas": list(mesas.values())}
    return None


def aviso_de_horario(conn, fecha, hora, conf_no, cache=None):
    """El texto que hay que enseñarle al salonero, o None si no hay nada que decir.

    NO BLOQUEA, AVISA. Es la misma decisión que en el spa y en la agenda de tours: el
    salón sabe si puede con tres mesas a la misma hora —depende de cuánta gente sea y de
    quién esté sirviendo— y bloquearlo llevaría a poner una hora falsa para saltarse el
    sistema, que es peor que una mesa apretada.
    """
    datos = mesas_a_esa_hora(conn, fecha, hora, conf_no, cache)
    if not datos or len(datos["mesas"]) < MESAS_QUE_APRIETAN:
        return None
    quienes = " · ".join(
        f"hab. {'+'.join(m['habitaciones']) or '?'} ({m['pax']} pax)"
        for m in datos["mesas"])
    return (f"Ya hay {len(datos['mesas'])} mesas a las {hora} en "
            f"{datos['restaurante']}: {quienes}. Esta sería la "
            f"{len(datos['mesas']) + 1}ª.")


# ---------------------------------------------------------------------------
# Un movimiento manual no mueve a nadie más
# ---------------------------------------------------------------------------
#
# EL PROBLEMA. El reparto no se guarda: se recalcula entero cada vez a partir de las
# reservas, el histórico y las excepciones. Así que al mover UNA habitación a mano, el
# equilibrio se rehacía desde cero y el hueco que dejaba lo llenaba otra —«de Bar el
# Bosque a Terra Kitchen»— sin que nadie lo hubiera pedido.
#
# Medido sobre la base del lodge, 45 noches seguidas: en 39 un solo movimiento manual
# arrastraba al menos otra habitación, y la noche del 30 de noviembre arrastraba SIETE.
# No es un intercambio de uno por uno: al cambiar el objetivo de Terra Kitchen se
# recoloca todo el que estuviera libre.
#
# Lo pidió el lodge: «cuando se haga un movimiento manual, dejarlo tal y como se
# realizó, que no haga ningún otro movimiento automático».
#
# LA SOLUCIÓN. Antes de escribir el cambio se anota dónde estaba cada quien, con la
# marca 'congelado'. Son filas que no decidió una persona: solo sostienen la foto.
#
# QUÉ NO CAMBIA, que es lo que hay que mirar al tocar esto:
#   · Las reglas siguen enteras —prioridad de la cena de bienvenida, capacidades,
#     grupos que no se separan— y se aplican a quien siga libre: una reserva que entre
#     a ese día DESPUÉS del movimiento se coloca con las reglas de siempre, y se sigue
#     respetando el tope de Terra Kitchen.
#   · Los demás días no se tocan: la marca es de una fecha y una comida.
#   · A quien fija OTRA regla —cena privada, restaurante fijo de la estadía— no se le
#     escribe nada: esa regla tiene que poder dejar de aplicar.
#   · Los avisos de capacidad y de diferencia siguen saltando. Si el movimiento deja la
#     noche desequilibrada, se dice; lo que ya no se hace es arreglarlo por cuenta
#     propia.
MOTIVO_CONGELADO = "quedó donde estaba al mover otra habitación"


def fijar_el_resto(conn, fecha, comida):
    """Clava el reparto de ese día y esa comida tal como está en este momento.

    Se llama ANTES de escribir un movimiento manual, así que la foto que queda es la de
    antes de moverlo: el resultado es la misma noche con una habitación cambiada.

    No pisa nada: quien ya tenga fila —puesta a mano o congelada— se queda como está.
    Devuelve cuántas habitaciones quedaron fijadas por esto.
    """
    if isinstance(fecha, str):
        fecha = datetime.date.fromisoformat(fecha)
    comida = (comida or "CENA").upper()
    clave = "cena" if comida == "CENA" else "almuerzo"
    dist = distribuir(conn, fecha)

    fijadas = 0
    for lista, restaurante in ((dist[clave]["terra_kitchen"], TERRA),
                               (dist[clave]["bar_el_bosque"], BOSQUE),
                               (dist[clave]["comedor_staff"], STAFF)):
        for x in lista:
            if x["manual"] or x["fijo"]:
                continue
            cur = conn.execute(
                """INSERT INTO restaurante_cambio
                     (fecha, conf_no, comida, restaurante, motivo, congelado)
                   VALUES (?,?,?,?,?,1)
                   ON CONFLICT(fecha, conf_no, comida) DO NOTHING""",
                (_iso(fecha), x["conf_no"], comida, restaurante, MOTIVO_CONGELADO))
            fijadas += cur.rowcount or 0
    return fijadas


def soltar_el_reparto(conn, fecha, comida=None):
    """Quita las filas congeladas y devuelve el día al reparto automático.

    Los cambios que puso una persona NO se tocan: son decisiones, no foto. El día vuelve
    a equilibrarse alrededor de ellas, que es lo que hacía antes de esta corrección.

    Existe para que fijar la noche no sea una puerta de un solo sentido.
    """
    cond, params = "fecha = ? AND congelado = 1", [_iso(fecha)]
    if comida:
        cond += " AND comida = ?"
        params.append((comida or "").upper())
    return conn.execute(
        f"DELETE FROM restaurante_cambio WHERE {cond}", params).rowcount or 0


def mover_grupo(conn, fecha, conf_no, comida, restaurante, solo_esta=False,
                motivo="solicitud del huésped"):
    """Mueve una reserva de restaurante y, si va en grupo, se lleva a los suyos.

    El reparto automático NUNCA separa a un grupo (ver _agrupar), pero el cambio manual
    sí lo hacía: movía una habitación sola y las otras siete de la agencia se quedaban en
    el otro restaurante. La regla del módulo decía una cosa y el botón hacía otra, y lo
    descubría el salonero con la gente ya sentada.

    Quién NO se arrastra, y por qué:

      · Quien ya tiene su propio cambio manual a un sitio distinto. Alguien lo separó a
        propósito —«esta pareja cena aparte»— y volver a juntarla desharía esa decisión
        sin avisar. Se informa en vez de pisarla.
      · Quien tiene cena privada esa noche. No está en la mesa del grupo: está en la
        piscina. Moverlo de restaurante no significa nada y le quitaría el sitio que su
        cena privada ocupa en Bar el Bosque.

    Devuelve (aplicadas, excepciones). No hace commit: lo hace quien llama, una sola vez.
    """
    if isinstance(fecha, str):
        fecha = datetime.date.fromisoformat(fecha)
    comida = (comida or "CENA").upper()

    # LO PRIMERO: la foto de cómo está el día, para que mover a esta habitación no
    # mueva a ninguna otra. Va aquí y no en el endpoint para que valga por cualquier
    # camino que escriba un cambio. Ver fijar_el_resto.
    fijar_el_resto(conn, fecha, comida)

    manuales = _cambios_manuales(conn, fecha)

    # SOLO CUENTA LO QUE DECIDIÓ UNA PERSONA. Las filas congeladas también clavan a una
    # reserva, pero nadie las pidió: son la foto del día. Mirándolas, la regla de «a
    # quien ya separaron a mano no se le pisa» se rompía —todas las habitaciones pasaban
    # a tener fila, así que la que alguien había apartado a propósito dejaba de
    # distinguirse de las demás y el grupo se la llevaba de vuelta—. Lo encontró la
    # prueba a_quien_ya_separaron_a_mano_no_se_le_pisa.
    def puesto_a_mano(cn):
        m = manuales.get((cn, comida))
        return m["restaurante"] if m and not m.get("congelado") else None

    anterior = puesto_a_mano(conf_no)

    def escribir(cn):
        # 'congelado = 0' también al actualizar: la fila que sostenía la foto pasa a ser
        # una decisión de una persona en cuanto alguien mueve esa habitación. Sin esa
        # línea, el cambio se guardaba bien pero la pantalla no lo marcaba como manual
        # —y «volver al reparto automático» se lo habría llevado por delante—.
        conn.execute(
            """INSERT INTO restaurante_cambio
                 (fecha, conf_no, comida, restaurante, motivo, congelado)
               VALUES (?,?,?,?,?,0)
               ON CONFLICT(fecha, conf_no, comida) DO UPDATE SET
                 restaurante = excluded.restaurante, motivo = excluded.motivo,
                 congelado = 0, creado_en = datetime('now')""",
            (_iso(fecha), cn, comida, restaurante, motivo))

    escribir(conf_no)
    if solo_esta:
        return [], []

    privadas = _cenas_privadas(conn, fecha) if comida == "CENA" else set()
    aplicadas, excepciones = [], []
    for c in companeros_de_mesa(conn, fecha, conf_no):
        cn = c["conf_no"]
        if cn in privadas:
            excepciones.append(dict(c, motivo="tiene cena privada"))
            continue
        suyo = puesto_a_mano(cn)
        if suyo and suyo != anterior and suyo != restaurante:
            excepciones.append(dict(c, motivo=f"ya estaba puesta a mano en {suyo}"))
            continue
        escribir(cn)
        aplicadas.append(c)
    return aplicadas, excepciones


def distribuir(conn, fecha, cache=None):
    """Devuelve la distribución de almuerzo y cena para esa fecha.

    No guarda nada: la asignación se calcula cada vez a partir de las reservas,
    los cambios manuales y el histórico. Solo las excepciones se persisten.

    `cache` es opcional y solo evita releer la tabla de reservas cuando se piden varios
    días seguidos (ver _reservas_base). No cambia el resultado de ningún día.
    """
    if isinstance(fecha, str):
        fecha = datetime.date.fromisoformat(fecha)
    entradas, en_casa, salidas = _reservas_del_dia(conn, fecha, cache)
    hist = _historial(conn, fecha)
    manuales = _cambios_manuales(conn, fecha)
    privadas = _cenas_privadas(conn, fecha)

    # Las filas CONGELADAS clavan igual que las manuales —para eso están— pero nadie las
    # pidió: solo sostienen la foto del día (ver fijar_el_resto). En pantalla no se
    # enseñan como un cambio, o el salonero vería treinta habitaciones «movidas a mano»
    # la noche en que recepción movió una.
    a_mano = {k for k, v in manuales.items() if not v.get("congelado")}
    congelada = {c: any(k[1] == c.upper() and v.get("congelado")
                        for k, v in manuales.items())
                 for c in ("cena", "almuerzo")}

    notas = []          # movimientos explicados, para que el salonero tenga el contexto
    avisos = []

    # ---------- CENA ----------
    # Fijos: cena privada, restaurante forzado de la estadía y cambios manuales
    fijos = {}
    for r in entradas + en_casa:
        cn = r["conf_no"]
        if cn in privadas:
            fijos[cn] = (BOSQUE, "cena privada")
        elif r.get("forzar_restaurante"):
            fijos[cn] = (r["forzar_restaurante"], "restaurante fijo de la estadía")
        m = manuales.get((cn, "CENA"))
        if m:
            fijos[cn] = (m["restaurante"], m.get("motivo") or "cambio manual")

    # Quien cena en el comedor del staff sale del reparto ENTERO: no ocupa sitio en
    # ninguno de los dos restaurantes y no cuenta para equilibrarlos. Ver STAFF.
    staff_cena = [r for r in entradas + en_casa
                  if fijos.get(r["conf_no"], ("",))[0] == STAFF]
    en_staff = {r["conf_no"] for r in staff_cena}

    libres = [r for r in entradas + en_casa if r["conf_no"] not in fijos]
    tk_fijo = [r for r in entradas + en_casa if fijos.get(r["conf_no"], ("",))[0] == TERRA]
    bosque_fijo = [r for r in entradas + en_casa if fijos.get(r["conf_no"], ("",))[0] == BOSQUE]

    # Prioridad para Terra Kitchen: rezagados, entradas, en casa por rotación
    def prioridad(r):
        h = hist.get(r["conf_no"], {})
        debe = h.get("debe_bienvenida", False)
        if debe:
            # Entre rezagados, primero el que se va antes
            return (0, r.get("noches_restantes", 99), 0)
        if r["tipo"] == "ENTRA":
            return (1, 0, 0)
        # En casa: primero quien lleva más noches sin cenar en Terra Kitchen y
        # quien tiene menos noches por delante
        tk, noches = h.get("tk", 0), max(h.get("noches", 0), 1)
        proporcion = tk / noches
        return (2, r.get("noches_restantes", 99), proporcion)

    bloques = sorted(_agrupar(libres), key=lambda b: min(prioridad(r) for r in b["reservas"]))

    # SIN LOS DEL COMEDOR DEL STAFF. Contándolos, el objetivo de Terra Kitchen se
    # calculaba sobre gente que no se iba a sentar en ninguno de los dos, y el aviso de
    # «no se puede equilibrar» saltaba por pax que no existían para el servicio.
    total_cena = (_pax([r for r in entradas if r["conf_no"] not in en_staff])
                  + _pax([r for r in en_casa if r["conf_no"] not in en_staff]))
    objetivo_tk = max(0, min(CAP_CENA_TK, (total_cena + 1) // 2))

    tk, bosque = list(tk_fijo), list(bosque_fijo)
    pax_tk, pax_bosque = _pax(_agrupar(tk_fijo)), _pax(_agrupar(bosque_fijo))

    for b in bloques:
        cabe_tk = pax_tk + b["pax"] <= CAP_CENA_TK
        # Se llena Terra Kitchen hasta el objetivo; el resto va a Bar el Bosque
        if cabe_tk and pax_tk < objetivo_tk:
            tk.extend(b["reservas"]); pax_tk += b["pax"]
        else:
            bosque.extend(b["reservas"]); pax_bosque += b["pax"]
            for r in b["reservas"]:
                if r["tipo"] == "ENTRA":
                    motivo = ("Terra Kitchen al tope" if not cabe_tk
                              else "para equilibrar los restaurantes")
                    notas.append({
                        "room_no": r["room_no"], "nombre": r["nombre_principal"],
                        "pax": r["pax"], "de": TERRA, "a": BOSQUE,
                        "motivo": motivo, "rezagado": True,
                    })

    # Los en casa que entraron a Terra Kitchen: se explica por qué
    for r in tk:
        if r["tipo"] == "EN_CASA" and r["conf_no"] not in fijos:
            notas.append({
                "room_no": r["room_no"], "nombre": r["nombre_principal"],
                "pax": r["pax"], "de": BOSQUE, "a": TERRA,
                "motivo": "para equilibrar los restaurantes", "rezagado": False,
            })

    diferencia = abs(pax_tk - pax_bosque)
    if total_cena > TOTAL_MAX_BALANCEABLE:
        avisos.append(
            f"Noche de {total_cena} pax: no se puede equilibrar porque Terra Kitchen "
            f"topa en {CAP_CENA_TK}. Diferencia inevitable de {diferencia} pax.")
    elif diferencia > MARGEN_BALANCE:
        avisos.append(
            f"La diferencia quedó en {diferencia} pax (margen {MARGEN_BALANCE}). "
            f"Los grupos no se dividen, así que no siempre se puede ajustar más.")
    if pax_bosque > CAP_CENA_BOSQUE:
        avisos.append(f"Bar el Bosque queda con {pax_bosque} pax y su tope es {CAP_CENA_BOSQUE}.")
    if total_cena > CAP_CENA_TK + CAP_CENA_BOSQUE:
        avisos.append(f"{total_cena} pax superan la capacidad total de la propiedad "
                      f"({CAP_CENA_TK + CAP_CENA_BOSQUE}).")

    # ---------- ALMUERZO ----------
    # Los de tour almuerzan en el hotel al regresar, así que cuentan como en casa.
    # El comedor del staff va por comida, igual que los otros dos: a alguien se le puede
    # mandar el almuerzo al comedor y dejarle la cena en el restaurante.
    alm_tk, alm_bosque, alm_staff = [], [], []
    for r in en_casa + entradas:
        m = manuales.get((r["conf_no"], "ALMUERZO"))
        if m and m["restaurante"] == STAFF:
            alm_staff.append(r)
            continue
        if r["tipo"] == "ENTRA":
            (alm_tk if (m and m["restaurante"] == TERRA) else alm_bosque).append(r)
        else:
            (alm_bosque if (m and m["restaurante"] == BOSQUE) else alm_tk).append(r)

    # Si el almuerzo en Terra Kitchen se pasa del tope, el sobrante va a Bar el Bosque
    # con el mismo criterio de prioridad.
    if _pax(_agrupar(alm_tk)) > CAP_ALMUERZO_TK:
        sobra = _pax(_agrupar(alm_tk)) - CAP_ALMUERZO_TK
        movibles = sorted(_agrupar([r for r in alm_tk if r["tipo"] == "EN_CASA"]),
                          key=lambda b: -b["pax"])
        for b in movibles:
            if sobra <= 0:
                break
            for r in b["reservas"]:
                alm_tk.remove(r); alm_bosque.append(r)
            sobra -= b["pax"]
            notas.append({
                "room_no": ", ".join(x["room_no"] or "?" for x in b["reservas"]),
                "nombre": b["reservas"][0]["nombre_principal"],
                "pax": b["pax"], "de": TERRA, "a": BOSQUE,
                "motivo": f"almuerzo en Terra Kitchen al tope ({CAP_ALMUERZO_TK})",
                "rezagado": False, "comida": "almuerzo",
            })
        avisos.append(f"El almuerzo en Terra Kitchen superaba el tope de {CAP_ALMUERZO_TK} pax.")

    # Horas de mesa que registró el salonero
    horas = {dict(r)["conf_no"]: dict(r)["hora"] for r in conn.execute(
        "SELECT conf_no, hora FROM restaurante_hora WHERE fecha = ?", (_iso(fecha),))}

    def salida(lista, comida):
        out = []
        for r in sorted(lista, key=lambda x: int(x["room_no"]) if (x["room_no"] or "").isdigit() else 999):
            fijo = fijos.get(r["conf_no"]) if comida == "cena" else None
            if fijo and fijo[1] == MOTIVO_CONGELADO:
                fijo = None          # sostiene la foto, no es una decisión que enseñar
            out.append({
                "conf_no": r["conf_no"], "room_no": r["room_no"],
                "nombre": r["nombre_principal"], "pax": r["pax"], "tipo": r["tipo"],
                # CUÁNTOS DE ESOS PAX SON NIÑOS. A la cocina le cambia la porción y al
                # salonero la silla; en la mesa no se distinguen de los adultos hasta que
                # están sentados. Lo pidió el lodge.
                "ninos": r.get("chl") or 0,
                "noche_estadia": r.get("noche_estadia"), "noches": r["noches"],
                "grupo": r["clave_grupo"] if not r["clave_grupo"].startswith("r") else None,
                "hora": horas.get(r["conf_no"]) if comida == "cena" else None,
                "fijo": fijo[1] if fijo else None,
                "manual": (r["conf_no"], comida.upper()) in a_mano,
                # Para el salonero: qué trae pagado y si ESTA comida le corresponde.
                "regimen": r.get("regimen"),
                "regimen_texto": texto_regimen(r.get("regimen")),
                "incluye_esta_comida": incluye_comida(r.get("regimen"), comida),
                # Y lo demás que trae pagado, que también se decide antes de servir:
                # qué bebidas incluye y si la reserva es de cortesía. Va el TEXTO de la
                # reserva, no un sí/no: «CPL en hospedaje» y «CPL boat transfer» no son
                # lo mismo, y quien pasa la cuenta necesita leer cuál de los dos es.
                "bebidas": r.get("bebidas_incluidas"),
                "cortesia": r.get("cortesia"),
            })
        return out

    return {
        "fecha": _iso(fecha),
        "cena": {
            "terra_kitchen": salida(tk, "cena"), "bar_el_bosque": salida(bosque, "cena"),
            "pax_tk": pax_tk, "pax_bosque": pax_bosque, "total": total_cena,
            "cap_tk": CAP_CENA_TK, "cap_bosque": CAP_CENA_BOSQUE,
            "diferencia": diferencia, "dentro_margen": diferencia <= MARGEN_BALANCE,
            # Los del comedor del staff van APARTE y no suman en 'total': no ocupan sitio
            # en ninguno de los dos restaurantes. Se devuelven para que la pantalla pueda
            # enseñarlos y traerlos de vuelta — moverlos no puede ser una puerta de una
            # sola dirección.
            "comedor_staff": salida(staff_cena, "cena"),
            "pax_staff": _pax(_agrupar(staff_cena)),
            # La noche quedó fijada por un movimiento manual: nadie más se reacomoda
            # solo. La pantalla lo dice y ofrece devolverla al reparto automático —si no
            # se dijera, el día dejaría de equilibrarse en silencio.
            "fijada_a_mano": congelada["cena"],
        },
        "almuerzo": {
            "terra_kitchen": salida(alm_tk, "almuerzo"), "bar_el_bosque": salida(alm_bosque, "almuerzo"),
            "pax_tk": _pax(_agrupar(alm_tk)), "pax_bosque": _pax(_agrupar(alm_bosque)),
            "total": _pax(_agrupar(alm_tk)) + _pax(_agrupar(alm_bosque)),
            "cap_tk": CAP_ALMUERZO_TK,
            "comedor_staff": salida(alm_staff, "almuerzo"),
            "pax_staff": _pax(_agrupar(alm_staff)),
            "fijada_a_mano": congelada["almuerzo"],
        },
        "notas": notas,
        "avisos": avisos,
        "salen": [{"room_no": r["room_no"], "nombre": r["nombre_principal"],
                   "pax": r["pax"]} for r in salidas],
        "cenas_privadas": sorted(privadas),
        # La información de cada una, para que la pantalla muestre de quién es y qué
        # lleva en vez de solo cuántas hay. Va como campo aparte y no cambiando el de
        # arriba, que otras cosas usan como lista de números de reserva.
        "cenas_privadas_info": info_cenas_privadas(conn, fecha),
        # Contratadas pero sin noche puesta: no entran en el reparto todavía, y por eso
        # hay que reclamarlas en pantalla mientras el huésped está en casa.
        "cenas_privadas_sin_noche": _privadas_sin_noche(
            conn, [r["conf_no"] for r in entradas + en_casa]),
    }


# ---------------------------------------------------------------------------
# Congelado del pasado y avisos anticipados
# ---------------------------------------------------------------------------

def congelar_dias_pasados(conn, hasta=None):
    """Guarda la asignación de los días que ya terminaron.

    Sin esto, al importar un PDF nuevo el pasado se recalcularía y podría cambiar:
    la rotación quedaría mal y una deuda de cena de bienvenida podría desaparecer
    después de que recepción ya se lo prometió al huésped.
    """
    hoy = hasta or datetime.date.today()
    ultimo = conn.execute("SELECT MAX(fecha) f FROM restaurante_historico").fetchone()["f"]
    if ultimo:
        desde = datetime.date.fromisoformat(ultimo) + datetime.timedelta(days=1)
    else:
        prim = conn.execute(
            "SELECT MIN(arr_date) a FROM reserva WHERE res_status != 'CANCELADA'").fetchone()["a"]
        desde = _a_fecha(prim) if prim else hoy
    if not desde:
        return 0

    guardados = 0
    d = desde
    # Una sola lectura de reservas para todos los días que falten congelar. El histórico
    # NO se guarda en caché: es justo lo que este bucle va escribiendo, y cada día tiene
    # que ver lo que dejó el anterior.
    cache = {}
    while d < hoy:
        dist = distribuir(conn, d, cache)
        for lugar, restaurante in ((dist["cena"]["terra_kitchen"], TERRA),
                                   (dist["cena"]["bar_el_bosque"], BOSQUE)):
            for x in lugar:
                alm = TERRA if any(y["conf_no"] == x["conf_no"]
                                   for y in dist["almuerzo"]["terra_kitchen"]) else BOSQUE
                conn.execute(
                    """INSERT INTO restaurante_historico (fecha, conf_no, almuerzo, cena, era_entrada)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(fecha, conf_no) DO UPDATE SET
                         almuerzo=excluded.almuerzo, cena=excluded.cena,
                         era_entrada=excluded.era_entrada""",
                    (_iso(d), x["conf_no"], alm, restaurante, 1 if x["tipo"] == "ENTRA" else 0))
                guardados += 1
        d += datetime.timedelta(days=1)
    conn.commit()
    return guardados


def avisos_anticipados(conn, dias=30, desde=None):
    """Noches futuras que no van a caber o no se van a poder equilibrar.

    Igual que el aviso de entradas al SINAC: mejor saberlo con semanas de
    anticipación que descubrirlo el mismo día.
    """
    inicio = desde or datetime.date.today()
    problemas = []
    cache = {}          # una lectura de reservas para los 30 días, no 30 lecturas
    for i in range(dias):
        f = inicio + datetime.timedelta(days=i)
        entradas, en_casa, _ = _reservas_del_dia(conn, f, cache)
        total = sum(r["pax"] for r in entradas + en_casa)
        if not total:
            continue
        if total > CAP_CENA_TK + CAP_CENA_BOSQUE:
            problemas.append({"fecha": _iso(f), "total": total, "gravedad": "NO_CABE",
                              "mensaje": f"{total} pax superan la capacidad total "
                                         f"({CAP_CENA_TK + CAP_CENA_BOSQUE}). Hay que abrir otro turno."})
        elif total > TOTAL_MAX_BALANCEABLE:
            problemas.append({"fecha": _iso(f), "total": total, "gravedad": "SIN_BALANCE",
                              "mensaje": f"{total} pax: no se podrá equilibrar, "
                                         f"Terra Kitchen quedará al tope de {CAP_CENA_TK}."})
    return problemas


def resumen_dia(conn, fecha):
    """Totales para la hoja de operación, que es la que consulta cocina."""
    d = distribuir(conn, fecha)
    return {
        "fecha": d["fecha"],
        "almuerzo_tk": d["almuerzo"]["pax_tk"], "almuerzo_bosque": d["almuerzo"]["pax_bosque"],
        "cena_tk": d["cena"]["pax_tk"], "cena_bosque": d["cena"]["pax_bosque"],
        "avisos": d["avisos"],
    }
