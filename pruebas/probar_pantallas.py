"""Fija que el menú de la interfaz y los permisos del servidor sigan alineados.

POR QUÉ ESTA SUITE. La interfaz resuelve cada pantalla por POSICIÓN: el índice del botón
del menú es el que elige su permiso (`CLAVE_PANTALLA`), su filtro
(`FILTRO_DE_PANTALLA`), su cargador (`cargadoresPantalla`) y si se refresca sola
(`PANTALLAS_QUE_SE_REFRESCAN`). Son cinco listas que tienen que decir lo mismo en el
mismo orden, más la lista de permisos del servidor (`auth.PANTALLAS`).

Desalinearlas NO da ningún error: abre la pantalla equivocada, o esconde un botón a quien
sí tiene permiso. El propio código lo advierte en un comentario y menciona un verificador
que no estaba en el repositorio; esto es ese verificador, escrito para que corra solo.

Se lee el HTML como texto a propósito. Ejecutarlo haría falta un navegador, y lo que hay
que comprobar es justamente lo que está escrito en el archivo.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "frontend", "index.html")


def _html():
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


def _lista(html, nombre):
    """El contenido de un `const NOMBRE = [...]` como lista de textos entre comillas."""
    m = re.search(nombre + r"\s*=\s*\[(.*?)\]", html, re.S)
    if not m:
        return None
    return re.findall(r'"([^"]*)"', m.group(1))


def _botones(html):
    """Los botones del menú, en orden, con el índice que le pasan a irAPantalla()."""
    nav = re.search(r"<nav[^>]*>(.*?)</nav>", html, re.S)
    if not nav:
        return []
    return [(int(i), t.strip()) for i, t in
            re.findall(r'onclick="irAPantalla\((\d+)\)"[^>]*>\s*<span class="largo">([^<]*)',
                       nav.group(1))]


def _cargadores(html):
    m = re.search(r"function cargadoresPantalla\(\)\s*\{\s*return \[(.*?)\];", html, re.S)
    if not m:
        return []
    return [x.strip() for x in m.group(1).replace("\n", " ").split(",") if x.strip()]


def _funcion(html, nombre):
    """El cuerpo de una función de JavaScript, contando las llaves."""
    i = html.find(f"function {nombre}(")
    if i < 0:
        return None
    nivel, j = 0, i
    while j < len(html):
        if html[j] == "{":
            nivel += 1
        elif html[j] == "}":
            nivel -= 1
            if nivel == 0:
                return html[i:j + 1]
        j += 1
    return None


# ---------------------------------------------------------------------------

def las_etiquetas_del_telefono_cuentan_el_rowspan(c):
    """En el telefono las tablas se vuelven tarjetas y cada dato lleva su etiqueta.

    La etiqueta la pone adaptarTablasMovil() leyendo el encabezado, y durante un tiempo
    la eligio por la POSICION de la celda en su fila. Con eso, cualquier tabla que use
    rowspan queda mal etiquetada sin dar ningun error: en la agenda de tours la celda del
    huesped abarca todos los tours de la reserva, asi que en el segundo tour esa celda no
    existe y las etiquetas se corren una a la izquierda. En el telefono se leia la
    asignacion de guias bajo el titulo «Grupo» y los botes bajo «Guia».

    Es la peor forma de equivocarse: el dato es correcto y el nombre no, asi que nadie
    duda de lo que esta leyendo. Lo reporto el hotel desde la app del telefono.

    Esto es una comprobacion de TEXTO —no hay navegador aqui— y sirve para que nadie
    vuelva a la version por posicion. La comprobacion de verdad, con un navegador y la
    tabla real, esta en pruebas/etiquetas_movil.html: se abre y dice 16/16.
    """
    html = _html()
    fn = _funcion(html, "adaptarTablasMovil")
    c.cierto(fn is not None, "adaptarTablasMovil sigue existiendo")
    if not fn:
        return
    c.cierto("rowspan" in fn,
             "tiene en cuenta el rowspan al decidir la columna de cada celda")
    c.cierto("colspan" in fn, "y el colspan")
    # La forma vieja: la etiqueta salia del indice de la celda dentro de la fila.
    c.igual(re.search(r"forEach\(\s*\(\s*celda\s*,\s*i\s*\)", fn) is not None, False,
            "ya no elige la etiqueta por la posicion de la celda en su fila")

    # Y que la tabla que lo destapo siga usando rowspan: si algun dia deja de usarlo, esta
    # prueba dejaria de proteger nada y conviene enterarse.
    #
    # Se ancla en «Fecha del tour», que solo esta en la agenda: «Huésped / Hab.» tambien
    # es el encabezado de la hoja del dia, y buscando por ahi se media la tabla
    # equivocada — que no usa rowspan y hacia fallar la comprobacion.
    i = html.find("<th>Fecha del tour</th>")
    c.cierto(i > 0, "se encuentra la tabla de la agenda de tours")
    if i > 0:
        c.cierto("rowspan" in html[i:i + 1400],
                 "la agenda de tours sigue uniendo filas con rowspan")


def la_tarjeta_de_cada_tour_abre_su_detalle(c):
    """En la agenda, las tarjetas del resumen por tipo de tour se tocan y despliegan
    QUIEN lo guio y QUE DIAS. Sale de los tours que la pantalla ya tiene cargados: si
    fuera otra consulta, la tarjeta y el detalle podrian decir cosas distintas."""
    html = _html()
    c.cierto('onclick="detalleTipoDeTour(' in html, "la tarjeta se puede tocar")
    c.cierto('id="detalle-tipo-tour"' in html, "y tiene donde desplegarse")
    c.cierto("function detalleTipoDeTour" in html, "existe el manejador")
    c.cierto("function vistaDeTipoDeTour" in html, "y quien dibuja el detalle")

    fn = _funcion(html, "vistaDeTipoDeTour")
    c.cierto(fn is not None, "se encuentra la funcion del detalle")
    if fn:
        c.cierto("_agendaRows" in fn,
                 "usa los tours ya cargados y no pide otra consulta")
        c.cierto("porFecha" in fn, "agrupa por FECHA, que es lo que se pidio")
        c.cierto("guia" in fn, "y muestra el guia")
    c.cierto("window._agendaRows = rows" in html,
             "loadAgenda guarda las filas para el detalle")
    # Al guardar un guia la pantalla se redibuja entera; sin esto el panel se cerraba
    # justo despues de asignar, que es cuando se quiere mirar si quedo bien.
    c.cierto("window._tourAbierto" in html, "el detalle abierto se recuerda")


def los_botones_del_menu_van_numerados_en_orden(c):
    """Un salto o un repetido aquí manda a la pantalla de al lado sin avisar."""
    botones = _botones(_html())
    c.cierto(botones, "tiene que haber botones en el menu")
    c.igual([i for i, _ in botones], list(range(len(botones))),
            "los indices de irAPantalla() tienen que ir 0,1,2… sin saltos ni repetidos")


def las_cinco_listas_de_la_interfaz_miden_lo_mismo(c):
    html = _html()
    botones = _botones(html)
    claves = _lista(html, "const CLAVE_PANTALLA")
    filtros = _lista(html, "const FILTRO_DE_PANTALLA")
    cargadores = _cargadores(html)

    c.igual(len(claves or []), len(botones),
            "CLAVE_PANTALLA tiene que tener una entrada por boton del menu")
    c.igual(len(cargadores), len(botones),
            "cargadoresPantalla() tiene que tener un cargador por boton del menu")
    # FILTRO_DE_PANTALLA lleva null en las pantallas sin fecha, y el null no queda
    # recogido por las comillas: se cuentan las comas.
    m = re.search(r"const FILTRO_DE_PANTALLA\s*=\s*\[(.*?)\]", html, re.S)
    cuantos = len([x for x in m.group(1).split(",") if x.strip()]) if m else 0
    c.igual(cuantos, len(botones),
            "FILTRO_DE_PANTALLA tiene que tener una entrada por boton del menu")


def cada_cargador_existe_de_verdad(c):
    """Un nombre mal escrito aquí deja la pantalla en blanco sin decir por qué."""
    html = _html()
    for nombre in _cargadores(html):
        c.cierto(re.search(r"function\s+" + re.escape(nombre) + r"\s*\(", html),
                 f"el cargador {nombre} tiene que existir")


def cada_pantalla_tiene_su_filtro_por_defecto(c):
    html = _html()
    defectos = re.search(r"const DEFECTOS_FILTRO\s*=\s*\{(.*?)\n\};", html, re.S)
    tiene = set(re.findall(r"^\s*(\w+)\s*:", defectos.group(1), re.M)) if defectos else set()
    m = re.search(r"const FILTRO_DE_PANTALLA\s*=\s*\[(.*?)\]", html, re.S)
    usados = set(re.findall(r'"([^"]*)"', m.group(1))) if m else set()
    faltan = usados - tiene
    c.igual(sorted(faltan), [],
            "toda pantalla nombrada en FILTRO_DE_PANTALLA necesita su DEFECTOS_FILTRO")


def el_menu_y_los_permisos_del_servidor_dicen_lo_mismo(c):
    """Si el servidor no conoce la pantalla, sus rutas responden 403 y el boton no sale.

    Es el fallo que ya pasó al agregar el Spa: se desplegó bien y no le aparecía a nadie.
    """
    import auth
    claves_ui = _lista(_html(), "const CLAVE_PANTALLA") or []
    claves_servidor = [k for k, _ in auth.PANTALLAS]
    c.igual(claves_ui, claves_servidor,
            "CLAVE_PANTALLA y auth.PANTALLAS tienen que ser la MISMA lista en el mismo orden")


def las_que_se_refrescan_solas_existen(c):
    html = _html()
    botones = _botones(html)
    m = re.search(r"const PANTALLAS_QUE_SE_REFRESCAN\s*=\s*\[([^\]]*)\]", html)
    indices = [int(x) for x in re.findall(r"\d+", m.group(1))] if m else []
    fuera = [i for i in indices if i >= len(botones)]
    c.igual(fuera, [],
            "PANTALLAS_QUE_SE_REFRESCAN no puede nombrar un boton que no existe")


def housekeeping_quedo_enganchada_en_las_cinco_listas(c):
    """La pantalla nueva: que no falte en ninguna de las cinco."""
    html = _html()
    claves = _lista(html, "const CLAVE_PANTALLA") or []
    c.cierto("housekeeping" in claves, "housekeeping tiene que estar en CLAVE_PANTALLA")
    c.cierto("loadHousekeeping" in _cargadores(html),
             "y su cargador en cargadoresPantalla()")
    m = re.search(r"const FILTRO_DE_PANTALLA\s*=\s*\[(.*?)\]", html, re.S)
    c.cierto(m and "housekeeping" in m.group(1),
             "y su filtro en FILTRO_DE_PANTALLA")
    c.cierto(re.search(r'irAPantalla\(\d+\)"[^>]*>\s*<span class="largo">Housekeeping', html),
             "y su boton en el menu")

    import auth
    c.cierto("housekeeping" in [k for k, _ in auth.PANTALLAS],
             "y el permiso en el servidor")
    c.cierto("Housekeeping" in auth.PERFILES,
             "con un perfil para crear usuarios de housekeeping rapido")


PRUEBAS = [
    los_botones_del_menu_van_numerados_en_orden,
    las_cinco_listas_de_la_interfaz_miden_lo_mismo,
    cada_cargador_existe_de_verdad,
    cada_pantalla_tiene_su_filtro_por_defecto,
    el_menu_y_los_permisos_del_servidor_dicen_lo_mismo,
    las_que_se_refrescan_solas_existen,
    housekeeping_quedo_enganchada_en_las_cinco_listas,
    las_etiquetas_del_telefono_cuentan_el_rowspan,
    la_tarjeta_de_cada_tour_abre_su_detalle,
]


if __name__ == "__main__":
    sys.exit(comun.correr("pantallas del menu", PRUEBAS))
