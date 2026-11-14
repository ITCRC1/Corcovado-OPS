"""La hoja del día que se le manda al staff, con el formato que el lodge ya usa.

POR QUÉ EXISTE. El lodge arma a mano un Excel y manda un pantallazo al grupo con la
operación del día siguiente. Casi todo lo que lleva ese Excel ya está en el sistema, pero
repartido por pantallas, así que alguien lo copiaba. Esta hoja lo entrega hecho, en PDF
para el pantallazo y en Excel para quien quiera tocarlo, mientras se completa la
transición a la app.

UNA SOLA DEFINICIÓN para los dos formatos: `definicion()` arma los datos y `pdf()` y
`excel()` los dibujan. Es la misma regla que ya cumplen los demás informes del sistema —
si el PDF y el Excel se armaran por separado, acabarían diciendo cosas distintas y el
que circula por WhatsApp es justo el que nadie contrasta.

El formato imita el del lodge a propósito: la gente que lo recibe lleva meses leyéndolo
así, y cambiarles el dibujo el mismo día que cambia la herramienta es pedirles dos cosas
a la vez.
"""
import datetime
import io

import notas as _notas
import notas_hoja as _mano

# Los colores del Excel del lodge. Se copian tal cual: el staff ya asocia el verde con
# «se queda», el rojo con «se va» y el amarillo con «llega», y eso se lee antes que el
# texto de la fila.
VERDE_CAB = "2D5A27"
VERDE_SUB = "3D7A33"
FONDO = {"EN CASA": "DFF0D8", "SALE": "F8C9C9", "ENTRA": "FDF3A6"}
LINEA = "9B9B9B"
ROJO = "C0392B"


def etiqueta_tour(t):
    """Cómo se nombra una salida en la hoja: «PNC gr.B · PRIVADO».

    En UNA función porque la hoja la escribe en tres sitios —la casilla de cada
    habitación, la caja de tours del PDF y la del Excel— y los tres tienen que decir lo
    mismo. Si uno marcara el privado y otro no, la misma salida parecería dos cosas
    distintas en la misma página.
    """
    grupo = "" if (t.get("grupo_operativo") or "A") == "A" else f" gr.{t['grupo_operativo']}"
    privado = " · PRIVADO" if t.get("es_privado") else ""
    return f"{t.get('tour_codigo') or ''}{grupo}{privado}"


# Cuánto de la nota AUTOMÁTICA cabe en la casilla. Lo escrito a mano no entra en este
# recorte: ver `nota_de_la_fila`.
TOPE_NOTA_AUTO = 110


def nota_de_la_fila(f, tope=TOPE_NOTA_AUTO):
    """Lo que dice la casilla NOTAS: lo escrito a mano delante, lo automático detrás.

    EN UNA SOLA FUNCIÓN porque esa casilla se escribe en cuatro sitios —el PDF del día,
    el del rango y los dos Excel— y los cuatro tienen que decir lo mismo. Es la misma
    razón por la que `etiqueta_tour` existe: con cuatro copias, una acaba poniendo lo
    escrito a mano detrás, o recortándolo, y la misma hoja dice dos cosas distintas según
    por dónde se mire.

    LO ESCRITO A MANO VA PRIMERO Y NO SE RECORTA. El recorte existe para que la nota de
    Opera —que llega con párrafos enteros— no se coma el renglón, y alcanza solo a esa
    parte. Alguien que escribe una nota a mano sobre la hoja del día la escribe porque
    hace falta hoy; perder la mitad por una cuenta de caracteres sería tirar justo lo que
    alguien decidió añadir.
    """
    mano = (f.get("nota_mano") or "").strip()
    auto = (f.get("notas") or "")[:tope]
    return " · ".join(x for x in (mano, auto) if x)


def _notas_con_marcado(f, escape, tope=TOPE_NOTA_AUTO):
    """Lo mismo, con lo escrito a mano en negrita, para el PDF.

    Se distingue a propósito: en una columna que mezcla lo que trajo Opera con lo que
    escribió una persona, quien lee la hoja en el muelle tiene que poder ver cuál es cuál
    —lo de la persona es lo que no está en ningún otro lado.
    """
    mano = (f.get("nota_mano") or "").strip()
    auto = (f.get("notas") or "")[:tope]
    partes = []
    if mano:
        partes.append(f"<b>{escape(mano)}</b>")
    if auto:
        partes.append(escape(auto))
    return " · ".join(partes)

# Las columnas de la tabla ancha, en el orden del Excel del lodge.
# (clave, título, ancho en mm para el PDF)
#
# LOS ANCHOS TIENEN QUE CABER EN LA HOJA. A4 apaisado da 297 mm y los márgenes se comen
# 14, así que el total no puede pasar de 283. Con 308 la tabla se salía por los dos
# lados y la primera columna se leía «CASA» en vez de «EN CASA»: justo la que dice de un
# vistazo quién llega y quién se va.
COLUMNAS = [
    ("estado", "ESTADO", 15),
    ("hab", "HAB.", 11),
    ("huesped", "HUÉSPED", 54),
    ("pax", "PAX", 8),
    ("sierpe", "SIERPE", 12),
    ("drake", "DRAKE", 12),
    ("horario", "HORARIO", 17),
    ("guia_t", "GUÍA T", 19),
    ("bote_t", "BOTE / CAPITÁN", 25),
    ("notas", "NOTAS", 46),
    # TOUR se lleva 22 y no 17 del hueco que sobraba: «CABALGATA» no entraba en 17 mm y
    # se partía en «CABALGAT / A». Un código de tour partido se lee como otro código.
    ("tour", "TOUR", 22),
    ("tour_guia", "GUÍA", 18),
    ("tour_bote", "BOTE", 18),
]
ANCHO_UTIL_MM = 283

# Las dos cajas de arriba: la de tours y la de movimientos. Ocupan juntas lo que antes
# ocupaban tres —la de «Alertas / pendientes» la quitó el lodge de la hoja que se
# reparte— y el ancho que sobró se fue casi todo a la de tours, que es donde los nombres
# de guía y de bote vivían apretados en 24 mm.
CAJA_TOURS_MM = (52, 14, 40, 40)      # tour, pax, guía, bote
CAJA_MOV_MM = (34, 20, 18)            # estado, habitaciones, pax
RANURAS_ARRIBA_MM = (150, 78)         # lo que mide cada caja con su aire alrededor

# Los tres grupos de la cabecera superior, con cuántas columnas abarca cada uno.
GRUPOS = [("HUÉSPEDES", 4), ("INGRESOS Y SALIDAS", 6), ("ACTIVIDADES", 3)]


def _nombre_legible(acompanantes, principal):
    """«Johnson/Derek» -> «DEREK JOHNSON», y los acompañantes unidos por Y.

    Es como lo escribe el lodge en su hoja —«DEREK JOHNSON Y ANDREA OGG»— y no es un
    capricho: quien la lee busca por el nombre de pila con el que saluda al huésped, no
    por el apellido del sistema.
    """
    nombres = [n.strip() for n in (acompanantes or []) if n and n.strip()]
    if not nombres:
        if "/" in (principal or ""):
            apellido, nombre = principal.split("/", 1)
            nombres = [f"{nombre.strip()} {apellido.strip()}"]
        elif principal:
            nombres = [principal]
    return " Y ".join(n.upper() for n in nombres)


def _acompanantes(conn, conf_nos):
    """{conf_no: [nombres]} del rooming, para escribir la fila como la escribe el lodge."""
    salida = {}
    if not conf_nos:
        return salida
    lista = list(conf_nos)
    for i in range(0, len(lista), 400):
        lote = lista[i:i + 400]
        marcas = ",".join("?" * len(lote))
        for f in conn.execute(
                f"""SELECT conf_no, nombre_completo FROM huesped
                    WHERE conf_no IN ({marcas}) ORDER BY id""", lote):
            salida.setdefault(f["conf_no"], []).append(f["nombre_completo"])
    return salida


def definicion(conn, fecha, resumen):
    """Los datos de la hoja. `resumen` es lo que devuelve el módulo de Resumen.

    Se recibe ya calculado a propósito: así la hoja y la pantalla no pueden contar
    distinto. Lo único que se añade aquí es el rooming (para el nombre) y la tripulación
    de cada corrida, que la hoja de Excel del lodge no tenía.
    """
    import traslados as _tras

    # Lo que alguien escribió A MANO sobre la hoja de este día. Se lee aquí y no en el
    # dibujo porque de aquí salen las cuatro salidas —PDF del día, PDF del rango y los dos
    # Excel—: leyéndolo en cada dibujo, el día que uno se olvidara, la hoja impresa y la
    # del pantallazo dirían cosas distintas. Ver notas_hoja.py.
    mano = _mano.leer(conn, fecha)

    # --- Una fila por habitación, igual que la hoja del lodge ---
    por_conf, por_hab = {}, {}

    def meter(r, estado):
        clave = r["conf_no"]
        # ENTRA y SALE mandan sobre EN CASA: el día que alguien llega o se va, eso es lo
        # que el staff necesita ver en su renglón.
        if clave in por_conf and por_conf[clave]["estado"] != "EN CASA":
            return
        fila = {
            "estado": estado,
            "hab": r.get("room_no") or "",
            "huesped": "",
            "conf_no": clave,
            "pax": (r.get("adl") or 0) + (r.get("chl") or 0),
            "sierpe": "", "drake": "", "horario": "", "guia_t": "", "bote_t": "",
            "notas": _notas.solo_lo_operativo(
                r.get("nota_salida") or r.get("nota_ingreso")),
            # Lo escrito a mano va en SU PROPIO campo y no pegado al de arriba: esa
            # columna la reescribe la carga de Opera, así que mezclarlos haría que la
            # importación siguiente se llevara por delante lo que escribió una persona.
            "nota_mano": mano["filas"].get(str(clave), ""),
            "tours": [],
            "tour": "", "tour_guia": "", "tour_bote": "",
        }
        por_conf[clave] = fila
        if fila["hab"]:
            por_hab[str(fila["hab"])] = fila

    for r in resumen.get("en_casa", []):
        meter(r, "EN CASA")
    for r in resumen.get("ingresos", []):
        meter(r, "ENTRA")
    for r in resumen.get("salidas", []):
        meter(r, "SALE")

    nombres = _acompanantes(conn, por_conf)
    for clave, fila in por_conf.items():
        origen = next((r for r in (resumen.get("en_casa", []) + resumen.get("ingresos", [])
                                   + resumen.get("salidas", []))
                       if r["conf_no"] == clave), {})
        fila["huesped"] = _nombre_legible(nombres.get(clave),
                                          origen.get("nombre_principal"))

    # --- El movimiento por muelle ---
    #
    # SE EMPAREJA POR RESERVA, NO POR HABITACIÓN. El número de habitación se reutiliza: el
    # día que un cuarto cambia de huésped, el que SE VA y el que LLEGA tienen el mismo, y
    # la fila del que se va era la última en quedarse con el cuarto. El 8 de noviembre la
    # habitación 13 salía con el vuelo del huésped que ENTRABA pegado en sus notas y con
    # la hora de otro en su horario, mientras el renglón del que entraba quedaba vacío.
    # Es la misma lección que ya está escrita aquí mismo para los tours.
    totales = {"Sierpe": {"ENTRA": 0, "SALE": 0}, "Drake": {"ENTRA": 0, "SALE": 0}}
    for punto in resumen.get("puntos", []):
        nombre_punto = punto["punto"]
        for det in punto.get("detalle", []):
            es_entrada = str(det.get("tipo") or "").lower().startswith("entrada")
            if nombre_punto in totales:
                totales[nombre_punto]["ENTRA" if es_entrada else "SALE"] += det.get("pax") or 0
            fila = por_conf.get(str(det.get("conf_no") or "")) \
                or por_hab.get(str(det.get("room_no")))
            if not fila:
                continue
            col = "sierpe" if nombre_punto.lower().startswith("sierpe") else "drake"
            fila[col] = det.get("pax") or ""
            # EL HORARIO ES EL DEL TRASLADO, NO EL DEL VUELO. Es la hora a la que el
            # huésped se mueve, que es lo único que el staff puede ejecutar: por Sierpe
            # el bote sale a su hora fija, y por Drake sale DOS HORAS ANTES del vuelo —la
            # regla que dio el lodge—. Poniendo la del vuelo, la hoja del 8 de noviembre
            # mandaba al muelle a las 9:25 a gente cuyo bote salía a las 7:25. El vuelo
            # no se pierde: va en la columna de notas, con su número.
            fila["horario"] = det.get("hora_traslado") or det.get("hora") or ""
            fila["guia_t"] = det.get("guia") or ""
            fila["bote_t"] = det.get("bote") or ""
            if det.get("vuelo"):
                # EL NÚMERO DEL VUELO Y LA HORA DEL AVIÓN. Lo volvió a pedir el lodge.
                #
                # Estuvo un tiempo sin la hora, y por un motivo que sigue siendo cierto:
                # en HORARIO va la del BOTE —que sale dos horas antes— así que en el mismo
                # renglón hay dos horas distintas y solo una se ejecuta. Por eso la del
                # avión va DICIENDO que es del avión: sin esa palabra, «7:10 … 9:10» son
                # dos cifras sueltas y la que manda no se distingue de la otra.
                vuelo = f"VUELO {det['vuelo']}"
                if det.get("hora"):
                    vuelo += f" · avión {det['hora']}"
                fila["notas"] = f"{fila['notas']} · {vuelo}".strip(" ·") if fila["notas"] else vuelo

    # --- La tripulación de cada corrida ---
    # Esto el Excel del lodge no lo tenía: el capitán y el ayudante se asignan ahora en
    # Transporte, y quien lee la hoja en el muelle necesita saber quién maneja el bote.
    corridas = _tras.corridas(conn, fecha, fecha)
    for c in corridas:
        for h in c.get("huespedes", []):
            fila = por_hab.get(str(h.get("room_no")))
            if not fila:
                continue
            if not fila["bote_t"]:
                fila["bote_t"] = " / ".join(
                    x for x in (c.get("bote_nombre"), c.get("capitan_nombre")) if x)
            if not fila["guia_t"]:
                fila["guia_t"] = c.get("guia_nombre") or ""

    # --- El BT de la habitación que lo pidió ---
    #
    # Lo pidió el lodge: «cuando una reserva necesite BT indicar en el resumen que hay BT
    # para esa reserva y la hora». El BT es un bote EXTRA, apartado para una habitación
    # concreta, y hasta ahora solo salía en la pantalla de Transporte: quien lee la hoja
    # del día no tenía forma de saber que ese cuarto tiene un viaje reservado.
    #
    # Va en NOTAS y no en una columna nueva porque es la excepción, no la norma: con una
    # columna, 24 habitaciones llevarían una casilla vacía para que una la tenga llena.
    for b in resumen.get("bts", []):
        fila = por_conf.get(str(b.get("conf_no")))
        if not fila:
            continue
        texto = "BT" + (f" {b['hora']}" if b.get("hora") else " (sin hora)")
        quien = " / ".join(x for x in (b.get("bote"), b.get("capitan")) if x)
        if quien:
            texto += f" · {quien}"
        fila["notas"] = f"{fila['notas']} · {texto}".strip(" ·") if fila["notas"] else texto

    # --- Los tours de cada habitación ---
    #
    # SE EMPAREJA POR RESERVA, NO POR HABITACIÓN. Es la misma lección que ya está escrita
    # en el resumen para las alergias: la habitación se reutiliza cada pocos días y el
    # número de reserva es lo único que identifica al huésped. Aquí el fallo tenía una
    # forma concreta: el día que una habitación cambia de huésped —55 veces en los
    # próximos cuatro meses— la fila de quien SE VA es la última que se queda con el
    # cuarto, así que el tour del que LLEGA se habría pintado en el renglón del que se
    # va. Y al revés: el que llega se quedaba sin su tour. Las dos mitades en silencio.
    # TODOS LOS DEL DÍA, NO EL PRIMERO. Lo pidió el lodge: «cuando un cliente tiene 2
    # tours el mismo día, ejemplo EBT y NW, solo se refleja un tour, hay que corregir el
    # resto porque perdemos información ahí». Pasa de verdad y es la combinación normal:
    # el pajareo de las 6 de la mañana y la caminata nocturna de las 17:45 son el mismo
    # día y los dos necesitan guía. Quedarse con el primero no daba error — daba una hoja
    # en la que el segundo guía no existía.
    #
    # Cada tour en su propio renglón DENTRO de la casilla, y el guía y el bote en el
    # suyo, para que las tres columnas se lean en paralelo: la primera línea de GUÍA es
    # la del primer tour. Con los tres pegados en una sola línea no habría forma de saber
    # cuál guía es de cuál salida.
    tours = resumen.get("tours", [])
    for t in tours:
        for conf in str(t.get("reservas") or "").split(","):
            fila = por_conf.get(conf.strip())
            if not fila or not t.get("tour_codigo"):
                continue
            fila["tours"].append({
                # El PRIVADO va pegado al código, no en una columna aparte: es lo que
                # hay que ver de un vistazo al leer la casilla. Un tour privado lleva su
                # propio bote y su propio guía, y quien arma la mañana necesita saberlo
                # sin cruzar la hoja con otra pantalla.
                "codigo": etiqueta_tour(t),
                "guia": t.get("guia_nombre") or "",
                "bote": t.get("bote_nombre") or "",
            })
    for fila in por_conf.values():
        # Ordenados como la jornada, que es como se lee la hoja.
        orden = {etiqueta_tour(t): (t.get("horario_inicio") or "99:99") for t in tours}
        fila["tours"].sort(key=lambda x: orden.get(x["codigo"], "99:99"))
        fila["tour"] = "\n".join(x["codigo"] for x in fila["tours"])

        def columna(campo):
            """Un renglón por tour, alineado con el de la casilla TOUR.

            El guion solo aparece cuando hay algo con qué confundirlo: con dos tours y
            un solo guía asignado, sin el hueco marcado no se sabría de cuál de los dos
            es. Si no hay ninguno asignado la casilla va vacía, que es lo que ya decía
            antes y se lee mejor que una columna de guiones.
            """
            valores = [x[campo] for x in fila["tours"]]
            if not any(valores):
                return ""
            return "\n".join(v or "—" for v in valores)

        fila["tour_guia"] = columna("guia")
        fila["tour_bote"] = columna("bote")

    filas = sorted(por_conf.values(),
                   key=lambda x: int(x["hab"]) if str(x["hab"]).isdigit() else 999)

    # YA NO SE CALCULAN LAS ALERTAS. Iban en una caja del papel —tours sin guía, corridas
    # sin cubrir, tours que caen el día de salida— y el lodge la quitó de la hoja que se
    # reparte: es una lista de pendientes que resuelve quien coordina en la app, no quien
    # lee la hoja en el muelle.
    #
    # NADA DE ESO SE PIERDE DE VISTA: los tours sin guía y sin bote salen en rojo en la
    # misma caja de tours de arriba, y la pantalla de Resumen sigue mostrando los cuatro
    # contadores y la caja de «tours el día que se va» con su explicación. Lo único que
    # cambió es que el papel no los repite.
    return {
        "fecha": fecha,
        "filas": filas,
        # La nota del día entero, la que va al pie. Vacía no dibuja nada: una caja con
        # el título y nada dentro ocuparía hoja para decir que no hay nada que decir.
        "nota_dia": mano["dia"],
        "tours": tours,
        "totales_punto": totales,
        "movimientos": [
            ("ENTRA", resumen.get("total_ingresos", 0), resumen.get("pax_ingresos", 0)),
            ("SALE", resumen.get("total_salidas", 0), resumen.get("pax_salidas", 0)),
            ("EN CASA", resumen.get("total_en_casa", 0), resumen.get("pax_en_casa", 0)),
        ],
        "pax_desayunos": resumen.get("pax_desayunos", 0),
        "pax_en_casa": resumen.get("pax_en_casa", 0),
    }


def _dmy(iso):
    try:
        d = datetime.date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.day}/{d.month}/{d.year}"


# ---------------------------------------------------------------------------
# El PDF, apaisado y de UNA hoja: es lo que se fotografía y se manda al grupo
# ---------------------------------------------------------------------------
#
# LA LETRA NO ES FIJA, LA PÁGINA SÍ. Lo pidió el lodge: «hay días que están quedando en
# 2 páginas y me gustaría ver todo en una página siempre, tal vez que el formato sea
# flexible a eso». Con el tamaño fijo de antes, 27 de los 73 días con operación —el 37%—
# se partían en dos, y la parte de abajo es justo la que se pierde: la hoja se fotografía
# para mandarla al grupo y nadie manda dos fotos.
#
# Así que la hoja se dibuja varias veces, se MIDE cada vez, y se queda con la letra más
# grande que quepa entera. Eso también la hace crecer: un día de seis habitaciones ya no
# sale con letra de hormiga en el tercio de arriba de un folio en blanco, que para un
# pantallazo en un teléfono importa tanto como lo otro.
FUENTE = 6.4
INTERLINEA = 7.6
RELLENO = 1.5            # lo que respira cada renglón por arriba y por abajo
HUECO = 5                # el aire entre las cajas de arriba, la franja y la tabla

# El margen de cada casilla contra su raya. ReportLab trae 6 pt de fábrica, que en una
# columna de 17 mm son la cuarta parte del ancho: «SNORKEL» no cabía y se partía en
# «SNORKE / L». Con 3 pt entra entero, los nombres largos parten en menos renglones y la
# hoja completa encoge lo bastante como para que la letra pueda ser más grande.
MARGEN_CELDA = 3.0

# Hasta dónde se estira y hasta dónde se encoge.
#
# ARRIBA manda el ancho de las columnas, que es fijo: con letra mucho más grande los
# nombres empiezan a partirse en dos renglones y la hoja gana menos alto del que gasta.
# En la práctica el tope de verdad lo pone `_techo_por_las_palabras` y queda más abajo
# —medido, 1.15— porque las cabeceras «SIERPE» y «DRAKE» viven en columnas de 12 mm que
# solo llevan un número. Este 1.25 es el freno de mano, no el que suele frenar.
# ABAJO manda el ojo de quien la lee en el muelle a las seis de la mañana.
MAS_GRANDE = 1.25
MAS_CHICA = 0.72
PASO = 0.01
AIRE_MAXIMO = 4.5        # cuánto se pueden separar los renglones cuando sobra hoja


def _escalas():
    cuantas = int(round((MAS_GRANDE - MAS_CHICA) / PASO)) + 1
    return [round(MAS_CHICA + i * PASO, 2) for i in range(cuantas)]


def _alto_de(piezas, ancho):
    """Lo que mide la hoja armada, en puntos. Es la misma cuenta que hace el marco."""
    return sum(pieza.wrap(ancho, 0x7FFFFFFF)[1] for pieza in piezas)


def _techo_por_las_palabras(d, columnas=None):
    """Hasta dónde puede crecer la letra sin que una palabra se parta por la mitad.

    Al crecer, «SNORKEL» dejaba de caber en su columna y ReportLab lo partía en
    «SNORKE / L» sin avisar. Un código de tour partido no es un código ilegible: es otro
    código, y quien lee la hoja en el muelle no tiene con qué contrastarlo.

    La cuenta sale cerrada y por eso no hay que dibujar nada para saberla. Si `a` es el
    ancho de la columna y `w` lo que mide la palabra con la letra de tamaño natural, al
    crecer por `k` la palabra mide `w·k` y el hueco se queda en `a − 2·MARGEN·k`, así
    que `k ≤ a / (w + 2·MARGEN)`. Manda la palabra más apretada de toda la hoja.

    Se calcula sobre el contenido de VERDAD y no sobre una lista de códigos: el día que
    el lodge añada un tour con un nombre más largo, la hoja crece un poco menos sola, en
    vez de partirlo.
    """
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth

    techo = MAS_GRANDE
    columnas = columnas or COLUMNAS

    def mirar(valor, ancho_mm, negrita=False):
        nonlocal techo
        fuente = "Helvetica-Bold" if negrita else "Helvetica"
        for palabra in str(valor or "").replace("\n", " ").split():
            ancho_palabra = stringWidth(palabra, fuente, FUENTE)
            if ancho_palabra > 0:
                techo = min(techo, (ancho_mm * mm) / (ancho_palabra + 2 * MARGEN_CELDA))

    for clave, titulo, ancho in columnas:
        mirar(titulo, ancho, negrita=True)
        for fila in d["filas"]:
            # La casilla de NOTAS lleva además lo escrito a mano, y en negrita. Mirando
            # solo `fila["notas"]` una palabra larga escrita hoy no contaría para el
            # techo, y la hoja crecería hasta partirla por la mitad.
            if clave == "notas":
                mirar(nota_de_la_fila(fila), ancho, negrita=True)
            else:
                mirar(fila.get(clave), ancho, negrita=clave in ("estado", "hab", "fecha"))

    # Y la caja de tours de arriba, que es donde viven los nombres de guía y de bote.
    for t in d["tours"]:
        for valor, ancho in zip(
                (etiqueta_tour(t), t.get("pax_total"),
                 t.get("guia_nombre") or "SIN ASIGNAR", t.get("bote_nombre") or "—"),
                CAJA_TOURS_MM):
            mirar(valor, ancho)

    # Nunca por debajo del suelo: si una palabra no cabe ni con la letra más chica, lo
    # que hay que arreglar es el ancho de esa columna, no encoger la hoja entera.
    return max(MAS_CHICA, techo)


def _la_letra_que_cabe(d, ancho, alto):
    """(escala, lo que sobra) con la letra más grande que entra en una sola página.

    Se busca por mitades y no probando una por una porque la hoja crece con la letra sin
    volver atrás: si con un tamaño no cabe, con ninguno mayor va a caber. Siete medidas
    bastan para las 54 escalas posibles.

    Si ni con la más chica entra, lo que sobra sale negativo y manda: la decide `pdf()`
    alargando el papel. Encoger la letra sin fondo convierte la hoja en algo que no se
    lee, y partirla en dos es justo lo que se vino a arreglar.
    """
    techo = _techo_por_las_palabras(d)
    pasos = [p for p in _escalas() if p <= techo] or [MAS_CHICA]
    medido = {}

    def cabe(i):
        if i not in medido:
            medido[i] = _alto_de(_historia(d, pasos[i]), ancho)
        return medido[i] <= alto

    if not cabe(0):
        return pasos[0], alto - medido[0]
    bajo, tope = 0, len(pasos) - 1
    while bajo < tope:
        medio = (bajo + tope + 1) // 2
        if cabe(medio):
            bajo = medio
        else:
            tope = medio - 1
    return pasos[bajo], alto - medido[bajo]


def _cabecera_verde(tabla, k, hasta_col=-1):
    """El verde del lodge en la primera fila, y la rejilla a escala `k`.

    Está en UN sitio porque lo usan las dos hojas —la del día y la del periodo— y son el
    mismo documento a ojos de quien lo recibe. Dos copias de este bloque acabarían con
    dos verdes, dos rejillas y dos interlíneas distintas sin que nadie lo decidiera.
    """
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle

    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (hasta_col, 0), colors.HexColor("#" + VERDE_CAB)),
        ("TEXTCOLOR", (0, 0), (hasta_col, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#" + LINEA)),
        ("FONTSIZE", (0, 0), (-1, -1), FUENTE * k),
        ("LEADING", (0, 0), (-1, -1), INTERLINEA * k),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), RELLENO * k),
        ("BOTTOMPADDING", (0, 0), (-1, -1), RELLENO * k),
        ("LEFTPADDING", (0, 0), (-1, -1), MARGEN_CELDA * k),
        ("RIGHTPADDING", (0, 0), (-1, -1), MARGEN_CELDA * k),
    ]))


def _caja_de_notas(renglones, k, columnas=None, titulo="NOTAS DEL DÍA"):
    """La caja de lo escrito a mano, al pie de la hoja. Vacía no devuelve nada.

    `renglones` son párrafos ya armados por quien llama, con SU estilo: la hoja del día
    dibuja con la letra que le quepa y la del rango con la de siempre.

    VA AL PIE Y NO ARRIBA porque arriba está el resumen que se lee de un vistazo —tours,
    movimientos, muelles— y meter ahí un párrafo libre empujaría hacia abajo justo lo que
    el staff busca primero. Al pie, cerrando la hoja, es donde el lodge escribe las suyas
    en el Excel que lleva meses armando a mano.

    Ancha como la tabla, no como la página: una caja más ancha que la tabla que tiene
    encima se lee como si fuera otra cosa, de otro documento.
    """
    from reportlab.lib.units import mm
    from reportlab.platypus import Table

    renglones = [x for x in renglones if x]
    if not renglones:
        return []
    ancho = sum(c[2] for c in (columnas or COLUMNAS))
    tabla = Table([[titulo]] + [[r] for r in renglones],
                  colWidths=[ancho * mm], hAlign="LEFT")
    _cabecera_verde(tabla, k)
    return [tabla]


def _historia(d, k, aire=0.0):
    """Las piezas de la hoja dibujadas a escala `k`, con `aire` extra en cada renglón.

    Vive aparte de `pdf()` porque la hoja se arma varias veces: una por cada tamaño de
    letra que se prueba y otra para el documento de verdad. Si el dibujo estuviera dentro
    de `pdf()` habría que medir una cosa y dibujar otra, que es exactamente como se cuela
    una fila a la segunda página sin que nadie se entere.
    """
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    verde = colors.HexColor("#" + VERDE_CAB)
    verde2 = colors.HexColor("#" + VERDE_SUB)
    linea = colors.HexColor("#" + LINEA)
    rojo = colors.HexColor("#" + ROJO)

    fuente = FUENTE * k
    relleno = RELLENO * k
    hueco = HUECO * k
    margen = MARGEN_CELDA * k
    chico = ParagraphStyle("c", fontName="Helvetica", fontSize=fuente,
                           leading=INTERLINEA * k)
    chico_b = ParagraphStyle("cb", parent=chico, fontName="Helvetica-Bold")

    def texto(valor, estilo=chico):
        """Una casilla de texto. Se escapa: un apellido con & rompía el dibujo entero."""
        return Paragraph(escape(str(valor or "")), estilo)

    e = []

    def cabecera_verde(tabla, hasta_col=-1):
        _cabecera_verde(tabla, k, hasta_col)

    # ---- Las dos cajas de arriba ----
    #
    # LA CAJA DE «ALERTAS / PENDIENTES» YA NO VA. La quitó el lodge de la hoja que se
    # reparte, y tiene sentido: es una lista de lo que falta por hacer —tours sin guía,
    # corridas sin cubrir— y eso lo resuelve quien coordina en la app, no quien lee la
    # hoja en el muelle. En el papel ocupaba un cuarto del ancho de arriba para decirle a
    # todo el mundo algo que le toca a una persona. Lo que decía sigue estando en la
    # pantalla de Resumen y en los avisos de la Agenda y de Transporte.
    #
    # Su ancho se reparte entre las dos que se quedan, que es donde hacía falta: en la de
    # tours, los nombres de guía y de bote vivían apretados en 24 mm.
    def casilla(valor, falta=False):
        """En párrafo, no en texto suelto: una casilla de texto suelto no parte renglón.

        Con la letra creciendo, «Wilberth Villalobos» en una columna de 24 mm se montaba
        encima de la de al lado y las dos quedaban ilegibles. Un párrafo baja de línea.
        """
        t = escape(str(valor or ""))
        if falta:
            t = f'<font color="#{ROJO}">{t}</font>'
        return Paragraph(t, chico)

    t_tours = [["Tour", "Pax", "Guía", "Bote"]]
    for t in d["tours"]:
        t_tours.append([casilla(etiqueta_tour(t)),
                        t.get("pax_total") or "",
                        casilla(t.get("guia_nombre") or "SIN ASIGNAR",
                                falta=not t.get("guia_nombre")),
                        casilla(t.get("bote_nombre") or "—",
                                falta=not t.get("bote_nombre"))])
    if len(t_tours) == 1:
        t_tours.append(["Sin tours este día", "", "", ""])
    tabla_tours = Table(t_tours, colWidths=[x * mm for x in CAJA_TOURS_MM],
                        hAlign="LEFT")
    cabecera_verde(tabla_tours)

    t_mov = [["Estado", "Habs.", "Pax"]]
    for estado, habs, pax in d["movimientos"]:
        t_mov.append([estado, habs, pax])
    t_mov.append(["TOTAL + BKF", "", d["pax_desayunos"]])
    tabla_mov = Table(t_mov, colWidths=[x * mm for x in CAJA_MOV_MM], hAlign="LEFT")
    cabecera_verde(tabla_mov)
    tabla_mov.setStyle(TableStyle([
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))

    titulos = Table(
        [[Paragraph("<b>Resumen de Tours</b>", chico_b),
          Paragraph("<b>Resumen de Movimientos</b>", chico_b)]],
        colWidths=[x * mm for x in RANURAS_ARRIBA_MM], hAlign="LEFT")
    titulos.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), verde),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), relleno),
        ("BOTTOMPADDING", (0, 0), (-1, -1), relleno),
    ]))
    arriba = Table([[tabla_tours, tabla_mov]],
                   colWidths=[x * mm for x in RANURAS_ARRIBA_MM], hAlign="LEFT")
    arriba.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    e += [titulos, arriba, Spacer(1, hueco)]

    # ---- La franja de la fecha y los muelles ----
    s = d["totales_punto"]["Sierpe"]
    dr = d["totales_punto"]["Drake"]
    franja = Table(
        [["Fecha", _dmy(d["fecha"]), "IN HOUSE", d["pax_en_casa"], "",
          "SIERPE", "", "DRAKE", ""],
         ["", "", "", "", "", "entra", "sale", "entra", "sale"],
         ["", "", "", "", "", s["ENTRA"] or "", s["SALE"] or "",
          dr["ENTRA"] or "", dr["SALE"] or ""]],
        colWidths=[16 * mm, 24 * mm, 24 * mm, 14 * mm, 8 * mm,
                   16 * mm, 16 * mm, 16 * mm, 16 * mm], hAlign="LEFT")
    franja.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), fuente),
        ("LEADING", (0, 0), (-1, -1), INTERLINEA * k),
        ("GRID", (0, 0), (3, 0), 0.4, linea),
        ("GRID", (5, 0), (-1, -1), 0.4, linea),
        ("SPAN", (5, 0), (6, 0)), ("SPAN", (7, 0), (8, 0)),
        ("SPAN", (0, 0), (0, 2)), ("SPAN", (1, 0), (1, 2)),
        ("SPAN", (2, 0), (2, 2)), ("SPAN", (3, 0), (3, 2)),
        ("BACKGROUND", (2, 0), (2, 0), verde),
        ("TEXTCOLOR", (2, 0), (2, 0), colors.white),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#D9EAD3")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#D9EAD3")),
        ("BACKGROUND", (5, 0), (-1, 1), verde),
        ("TEXTCOLOR", (5, 0), (-1, 1), colors.white),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), relleno),
        ("BOTTOMPADDING", (0, 0), (-1, -1), relleno),
        ("LEFTPADDING", (0, 0), (-1, -1), margen),
        ("RIGHTPADDING", (0, 0), (-1, -1), margen),
    ]))
    e += [franja, Spacer(1, hueco)]

    # ---- La tabla ancha ----
    anchos = [c[2] * mm for c in COLUMNAS]
    grupo_fila, i = [], 0
    for titulo, cuantas in GRUPOS:
        grupo_fila.append(titulo)
        grupo_fila += [""] * (cuantas - 1)
        i += cuantas
    datos = [grupo_fila, [c[1] for c in COLUMNAS]]

    def renglones(valor):
        """Un párrafo con un renglón por tour. Sin esto el segundo tour se saldría de la
        casilla: una celda de texto suelto no parte la línea, y el PDF se genera igual."""
        return Paragraph(
            "<br/>".join(escape(x) for x in str(valor or "").split("\n")), chico)

    for f in d["filas"]:
        datos.append([
            f["estado"], f["hab"],
            texto(f["huesped"]),
            f["pax"], f["sierpe"], f["drake"], f["horario"],
            texto(f["guia_t"]), texto(f["bote_t"]),
            Paragraph(_notas_con_marcado(f, escape), chico),
            renglones(f["tour"]), renglones(f["tour_guia"]), renglones(f["tour_bote"]),
        ])
    if not d["filas"]:
        datos.append(["Sin movimiento este día"] + [""] * (len(COLUMNAS) - 1))

    tabla = Table(datos, colWidths=anchos, repeatRows=2, hAlign="LEFT")
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 1), verde),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), verde2),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), fuente),
        # SIN ESTO LA LETRA ENCOGE PERO EL RENGLÓN NO. `FONTSIZE` en una tabla de
        # ReportLab no toca la interlínea, que se queda en los 12 pt de fábrica: cada
        # fila medía 5 mm aunque su texto ocupara la mitad, y la hoja se iba a la segunda
        # página por un hueco que nadie había pedido. Es el mismo motivo por el que la
        # caja de alertas, con seis renglones de nada, se comía 30 mm de hoja.
        ("LEADING", (0, 0), (-1, -1), INTERLINEA * k),
        ("GRID", (0, 0), (-1, -1), 0.4, linea),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
        ("ALIGN", (1, 2), (1, -1), "CENTER"),
        ("ALIGN", (3, 2), (6, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # El aire sobrante se reparte AQUÍ y no en la letra: cuando el día es flojo y
        # queda media hoja en blanco, separar los renglones llena la página sin tocar un
        # tamaño de letra que ya es el mayor que cabe.
        ("TOPPADDING", (0, 0), (-1, -1), relleno + aire),
        ("BOTTOMPADDING", (0, 0), (-1, -1), relleno + aire),
        ("LEFTPADDING", (0, 0), (-1, -1), margen),
        ("RIGHTPADDING", (0, 0), (-1, -1), margen),
        ("FONTNAME", (0, 2), (1, -1), "Helvetica-Bold"),
    ]
    col = 0
    for titulo, cuantas in GRUPOS:
        estilo.append(("SPAN", (col, 0), (col + cuantas - 1, 0)))
        col += cuantas
    for n, f in enumerate(d["filas"], start=2):
        fondo = FONDO.get(f["estado"])
        if fondo:
            estilo.append(("BACKGROUND", (0, n), (-1, n), colors.HexColor("#" + fondo)))
    tabla.setStyle(TableStyle(estilo))
    e.append(tabla)

    # ---- La nota del día, escrita a mano sobre esta hoja ----
    #
    # Entra en la MEDIDA como todo lo demás —se arma aquí dentro, no se pega después— así
    # que la letra ya encoge contando con ella. Pegándola fuera, un día con nota larga se
    # habría ido a la segunda página con la hoja ya decidida: exactamente el fallo que
    # costó rehacer este dibujo.
    if d.get("nota_dia"):
        e += [Spacer(1, hueco)] + _caja_de_notas(
            [Paragraph(escape(d["nota_dia"]), chico)], k)
    return e


def _marco_de_la_hoja():
    """(ancho de papel, alto de papel, margen vertical, margen horizontal, ancho útil).

    SE MIDE CONTRA EL MARCO, NO CONTRA EL PAPEL. El marco de `SimpleDocTemplate` se queda
    6 pt de relleno por cada lado, y midiendo contra el alto de la página esos 12 pt son
    justo la última fila cayéndose a la hoja 2 sin que nada avise.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm

    ancho_hoja, alto_hoja = landscape(A4)
    margen_v, margen_h = 8 * mm, 7 * mm
    return ancho_hoja, alto_hoja, margen_v, margen_h, ancho_hoja - 2 * margen_h - 12


def _escala_y_papel(d, ancho, alto):
    """(escala, alto de papel que hace falta) para que la hoja quepa en UNA página.

    Si ni con la letra más chica entra, antes que partirla en dos se alarga el papel:
    sigue siendo UNA página, que es lo que se fotografía y lo que se imprime (la
    impresora la ajusta sola al folio).
    """
    k, sobra = _la_letra_que_cabe(d, ancho, alto)
    return k, (alto if sobra >= 0 else alto - sobra + 1)


def _aire_para(d, k, ancho, alto):
    """El aire que se reparte entre los renglones para llenar la hoja. SE MIDE.

    Antes se repartía con una cuenta que daba por supuesto cuántos renglones lleva la
    tabla, y bastaba una fila de más para que el aire se pasara y la hoja se fuera a la
    segunda página teniendo sitio de sobra. La hoja crece de forma LINEAL con el aire, de
    modo que armándola con 0 y con 1 se sabe exactamente cuánto crece por cada punto,
    tenga las filas que tenga. Dos medidas y ya no hay nada que suponer.
    """
    h0 = _alto_de(_historia(d, k, 0.0), ancho)
    por_punto = max(1e-6, _alto_de(_historia(d, k, 1.0), ancho) - h0)
    return max(0.0, min(AIRE_MAXIMO, (alto - h0) / por_punto))


def pdf(d):
    """La hoja de UN día: apaisada, una sola página, con la letra que quepa."""
    from reportlab.platypus import SimpleDocTemplate

    ancho_hoja, alto_hoja, margen_v, margen_h, ancho = _marco_de_la_hoja()
    alto = alto_hoja - 2 * margen_v - 12
    k, alto_util = _escala_y_papel(d, ancho, alto)
    alto_hoja += alto_util - alto

    buf = io.BytesIO()
    SimpleDocTemplate(
        buf, pagesize=(ancho_hoja, alto_hoja),
        topMargin=margen_v, bottomMargin=margen_v,
        leftMargin=margen_h, rightMargin=margen_h,
        title=f"Operación {_dmy(d.get('fecha'))}").build(
            _historia(d, k, _aire_para(d, k, ancho, alto_util)))
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# La hoja del RANGO: el mismo formato, el movimiento de varios días seguido
# ---------------------------------------------------------------------------
#
# Lo pidió el lodge en dos pasos. Primero: «que aplique este mismo formato al rango de
# fechas». Y cuando le dije que un rango no cabe en una página: «no importa que no quede
# en una sola página si es por rango de fechas, para que se vea a manera de resumen
# siguiendo el formato».
#
# Así que es la hoja de siempre —mismo verde, mismas columnas, misma letra— con una
# columna de FECHA delante y tantas páginas como haga falta. La cabecera de la tabla se
# repite en cada página, que es lo que hace legible una tabla larga en papel.
#
# SOLO ENTRADAS Y SALIDAS, y lo eligió el lodge entre tres formas. Es lo que convierte
# esto en un RESUMEN: quien solo está alojado no aporta nada nuevo cada día, y metiendo
# sus renglones un mes pasaba de 265 a 608 — de nueve páginas a veinte, para repetir
# veinte veces la misma habitación. Los días que esa gente tiene tour siguen apareciendo
# en su hoja del día, que es donde se opera.
COLUMNAS_RANGO = [
    ("fecha", "FECHA", 24),
    ("estado", "ESTADO", 15),
    ("hab", "HAB.", 11),
    ("huesped", "HUÉSPED", 46),
    ("pax", "PAX", 8),
    ("sierpe", "SIERPE", 12),
    ("drake", "DRAKE", 12),
    ("horario", "HORARIO", 17),
    ("guia_t", "GUÍA T", 17),
    ("bote_t", "BOTE / CAPITÁN", 22),
    ("notas", "NOTAS", 40),
    ("tour", "TOUR", 20),
    ("tour_guia", "GUÍA", 16),
    ("tour_bote", "BOTE", 16),
]
GRUPOS_RANGO = [("CUÁNDO", 2), ("HUÉSPEDES", 3), ("INGRESOS Y SALIDAS", 6),
                ("ACTIVIDADES", 3)]


def definicion_rango(dias):
    """Los datos de la hoja del rango, a partir de las definiciones de cada día.

    No vuelve a consultar nada: cada día ya viene calculado con `definicion()`, que es la
    misma función de la que sale la hoja de un día y la pantalla. Rehacer aquí la cuenta
    sería abrir la puerta a que el papel del rango y el del día discrepen.
    """
    filas, tours, movs, puntos = [], {}, {"ENTRA": [0, 0], "SALE": [0, 0]}, {
        "Sierpe": {"ENTRA": 0, "SALE": 0}, "Drake": {"ENTRA": 0, "SALE": 0}}
    notas_dia = []
    habitaciones_noche = pax_noche = pax_desayunos = 0

    for d in dias:
        for f in d["filas"]:
            if f["estado"] == "EN CASA":
                # LO ESCRITO A MANO NO SE CAE DEL RESUMEN. El rango deja fuera a quien
                # solo está alojado —es lo que lo hace un resumen y lo eligió el lodge—
                # pero si alguien se tomó el trabajo de escribir una nota sobre ese
                # renglón, es justo lo que no está en ningún otro sitio. El renglón
                # aparece; en los totales de movimiento sigue sin contar, porque no se
                # movió.
                if (f.get("nota_mano") or "").strip():
                    filas.append(dict(f, fecha=_dmy(d["fecha"])))
                continue
            filas.append(dict(f, fecha=_dmy(d["fecha"])))
            movs[f["estado"]][0] += 1
            movs[f["estado"]][1] += f.get("pax") or 0
        if d.get("nota_dia"):
            notas_dia.append((_dmy(d["fecha"]), d["nota_dia"]))
        for t in d["tours"]:
            fila = tours.setdefault(etiqueta_tour(t), {
                "tour_codigo": t.get("tour_codigo"),
                "grupo_operativo": t.get("grupo_operativo"),
                "es_privado": t.get("es_privado"),
                "salidas": 0, "pax_total": 0,
                "sin_guia": 0, "sin_bote": 0})
            fila["salidas"] += 1
            fila["pax_total"] += t.get("pax_total") or 0
            fila["sin_guia"] += 0 if t.get("guia_nombre") else 1
            fila["sin_bote"] += 0 if t.get("bote_nombre") else 1
        for nombre, totales in d["totales_punto"].items():
            for tipo in ("ENTRA", "SALE"):
                puntos.setdefault(nombre, {"ENTRA": 0, "SALE": 0})[tipo] += totales[tipo]
        pax_desayunos += d.get("pax_desayunos") or 0
        pax_noche += d.get("pax_en_casa") or 0
        habitaciones_noche += sum(1 for f in d["filas"] if f["estado"] == "EN CASA")

    return {
        "desde": dias[0]["fecha"] if dias else None,
        "hasta": dias[-1]["fecha"] if dias else None,
        "dias": len(dias),
        "filas": filas,
        # Las notas del día de cada día del periodo, con su fecha delante. Sueltas no se
        # entenderían: en una hoja de quince días, «llega el inspector» sin fecha no dice
        # qué día hay que esperarlo.
        "notas_dia": notas_dia,
        "tours": sorted(tours.values(), key=lambda t: (-t["pax_total"],
                                                       t["tour_codigo"] or "")),
        "totales_punto": puntos,
        "movimientos": [("ENTRA", movs["ENTRA"][0], movs["ENTRA"][1]),
                        ("SALE", movs["SALE"][0], movs["SALE"][1])],
        # No es «cuánta gente hay»: es cuántas noches de huésped suma el periodo. El
        # nombre lo dice para que nadie lo lea como lo otro.
        "habitaciones_noche": habitaciones_noche,
        "pax_noche": pax_noche,
        "pax_desayunos": pax_desayunos,
    }


def _historia_rango(d, k=1.0):
    """Las piezas de la hoja del rango. SIN buscar tamaño de letra: va a la de siempre.

    La del día encoge para caber en una página; esta no tiene que caber, así que se queda
    con el tamaño que el staff lleva meses leyendo. Lo que se pidió es el FORMATO, y el
    formato incluye lo grande que se ve.
    """
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    verde = colors.HexColor("#" + VERDE_CAB)
    verde2 = colors.HexColor("#" + VERDE_SUB)
    linea = colors.HexColor("#" + LINEA)
    rojo = colors.HexColor("#" + ROJO)

    fuente, relleno = FUENTE * k, RELLENO * k
    hueco, margen = HUECO * k, MARGEN_CELDA * k
    chico = ParagraphStyle("r", fontName="Helvetica", fontSize=fuente,
                           leading=INTERLINEA * k)
    chico_b = ParagraphStyle("rb", parent=chico, fontName="Helvetica-Bold")

    def texto(valor, estilo=chico):
        return Paragraph(escape(str(valor or "")), estilo)

    def casilla(valor, falta=False):
        t = escape(str(valor if valor not in (None, "") else ""))
        if falta:
            t = f'<font color="#{ROJO}">{t}</font>'
        return Paragraph(t, chico)

    e = []

    # ---- Las dos cajas de arriba, con el periodo entero ----
    t_tours = [["Tour", "Salidas", "Pax", "Sin guía"]]
    for t in d["tours"]:
        t_tours.append([casilla(etiqueta_tour(t)), t["salidas"], t["pax_total"],
                        casilla(t["sin_guia"] or "—", falta=bool(t["sin_guia"]))])
    if len(t_tours) == 1:
        t_tours.append(["Sin tours en el periodo", "", "", ""])
    tabla_tours = Table(t_tours, colWidths=[x * mm for x in (62, 22, 20, 22)],
                        hAlign="LEFT")
    _cabecera_verde(tabla_tours, k)
    tabla_tours.setStyle(TableStyle([("ALIGN", (1, 0), (-1, -1), "CENTER")]))

    t_mov = [["Movimiento", "Habs.", "Pax"]]
    for estado, habs, pax in d["movimientos"]:
        t_mov.append([estado, habs, pax])
    t_mov.append(["HAB-NOCHE / PAX-NOCHE", d["habitaciones_noche"], d["pax_noche"]])
    t_mov.append(["TOTAL + BKF", "", d["pax_desayunos"]])
    tabla_mov = Table(t_mov, colWidths=[x * mm for x in (46, 18, 18)], hAlign="LEFT")
    _cabecera_verde(tabla_mov, k)
    tabla_mov.setStyle(TableStyle([
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))

    ranuras = [x * mm for x in (132, 86)]
    titulos = Table([[Paragraph("<b>Resumen de Tours del periodo</b>", chico_b),
                      Paragraph("<b>Resumen de Movimientos</b>", chico_b)]],
                    colWidths=ranuras, hAlign="LEFT")
    titulos.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), verde),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), relleno),
        ("BOTTOMPADDING", (0, 0), (-1, -1), relleno),
    ]))
    arriba = Table([[tabla_tours, tabla_mov]], colWidths=ranuras, hAlign="LEFT")
    arriba.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    e += [titulos, arriba, Spacer(1, hueco)]

    # ---- La franja del periodo y los muelles ----
    s = d["totales_punto"].get("Sierpe", {"ENTRA": 0, "SALE": 0})
    dr = d["totales_punto"].get("Drake", {"ENTRA": 0, "SALE": 0})
    franja = Table(
        [["Periodo", f"{_dmy(d['desde'])} — {_dmy(d['hasta'])}", "DÍAS", d["dias"], "",
          "SIERPE", "", "DRAKE", ""],
         ["", "", "", "", "", "entra", "sale", "entra", "sale"],
         ["", "", "", "", "", s["ENTRA"] or "", s["SALE"] or "",
          dr["ENTRA"] or "", dr["SALE"] or ""]],
        colWidths=[x * mm for x in (20, 48, 16, 14, 8, 16, 16, 16, 16)], hAlign="LEFT")
    franja.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), fuente),
        ("LEADING", (0, 0), (-1, -1), INTERLINEA * k),
        ("GRID", (0, 0), (3, 0), 0.4, linea),
        ("GRID", (5, 0), (-1, -1), 0.4, linea),
        ("SPAN", (5, 0), (6, 0)), ("SPAN", (7, 0), (8, 0)),
        ("SPAN", (0, 0), (0, 2)), ("SPAN", (1, 0), (1, 2)),
        ("SPAN", (2, 0), (2, 2)), ("SPAN", (3, 0), (3, 2)),
        ("BACKGROUND", (2, 0), (2, 0), verde),
        ("TEXTCOLOR", (2, 0), (2, 0), colors.white),
        ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#D9EAD3")),
        ("BACKGROUND", (5, 0), (-1, 1), verde),
        ("TEXTCOLOR", (5, 0), (-1, 1), colors.white),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), relleno),
        ("BOTTOMPADDING", (0, 0), (-1, -1), relleno),
        ("LEFTPADDING", (0, 0), (-1, -1), margen),
        ("RIGHTPADDING", (0, 0), (-1, -1), margen),
    ]))
    e += [franja, Spacer(1, relleno),
          Paragraph("Solo <b>entradas y salidas</b>. Quien está alojado sin entrar ni "
                    "salir ese día sale en la hoja de su día.", chico),
          Spacer(1, hueco)]

    # ---- La tabla corrida ----
    def renglones(valor):
        return Paragraph(
            "<br/>".join(escape(x) for x in str(valor or "").split("\n")), chico)

    grupo_fila = []
    for titulo, cuantas in GRUPOS_RANGO:
        grupo_fila.append(titulo)
        grupo_fila += [""] * (cuantas - 1)
    datos = [grupo_fila, [c[1] for c in COLUMNAS_RANGO]]
    for f in d["filas"]:
        datos.append([
            f["fecha"], f["estado"], f["hab"], texto(f["huesped"]),
            f["pax"], f["sierpe"], f["drake"], f["horario"],
            texto(f["guia_t"]), texto(f["bote_t"]),
            Paragraph(_notas_con_marcado(f, escape), chico),
            renglones(f["tour"]), renglones(f["tour_guia"]), renglones(f["tour_bote"]),
        ])
    if not d["filas"]:
        datos.append(["Sin entradas ni salidas en el periodo"]
                     + [""] * (len(COLUMNAS_RANGO) - 1))

    # repeatRows=2: la cabecera se repite en CADA página. Sin eso, de la segunda hoja en
    # adelante hay catorce columnas de cifras sin un título que diga cuál es cuál.
    tabla = Table(datos, colWidths=[c[2] * mm for c in COLUMNAS_RANGO],
                  repeatRows=2, hAlign="LEFT")
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 1), verde),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), verde2),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), fuente),
        ("LEADING", (0, 0), (-1, -1), INTERLINEA * k),
        ("GRID", (0, 0), (-1, -1), 0.4, linea),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
        ("ALIGN", (0, 2), (2, -1), "CENTER"),
        ("ALIGN", (4, 2), (7, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), relleno),
        ("BOTTOMPADDING", (0, 0), (-1, -1), relleno),
        ("LEFTPADDING", (0, 0), (-1, -1), margen),
        ("RIGHTPADDING", (0, 0), (-1, -1), margen),
        ("FONTNAME", (0, 2), (2, -1), "Helvetica-Bold"),
    ]
    col = 0
    for titulo, cuantas in GRUPOS_RANGO:
        estilo.append(("SPAN", (col, 0), (col + cuantas - 1, 0)))
        col += cuantas
    for n, f in enumerate(d["filas"], start=2):
        fondo = FONDO.get(f["estado"])
        if fondo:
            estilo.append(("BACKGROUND", (0, n), (-1, n), colors.HexColor("#" + fondo)))
    tabla.setStyle(TableStyle(estilo))
    e.append(tabla)

    # ---- Las notas de cada día, al final del periodo ----
    if d.get("notas_dia"):
        e += [Spacer(1, hueco)] + _caja_de_notas(
            [Paragraph(f"<b>{escape(fecha)}</b> · {escape(nota)}", chico)
             for fecha, nota in d["notas_dia"]],
            k, columnas=COLUMNAS_RANGO, titulo="NOTAS DE CADA DÍA")
    return e


def pdf_rango(d):
    """La hoja del rango, con las páginas que haga falta y el pie numerado."""
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    ancho_hoja, alto_hoja, margen_v, margen_h, _ = _marco_de_la_hoja()
    titulo = f"Operación {_dmy(d.get('desde'))} a {_dmy(d.get('hasta'))}"

    def pie(canvas, doc):
        # EN VARIAS PÁGINAS HACE FALTA. Una hoja suelta de la quinta página no dice de
        # qué periodo es ni si le falta la siguiente.
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColorRGB(0.45, 0.45, 0.45)
        canvas.drawString(margen_h, margen_v / 2, titulo)
        canvas.drawRightString(ancho_hoja - margen_h, margen_v / 2,
                               f"página {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(
        buf, pagesize=(ancho_hoja, alto_hoja),
        topMargin=margen_v, bottomMargin=margen_v + 4 * mm,
        leftMargin=margen_h, rightMargin=margen_h,
        title=titulo).build(_historia_rango(d), onFirstPage=pie, onLaterPages=pie)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# El Excel, con las MISMAS columnas y los mismos colores
# ---------------------------------------------------------------------------

def excel(d):
    """El Excel de UN día."""
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.title = "Operación"
    _pintar_excel(wb.active, d)
    return _guardar(wb)


def excel_rango(d):
    """El Excel del rango: UNA hoja con las mismas columnas que el PDF del rango.

    El PDF y el Excel tienen que decir lo mismo, que es la regla de esta pareja desde el
    principio. Así que aquí tampoco van los días en que alguien solo está alojado.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.properties import PageSetupProperties

    wb = Workbook()
    ws = wb.active
    ws.title = "Periodo"
    borde = Border(*[Side(style="thin", color=LINEA)] * 4)
    blanco_negrita = Font(bold=True, color="FFFFFF")
    relleno_verde = PatternFill("solid", fgColor=VERDE_CAB)
    relleno_verde2 = PatternFill("solid", fgColor=VERDE_SUB)
    centrado = Alignment(horizontal="center", vertical="center")

    def poner(fila, col, valor, **kw):
        c = ws.cell(row=fila, column=col, value=valor)
        c.border = borde
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    poner(1, 1, "Resumen de Tours del periodo", font=blanco_negrita,
          fill=relleno_verde, alignment=centrado)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
    for i, titulo in enumerate(("Tour", "Salidas", "Pax", "Sin guía"), start=1):
        poner(2, i, titulo, font=blanco_negrita, fill=relleno_verde2, alignment=centrado)
    fila = 2
    for t in d["tours"]:
        fila += 1
        poner(fila, 1, etiqueta_tour(t))
        poner(fila, 2, t["salidas"], alignment=centrado)
        poner(fila, 3, t["pax_total"], alignment=centrado)
        poner(fila, 4, t["sin_guia"] or None, alignment=centrado,
              font=Font(bold=True, color=ROJO) if t["sin_guia"] else Font())
    if not d["tours"]:
        poner(fila + 1, 1, "Sin tours en el periodo")

    poner(1, 6, "Resumen de Movimientos", font=blanco_negrita, fill=relleno_verde,
          alignment=centrado)
    ws.merge_cells(start_row=1, start_column=6, end_row=1, end_column=8)
    for i, titulo in enumerate(("Movimiento", "Habs.", "Pax"), start=6):
        poner(2, i, titulo, font=blanco_negrita, fill=relleno_verde2, alignment=centrado)
    renglones = list(d["movimientos"]) + [
        ("HAB-NOCHE / PAX-NOCHE", d["habitaciones_noche"], d["pax_noche"]),
        ("TOTAL + BKF", None, d["pax_desayunos"])]
    for n, (etiqueta, habs, pax) in enumerate(renglones, start=3):
        poner(n, 6, etiqueta, font=Font(bold=True))
        poner(n, 7, habs, alignment=centrado)
        poner(n, 8, pax, alignment=centrado)

    poner(8, 1, "Periodo", font=Font(bold=True))
    poner(8, 2, f"{_dmy(d['desde'])} — {_dmy(d['hasta'])}", alignment=centrado,
          font=Font(bold=True))
    poner(8, 3, "DÍAS", font=blanco_negrita, fill=relleno_verde, alignment=centrado)
    poner(8, 4, d["dias"], alignment=centrado, font=Font(bold=True))
    s = d["totales_punto"].get("Sierpe", {"ENTRA": 0, "SALE": 0})
    dr = d["totales_punto"].get("Drake", {"ENTRA": 0, "SALE": 0})
    for i, (titulo, valor) in enumerate(
            (("SIERPE entra", s["ENTRA"]), ("SIERPE sale", s["SALE"]),
             ("DRAKE entra", dr["ENTRA"]), ("DRAKE sale", dr["SALE"])), start=6):
        poner(8, i, titulo, font=blanco_negrita, fill=relleno_verde2, alignment=centrado)
        poner(9, i, valor, alignment=centrado)

    inicio = 11
    col = 1
    for titulo, cuantas in GRUPOS_RANGO:
        poner(inicio, col, titulo, font=blanco_negrita, fill=relleno_verde,
              alignment=centrado)
        if cuantas > 1:
            ws.merge_cells(start_row=inicio, start_column=col,
                           end_row=inicio, end_column=col + cuantas - 1)
            for x in range(col + 1, col + cuantas):
                ws.cell(row=inicio, column=x).border = borde
        col += cuantas
    for i, (_, titulo, _) in enumerate(COLUMNAS_RANGO, start=1):
        poner(inicio + 1, i, titulo, font=blanco_negrita, fill=relleno_verde2,
              alignment=centrado)
    ws.freeze_panes = ws.cell(row=inicio + 2, column=1)

    for n, f in enumerate(d["filas"], start=inicio + 2):
        relleno = FONDO.get(f["estado"])
        for i, (clave, _, _) in enumerate(COLUMNAS_RANGO, start=1):
            # La misma casilla que el PDF, de la misma función: lo escrito a mano
            # delante. En el Excel no puede ir en negrita dentro de la celda, pero el
            # texto es palabra por palabra el del papel.
            valor = nota_de_la_fila(f) if clave == "notas" else f.get(clave)
            c = poner(n, i, valor if valor != "" else None)
            if relleno:
                c.fill = PatternFill("solid", fgColor=relleno)
            if clave in ("fecha", "estado", "hab"):
                c.font = Font(bold=True)
            if clave in ("fecha", "hab", "pax", "sierpe", "drake", "horario"):
                c.alignment = centrado
            if clave in ("tour", "tour_guia", "tour_bote", "huesped", "notas"):
                c.alignment = Alignment(vertical="top", wrap_text=True)

    if d.get("notas_dia"):
        _caja_notas_excel(ws, inicio + 3 + len(d["filas"]),
                          [f"{fecha} · {nota}" for fecha, nota in d["notas_dia"]],
                          len(COLUMNAS_RANGO), titulo="NOTAS DE CADA DÍA")

    for i, (_, titulo, ancho) in enumerate(COLUMNAS_RANGO, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(ancho * 0.52,
                                                               len(titulo) + 2)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0      # a lo ancho sí, a lo largo las que hagan falta
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_rows = f"{inicio}:{inicio + 1}"
    return _guardar(wb)


def _guardar(wb):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _caja_notas_excel(ws, fila, renglones, cuantas_columnas, titulo="NOTAS DEL DÍA"):
    """El mismo bloque de notas del PDF, en el Excel: título verde y el texto debajo.

    Está en una función porque lo ponen las dos hojas —la del día y la del periodo— por
    el mismo motivo que `_cabecera_verde` en el PDF: dos copias acabarían con dos verdes
    y dos sitios distintos donde buscarlo.
    """
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    renglones = [x for x in renglones if x]
    if not renglones:
        return fila
    borde = Border(*[Side(style="thin", color=LINEA)] * 4)

    def banda(n, valor, **kw):
        c = ws.cell(row=n, column=1, value=valor)
        c.border = borde
        for k, v in kw.items():
            setattr(c, k, v)
        ws.merge_cells(start_row=n, start_column=1, end_row=n,
                       end_column=cuantas_columnas)
        # El borde de una celda fusionada solo lo pinta la primera; sin esto la caja
        # quedaría abierta por la derecha.
        for x in range(2, cuantas_columnas + 1):
            ws.cell(row=n, column=x).border = borde

    banda(fila, titulo, font=Font(bold=True, color="FFFFFF"),
          fill=PatternFill("solid", fgColor=VERDE_CAB))
    for i, texto in enumerate(renglones, start=1):
        banda(fila + i, texto, alignment=Alignment(vertical="top", wrap_text=True))
    return fila + len(renglones)


def _pintar_excel(ws, d):
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.properties import PageSetupProperties

    borde = Border(*[Side(style="thin", color=LINEA)] * 4)
    blanco_negrita = Font(bold=True, color="FFFFFF")
    relleno_verde = PatternFill("solid", fgColor=VERDE_CAB)
    relleno_verde2 = PatternFill("solid", fgColor=VERDE_SUB)
    centrado = Alignment(horizontal="center", vertical="center")

    def poner(fila, col, valor, **kw):
        c = ws.cell(row=fila, column=col, value=valor)
        c.border = borde
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    # ---- Cajas de arriba ----
    poner(1, 1, "Resumen de Tours", font=blanco_negrita, fill=relleno_verde,
          alignment=centrado)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
    for i, titulo in enumerate(("Tour", "Pax", "Guía", "Bote"), start=1):
        poner(2, i, titulo, font=blanco_negrita, fill=relleno_verde2, alignment=centrado)
    fila = 2
    for t in d["tours"]:
        fila += 1
        poner(fila, 1, etiqueta_tour(t))
        poner(fila, 2, t.get("pax_total"), alignment=centrado)
        poner(fila, 3, t.get("guia_nombre") or "SIN ASIGNAR")
        poner(fila, 4, t.get("bote_nombre") or "—")
    if not d["tours"]:
        fila += 1
        poner(fila, 1, "Sin tours este día")

    poner(1, 6, "Resumen de Movimientos", font=blanco_negrita, fill=relleno_verde,
          alignment=centrado)
    ws.merge_cells(start_row=1, start_column=6, end_row=1, end_column=8)
    for i, titulo in enumerate(("Estado", "Habs.", "Pax"), start=6):
        poner(2, i, titulo, font=blanco_negrita, fill=relleno_verde2, alignment=centrado)
    for n, (estado, habs, pax) in enumerate(d["movimientos"], start=3):
        poner(n, 6, estado, font=Font(bold=True))
        poner(n, 7, habs, alignment=centrado)
        poner(n, 8, pax, alignment=centrado)
    poner(6, 6, "TOTAL + BKF", font=Font(bold=True))
    poner(6, 7, "")
    poner(6, 8, d["pax_desayunos"], alignment=centrado)

    # La caja de «Alertas / pendientes» ya no va, ni aquí ni en el PDF: la quitó el lodge
    # de la hoja que se reparte. Lo que decía sigue en la pantalla de Resumen.

    # ---- Franja de fecha y muelles ----
    s, dr = d["totales_punto"]["Sierpe"], d["totales_punto"]["Drake"]
    poner(8, 1, "Fecha", font=Font(bold=True))
    poner(8, 2, _dmy(d["fecha"]), alignment=centrado, font=Font(bold=True))
    poner(8, 3, "IN HOUSE", font=blanco_negrita, fill=relleno_verde)
    poner(8, 4, d["pax_en_casa"], alignment=centrado, font=Font(bold=True))
    for i, (titulo, valor) in enumerate(
            (("SIERPE entra", s["ENTRA"]), ("SIERPE sale", s["SALE"]),
             ("DRAKE entra", dr["ENTRA"]), ("DRAKE sale", dr["SALE"])), start=6):
        poner(8, i, titulo, font=blanco_negrita, fill=relleno_verde2, alignment=centrado)
        poner(9, i, valor, alignment=centrado)

    # ---- La tabla ancha ----
    inicio = 11
    col = 1
    for titulo, cuantas in GRUPOS:
        poner(inicio, col, titulo, font=blanco_negrita, fill=relleno_verde,
              alignment=centrado)
        if cuantas > 1:
            ws.merge_cells(start_row=inicio, start_column=col,
                           end_row=inicio, end_column=col + cuantas - 1)
            for x in range(col + 1, col + cuantas):
                ws.cell(row=inicio, column=x).border = borde
        col += cuantas
    for i, (_, titulo, _) in enumerate(COLUMNAS, start=1):
        poner(inicio + 1, i, titulo, font=blanco_negrita, fill=relleno_verde2,
              alignment=centrado)
    ws.freeze_panes = ws.cell(row=inicio + 2, column=1)

    for n, f in enumerate(d["filas"], start=inicio + 2):
        relleno = FONDO.get(f["estado"])
        for i, (clave, _, _) in enumerate(COLUMNAS, start=1):
            # Lo escrito a mano delante, igual que en el PDF y desde la misma función.
            valor = nota_de_la_fila(f) if clave == "notas" else f.get(clave)
            c = poner(n, i, valor if valor != "" else None)
            if relleno:
                c.fill = PatternFill("solid", fgColor=relleno)
            if clave in ("estado", "hab"):
                c.font = Font(bold=True)
            if clave in ("hab", "pax", "sierpe", "drake", "horario"):
                c.alignment = centrado
            # Las de actividades llevan un tour por renglón. Sin ajuste de texto Excel
            # enseña solo el primero y el resto se queda escondido dentro de la celda.
            if clave in ("tour", "tour_guia", "tour_bote", "huesped", "notas"):
                c.alignment = Alignment(vertical="top", wrap_text=True)

    if d.get("nota_dia"):
        _caja_notas_excel(ws, inicio + 3 + len(d["filas"]), [d["nota_dia"]],
                          len(COLUMNAS))

    for i, (_, titulo, ancho) in enumerate(COLUMNAS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(ancho * 0.52, len(titulo) + 2)

    # UNA PÁGINA TAMBIÉN AL IMPRIMIRLO, igual que el PDF. Quien abre el Excel y le da a
    # imprimir sin mirar la vista previa sacaba tres folios con las columnas repartidas
    # entre ellos; con esto sale la misma hoja apaisada que el PDF.
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    return ws
