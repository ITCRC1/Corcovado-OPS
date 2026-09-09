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


# ---------------------------------------------------------------------------

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
]


if __name__ == "__main__":
    sys.exit(comun.correr("pantallas del menu", PRUEBAS))
