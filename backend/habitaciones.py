"""Las habitaciones del lodge, y las que no se venden pero duermen gente.

LOS CUARTOS DE GUÍAS. El lodge tiene 30 habitaciones vendibles —de la 01 a la 30— y
además unos cuartos en la casa de guías. Esos no son habitaciones de hotel: no se venden
y solo aparecen cuando Reservas mete ahí al guía de un grupo. Opera los manda con su
propio número y una «G» detrás:

    31G   es el cuarto 16 de la casa de guías
    32G   es el cuarto 15

Lo pidió el lodge: «estas no corresponden de forma directa como habitaciones de hotel,
porque solo se habilitan cuando Reservas coloca el guía ahí; hay que contarlas dentro de
la operación cuando aparezcan y que actúe como una habitación más del hotel con el grupo
que corresponda».

QUÉ HACE FALTA PARA ESO, Y QUÉ NO. Medido antes de tocar nada: una reserva en «31G» YA
entraba en el resumen, en los desayunos, en el reparto del comedor, en la hoja del día y
viajaba con su grupo —el block code la junta con las habitaciones a las que acompaña—.
Eso no se toca. Lo que faltaba es lo que este módulo resuelve:

  · el NOMBRE. «31G» no le dice nada a quien lee la hoja en el muelle, y traducirlo a
    «16» a secas sería peor: el lodge ya tiene una habitación 16 de huéspedes y habría
    dos renglones con el mismo número. Se escribe «G16», que no se confunde con ninguna;
  · el ORDEN. Las listas ordenan con CAST(room_no AS INTEGER), y de «G16» eso da 0: el
    cuarto de guías se habría puesto ANTES de la 01 en todas las pantallas. Aquí está la
    expresión que los manda al final, después de la 30;
  · la OCUPACIÓN. No es una habitación que se vende, así que no cuenta para el
    porcentaje: con 31 cuartos ocupados sobre 30 vendibles, el informe habría pasado del
    100% sin que nadie hubiera vendido de más. Sigue contando en todo lo demás.
"""

# El mapa que dio el lodge. Se agrega un cuarto escribiendo un renglón aquí.
CUARTOS_DE_GUIA = {
    "31G": "G16",
    "32G": "G15",
}

# Cómo se reconoce uno que todavía no esté en el mapa: el número de Opera con una «G»
# detrás. Hace falta porque el lodge puede habilitar otro cuarto sin avisar, y es mejor
# que salga como «G33» —marcado como cuarto de guías, en su sitio al final de la lista—
# a que entre como una habitación de hotel más y descuadre la ocupación en silencio.
SUFIJO = "G"


def _limpio(room_no):
    return str(room_no or "").strip().upper()


def es_de_guia(room_no):
    """¿Ese número es un cuarto de la casa de guías y no una habitación de hotel?"""
    hab = _limpio(room_no)
    if not hab:
        return False
    if hab in CUARTOS_DE_GUIA or hab in set(CUARTOS_DE_GUIA.values()):
        return True
    # «31G», y también el «G31» que deja este mismo módulo al normalizar.
    return (hab.endswith(SUFIJO) and hab[:-1].isdigit()) or \
           (hab.startswith(SUFIJO) and hab[1:].isdigit())


def normalizar(room_no):
    """El número con el que el cuarto se escribe en TODO el sistema.

    «31G» -> «G16» (el que el lodge usa hablando), y cualquier otro cuarto de guías que
    aparezca sin estar en el mapa -> «G» + su número, para que al menos se reconozca.
    Una habitación normal se devuelve tal cual.

    Se normaliza AL GUARDAR y no al dibujar, a propósito: hay quince consultas que
    ordenan y agrupan por este número, y traducirlo en cada pantalla habría dejado a una
    diciendo «31G» y a la de al lado «G16» en cuanto alguien olvidara una.
    """
    hab = _limpio(room_no)
    if not hab:
        return room_no
    if hab in CUARTOS_DE_GUIA:
        return CUARTOS_DE_GUIA[hab]
    if hab.endswith(SUFIJO) and hab[:-1].isdigit():
        return SUFIJO + hab[:-1]
    return room_no


def sql_orden(col="room_no"):
    """La expresión para ordenar por habitación dejando los cuartos de guías al final.

    Las listas ordenaban con CAST(room_no AS INTEGER) a secas, y de cualquier cosa que no
    empiece por un dígito eso da 0: el cuarto de guías se habría colado delante de la 01
    en las quince pantallas que ordenan así. No daba error, daba una lista en la que el
    primer renglón no es el que uno espera.

    Va aquí y no copiada en cada consulta por lo mismo que sql_fecha: con quince copias,
    el día que una cambie las listas empiezan a ordenar distinto según por dónde se miren.
    """
    return (f"CASE WHEN {col} GLOB '[0-9]*' THEN CAST({col} AS INTEGER) ELSE 9999 END, "
            f"{col}")


# Las dos formas con las que se escribe la columna en las consultas del sistema, ya
# armadas. Van como constantes para poder pegarlas en una consulta que NO es f-string,
# que es como están escritas la mitad: convertirlas a f-string solo para esto habría
# obligado a escapar todas las llaves que ya tienen dentro.
ORDEN = sql_orden("room_no")
ORDEN_R = sql_orden("r.room_no")


def orden(room_no):
    """Lo mismo que sql_orden, para ordenar en Python."""
    hab = _limpio(room_no)
    cabeza = ""
    for ch in hab:
        if not ch.isdigit():
            break
        cabeza += ch
    return (int(cabeza), hab) if cabeza else (9999, hab)


def solo_las_que_se_venden(habs):
    """Las habitaciones de hotel de esa lista, sin los cuartos de guías.

    Es lo que hay que contar para la OCUPACIÓN: un cuarto de guías no se vende, así que
    no puede subir el porcentaje. Con 31 ocupados sobre 30 vendibles el informe habría
    pasado del 100% sin que nadie hubiera vendido de más.
    """
    return {h for h in habs if h and not es_de_guia(h)}
