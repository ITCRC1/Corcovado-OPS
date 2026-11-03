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


def _sin_comentarios(texto):
    """El mismo trozo de JavaScript sin sus renglones de comentario.

    Estas pruebas leen el HTML como texto, asi que un comentario que NOMBRA una funcion
    pesa igual que una llamada de verdad. Pasó: el comentario que explica por qué tras
    asignar se recarga Transporte dice «antes esto decía loadAgenda()», y la prueba de
    que ya no se llama a la Agenda fallaba por esa frase, con el código correcto.

    Se quitan solo los renglones que EMPIEZAN por //, para no partir un `https://`.
    """
    return "\n".join(r for r in texto.split("\n") if not r.lstrip().startswith("//"))


def _cuerpo_de_funcion(html, nombre):
    """El cuerpo de UNA funcion del index.html, hasta donde empieza la siguiente.

    El corte mira «\\nfunction » ademas de «\\nasync function »: seccionTraslados esta
    definida justo despues de loadAgenda y NO es async, asi que cortando solo por async
    el recorte se la tragaba entera y la comprobacion encontraba su definicion creyendo
    que era una llamada. Fallaba la prueba, no el codigo.

    Es la forma FIABLE de acotar: buscar un trozo de HTML suelto no sirve porque el
    mismo encabezado —«Huésped / Hab.», «No hay tours para esta fecha»— aparece tambien
    en la tarjeta del Dashboard, y el recorte se quedaba en esa.
    """
    i = html.find(f"async function {nombre}(")
    if i < 0:
        i = html.find(f"function {nombre}(")
    if i < 0:
        return ""
    siguientes = [x for x in (html.find("\nfunction ", i + 20),
                              html.find("\nasync function ", i + 20)) if x > i]
    trozo = html[i:min(siguientes)] if siguientes else html[i:i + 9000]
    return _sin_comentarios(trozo)


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


def quien_se_va_hoy_no_esta_en_casa(c):
    """Lo que reporto el hotel: el dashboard contaba como «en casa» a los que se van.

    El huesped que sale durmio anoche, pero se va en el bote de la manana y su
    habitacion queda libre. Contandolo, aparecia a la vez en «salen hoy» y en «en casa»
    —dos veces— y el dashboard decia que habia mas gente en el lodge de la que habia.

    La regla ya existia y estaba escrita en tres sitios (el Resumen de operacion, la
    ocupacion y el reparto del comedor): se cuenta la noche que el huesped DUERME ahi,
    o sea hasta el dia ANTES de su salida. El dashboard era el unico que usaba `>=`.
    """
    with open(os.path.join(RAIZ, "backend", "main.py"), encoding="utf-8") as f:
        servidor = f.read()

    # La consulta del dashboard: se busca por su comentario, que es lo unico estable.
    i = servidor.find("QUIEN SE VA HOY NO ESTÁ EN CASA")
    c.cierto(i > 0, "la consulta del dashboard dice por que excluye a los que salen")
    if i > 0:
        bloque = servidor[i:i + 700]
        c.cierto(re.search(r"sql_fecha\('dep_date'\)\}\s*>\s*\?", bloque),
                 "y compara con «>», no con «>=»")
        c.igual(">= ?" in bloque.split("fetchall")[0], False,
                "no queda ningun «>=» en esa consulta")

    # Y las otras dos de main.py siguen igual, que es con lo que tiene que coincidir.
    # 'desayunos' es la excepcion a proposito: el que se va SI desayuna.
    i = servidor.find("desayunos = lista(")
    c.cierto(i > 0, "se encuentra la consulta de los desayunos")
    if i > 0:
        c.cierto(">= ?" in servidor[i:i + 500],
                 "los desayunos SI incluyen a quien se va: desayuna antes del bote")

    with open(os.path.join(RAIZ, "backend", "informe.py"), encoding="utf-8") as f:
        c.cierto("dia < sale" in f.read(),
                 "el informe cuenta la noche que se duerme, no el dia de salida")


def el_filtro_de_fecha_manda_en_toda_la_pantalla(c):
    """Lo reporto el lodge: «cuando se elige una fecha, que aparezca solo la info de esa
    fecha, que no cargue las anteriores».

    El caso concreto: en Transporte la tabla de arriba iba filtrada por dia, pero la
    lista de «pendientes de confirmar» de abajo se pedia SIN fecha y devolvia las 56 de
    toda la base. Una lista de pendientes que mezcla hoy con diciembre no se puede
    cerrar, y lo que no se puede cerrar se deja de mirar."""
    with open(os.path.join(RAIZ, "backend", "main.py"), encoding="utf-8") as f:
        servidor = f.read()
    i = servidor.find('def transporte_pendientes(')
    c.cierto(i > 0, "existe el endpoint de pendientes")
    firma = servidor[i:i + 200]
    for parametro in ("fecha", "desde", "hasta"):
        c.cierto(parametro in firma, f"los pendientes reciben «{parametro}»")

    cuerpo = servidor[i:i + 2000]
    c.cierto("res_status != 'CANCELADA'" in cuerpo,
             "y tampoco muestran las canceladas")

    with open(os.path.join(RAIZ, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()
    j = pantalla.find("/api/transporte/pendientes")
    c.cierto(j > 0, "la pantalla pide los pendientes")
    c.cierto("fecha=" in pantalla[j - 200:j + 200] or "desde=" in pantalla[j:j + 200],
             "y le pasa el filtro que tiene puesto, no la lista entera")


def las_canceladas_no_salen_en_reservas(c):
    """Lo pidio el lodge dos veces: «en el modulo de reservas siguen apareciendo las
    canceladas y ya se solicito que no aparezcan del todo».

    Una reserva caida no es trabajo de nadie, y mezclada con las vivas obliga a leer el
    estado de cada fila para saber cuales cuentan. No se borran de la base —la fila se
    queda con su estado— pero esta pantalla no las lista."""
    with open(os.path.join(RAIZ, "backend", "main.py"), encoding="utf-8") as f:
        servidor = f.read()
    i = servidor.find("LAS CANCELADAS NO SALEN EN RESERVAS")
    c.cierto(i > 0, "la consulta de reservas dice por que las excluye")
    # La ventana se mide hasta el ORDER BY, no por un numero de caracteres: los
    # comentarios de esa funcion crecieron y empujaron el filtro fuera de los 1200 que
    # habia puesto, asi que la comprobacion fallaba por el tamaño de la ventana y no por
    # el codigo.
    fin = servidor.find("ORDER BY r.arr_date", i)
    bloque = servidor[i:fin if fin > i else i + 2500]
    c.cierto("res_status != 'CANCELADA'" in bloque, "y las filtra de verdad")
    # El filtro de fecha tiene que seguir funcionando: se SUMA con AND al WHERE de las
    # canceladas, no lo reemplaza. Si abriera su propio WHERE, una de las dos reglas se
    # perderia en silencio.
    c.cierto('query += f" AND ' in bloque,
             "el filtro de fecha se suma con AND, no lo reemplaza")
    c.igual(bloque.count("WHERE r.res_status"), 1,
            "hay un solo WHERE en esa consulta")


def reservas_muestra_los_ingresos_de_la_fecha_elegida(c):
    """Lo reporto el lodge dos veces: «cuando se elige una fecha en reservas se cargan
    tambien las fechas anteriores».

    Y era cierto: el 12 de noviembre devolvia TRECE filas, doce de ellas llegadas el 8 y
    el 11 —seguian en casa— y NINGUNA del 12. Se incluian las que 'tocaban' el rango para
    no dejar fuera a quien ya estaba hospedado, pero desde fuera se lee como que la
    pantalla arrastra lo viejo.

    Decision del lodge: la lista son los INGRESOS del periodo. Quien esta alojado se ve
    en el Dashboard y en el Resumen de operacion, que es donde esa pregunta se hace."""
    with open(os.path.join(RAIZ, "backend", "main.py"), encoding="utf-8") as f:
        servidor = f.read()
    i = servidor.find("SOLO LAS QUE LLEGAN EN EL PERIODO")
    c.cierto(i > 0, "la consulta de reservas dice que son los ingresos")
    bloque = servidor[i:i + 1200]
    c.cierto("arr_date')} BETWEEN ? AND ?" in bloque,
             "filtra por la fecha de LLEGADA")
    c.igual("dep_date" in bloque, False,
            "y ya no mete a los que salen dentro del rango")

    with open(os.path.join(RAIZ, "frontend", "index.html"), encoding="utf-8") as f:
        pantalla = f.read()
    # Un dia puede quedar vacio aunque el lodge este lleno: hay que decirlo, o se lee
    # como una pantalla rota.
    c.cierto("Reservas · ingresos" in pantalla,
             "el titulo dice que la lista son los ingresos")
    c.cierto("Nadie ingresa" in pantalla,
             "y el dia vacio se explica en vez de salir en blanco")


def el_bote_se_elige_en_transporte_y_el_guia_en_la_agenda(c):
    """El reparto que pidio el lodge, y la razon por la que importa.

    «Que cuando en la agenda de tours se coloca el guia se jale automatico a la parte de
    transporte, pero que en transporte no sea editable», y al reves con el bote: «se
    asignan en la parte de transportes... y se refleja de manera automatica en la hoja de
    agenda de tours».

    O sea: CADA DATO SE ESCRIBE EN UNA SOLA PANTALLA y se lee en las dos. Si las dos
    pudieran escribirlo, dos personas mirando pantallas distintas podrian poner cosas
    distintas y la ultima en guardar se llevaria la otra por delante.

    Por eso se comprueban las dos mitades. Que el bote no sea editable en la Agenda no
    sirve de nada si tampoco lo es en Transporte: el dato no tendria donde ponerse."""
    html = _html()

    def cuerpo(nombre):
        trozo = _cuerpo_de_funcion(html, nombre)
        c.cierto(bool(trozo), f"existe {nombre}")
        return trozo

    agenda = cuerpo("loadAgenda")
    transporte = cuerpo("loadTransporte")

    # --- La seccion de BOTES de la Agenda: no esta ---
    c.igual("seccionTraslados" in agenda, False,
            "la agenda ya no dibuja las corridas de bote")
    c.cierto("seccionTraslados" in transporte,
             "y Transporte SI las dibuja")
    c.cierto("seccionToursEnBote" in transporte,
             "Transporte tambien dibuja los tours que van en bote")
    c.igual("seccionToursEnBote" in agenda, False,
            "y la agenda no: el bote del tour se pone en Transporte")

    # La Agenda SI pide /api/traslados, pero para ponerles el GUIA, no el bote. Una
    # corrida de muelle no tiene tour detras del cual sacarlo, asi que si no se eligiera
    # aqui no se podria elegir en ningun lado.
    c.cierto("seccionGuiasDeCorridas" in agenda,
             "la agenda pone el guia de las corridas")
    c.cierto("/api/traslados" in agenda, "para lo cual si las pide")

    # --- Volver a la pantalla desde la que se llamo ---
    # Las corridas se tocan desde las dos pantallas, asi que recargar siempre la misma
    # mandaria al usuario a la otra cada vez que asigna a alguien.
    bloque = cuerpo("asignarTraslado")
    c.cierto("loadTransporte()" in bloque and "loadAgenda()" in bloque,
             "tras asignar se recarga la pantalla de la que se vino")
    c.cierto('volver === "agenda"' in bloque, "y se sabe cual es porque se manda")


def el_guia_no_se_edita_en_transporte_ni_el_bote_en_la_agenda(c):
    """La otra mitad: que la pantalla que solo LEE el dato no ofrezca cambiarlo.

    Un desplegable que se puede tocar pero no guarda nada es peor que no tenerlo: quien
    lo usa se queda creyendo que asigno a alguien."""
    html = _html()

    # En TRANSPORTE el guia es texto, no un <select>.
    corridas = _cuerpo_de_funcion(html, "seccionTraslados")
    c.cierto("celdaGuia(c.guia_nombre)" in corridas,
             "la corrida enseña el guia sin dejar cambiarlo")
    c.igual("'guia',this.value" in corridas, False,
            "y no hay forma de mandarlo desde aqui")

    tours = _cuerpo_de_funcion(html, "seccionToursEnBote")
    c.cierto("celdaGuia(t.guia_nombre)" in tours,
             "y el tour en bote tampoco deja cambiar el guia")
    for campo in ("bote", "capitan", "ayudante"):
        c.cierto(f"asignarTourBote('${{k}}','{campo}'" in tours,
                 f"pero si el {campo}")

    # En la AGENDA el bote y la tripulacion son texto.
    agenda = _cuerpo_de_funcion(html, "loadAgenda")
    c.cierto("soloLectura(t.bote_nombre" in agenda,
             "la agenda enseña el bote sin dejar cambiarlo")
    for titulo in ("Capitán", "Ayudante"):
        c.cierto(f"<th>{titulo}</th>" in agenda,
                 f"y tambien el {titulo.lower()}")
    c.igual('id="b-' in agenda, False,
            "ya no queda el desplegable de bote de la agenda")

    # Y lo que la agenda guarda del tour es SOLO el guia: mandar un bote vacio desde una
    # pantalla que ya no lo enseña borraria el que Transporte acaba de poner.
    guardar = _cuerpo_de_funcion(html, "guardarAsignacion")
    c.cierto('params.append("guia"' in guardar, "la agenda guarda el guia")
    c.igual('params.append("bote"' in guardar, False, "y no toca el bote")


def el_tour_privado_se_ve_y_se_cuenta_aparte(c):
    """Lo pidio el lodge: «que los tours que vienen declarados como privados aparezcan asi
    tanto en reserva, itinerario y mas importante en la agenda de tours o transporte... y
    que no se sume de manera automatica con los tours normales sino en una casilla resumen
    aparte».

    Las dos mitades importan por separado:

      · VERSE. Un privado lleva su propio guia y su propio bote. Si en la pantalla se lee
        igual que un compartido, quien asigna no tiene como saberlo.
      · CONTARSE APARTE. Es lo que de verdad rompe: sumados dan una salida donde hay dos,
        con un pax que ningun bote va a llevar junto."""
    html = _html()

    # Una sola forma de dibujar la marca, para que las tres pantallas digan lo mismo.
    c.cierto("function insigniaPrivado(" in html, "hay UNA insignia compartida")
    c.cierto("function claveTipoTour(" in html, "y UNA forma de armar la clave")

    resumen = _cuerpo_de_funcion(html, "resumenPorTour")
    c.cierto("claveTipoTour(t)" in resumen,
             "el resumen agrupa por codigo Y modalidad")
    c.igual("const k = t.tour_codigo" in resumen, False,
            "ya no agrupa solo por codigo, que era lo que los sumaba")

    clave = _cuerpo_de_funcion(html, "claveTipoTour")
    c.cierto("es_privado" in clave and "PRIV" in clave,
             "la clave lleva la modalidad dentro")

    # Transporte: la modalidad viaja en la clave de la corrida, o el bote del privado
    # acabaria puesto tambien en el compartido.
    tours = _cuerpo_de_funcion(html, "seccionToursEnBote")
    c.cierto("t.privado" in tours, "Transporte distingue la salida privada")
    c.cierto("insigniaPrivado()" in tours, "y la marca")
    envio = _cuerpo_de_funcion(html, "asignarTourBote")
    c.cierto("privado: priv" in envio, "y se manda al servidor al asignar")

    # Agenda y detalle de la reserva.
    agenda = _cuerpo_de_funcion(html, "loadAgenda")
    c.cierto("t.es_privado" in agenda and "insigniaPrivado()" in agenda,
             "la agenda marca la fila privada")
    c.cierto(html.count("insigniaPrivado()") >= 4,
             "la marca sale en el resumen, la agenda, transporte y la reserva")


def la_alergia_se_puede_corregir_desde_la_hoja_de_cocina(c):
    """Lo pidio el lodge: «crear opcion para editar las alergias».

    Se edita DONDE SE LEE. Antes habia que irse a Amenidades a buscarla, y una alergia
    mal escrita que hay que ir a buscar a otra pantalla se queda mal escrita."""
    html = _html()
    hoja = _cuerpo_de_funcion(html, "detalleAlergias")
    c.cierto("editarRestriccion(" in hoja, "la hoja ofrece corregir la restriccion")
    c.cierto("marcarRestriccion(" in hoja, "y marcarla avisada, como antes")

    editar = _cuerpo_de_funcion(html, "editarRestriccion")
    c.cierto("/api/amenidades/" in editar and "/texto" in editar,
             "y escribe por la ruta que ya existia")
    # Si el texto queda vacio no se guarda: una restriccion sin texto es una fila que
    # dice que hay una alergia y no dice cual, que es peor que no tenerla.
    c.cierto("no puede quedar vacío" in editar, "no deja guardar un texto vacio")

    # Una nota copiada en dos reservas se corrige en LAS DOS: es el mismo texto, y dejar
    # una vieja volveria a enseñar dos versiones de la misma alergia.
    c.cierto("for (const id of lista)" in editar, "corrige todas las que comparten texto")
    marcar = _cuerpo_de_funcion(html, "marcarRestriccion")
    c.cierto("split(\",\")" in marcar, "y marcarla avisada tambien las marca todas")

    # Y se puede quitar CUALQUIERA, y agregar una nueva. Lo pidio el lodge: «que tambien
    # las alergias se puedan eliminar o agregar de forma manual».
    c.cierto("quitarRestriccion(" in hoja, "se puede quitar")
    c.cierto("agregarRestriccion()" in hoja, "y agregar una que no venia en la reserva")

    # Y EL BOTON TAMBIEN CUANDO NO HAY NINGUNA. Lo pidio el lodge despues de quedarse
    # sin ninguna: «crea una opcion de hacer una alergia ahi mismo en esa pantalla en
    # caso de que no hayan alergias». El dia vacio era un callejon sin salida — el unico
    # sitio para anotar una era la lista, y la lista no existia—, justo cuando mas falta
    # hace: alguien avisa de una alergia y no hay ninguna anotada.
    vacio = hoja[:hoja.find("Agrupadas por habitación") if "Agrupadas por habitación" in hoja
                 else hoja.find("const puedoEditar")]
    c.cierto("agregarRestriccion()" in vacio,
             "el dia sin alergias tambien deja anotar una")

    # Quitar no borra, asi que tiene que haber donde devolverlas.
    c.cierto("panelQuitadas(" in hoja, "las quitadas se pueden ver")
    devolver = _cuerpo_de_funcion(html, "devolverRestriccion")
    c.cierto("/devolver" in devolver, "y devolver a la hoja")

    agregar = _cuerpo_de_funcion(html, "agregarRestriccion")
    c.cierto("/api/amenidades" in agregar, "la nueva se guarda por la ruta que ya existia")
    # La habitacion se ELIGE de entre las que comen, no se escribe a mano: una alergia
    # anotada en el cuarto equivocado es peor que no anotarla, porque cocina se confia.
    c.cierto("d.cena" in agregar and "terra_kitchen" in agregar,
             "y la habitacion sale de quienes comen esa noche")
    c.cierto("no come esta noche" in agregar,
             "si la habitacion no come, se dice en vez de guardar mal")


def las_canceladas_no_salen_en_ningun_modulo(c):
    """Lo pidio el lodge: «eliminar las reservas canceladas del dashboard y de todos los
    modulos para no crear confusion».

    No es solo ruido: hay 98 canceladas cargadas, y cuando una habitacion tiene a la vez
    una cancelada y una viva, la lista del dia enseña dos huespedes donde hay uno.

    Se comprueba que la regla este escrita UNA vez y que las consultas la usen. Una
    condicion copiada a mano en quince consultas se desalinea en la primera que alguien
    agregue, y la que falta no da error: enseña de mas, que es la forma de fallar que
    nadie revisa."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "backend", "main.py"), encoding="utf-8") as f:
        servidor = f.read()

    c.cierto('VIVA = "res_status != \'CANCELADA\'"' in servidor,
             "la regla esta escrita una sola vez")
    c.cierto("def viva(" in servidor, "y hay una forma de usarla con alias")

    # El dashboard: las tres listas del dia tienen que decidir igual. 'en_casa' ya la
    # filtraba y las otras dos no, asi que el mismo dia podia decir que entraban 6 y que
    # habia 4 en casa.
    i = servidor.find("def dashboard(")
    c.cierto(i > 0, "existe el dashboard")
    bloque = servidor[i:i + 2600]
    # Se busca la consulta COMPLETA, con su parametro. Mirar solo «arr_date = ?» no sirve
    # —es un prefijo del texto nuevo, asi que la comprobacion pasaba igual— y una prueba
    # que pasa con el codigo viejo y con el nuevo no comprueba nada.
    for vieja in ('"SELECT * FROM reserva WHERE arr_date = ?", (dd,)',
                  '"SELECT * FROM reserva WHERE dep_date = ?", (dd,)'):
        c.igual(vieja in bloque, False, f"ya no queda la consulta sin filtrar: {vieja[:46]}")
    for que in ("arr_date = ? AND {VIVA}", "dep_date = ? AND {VIVA}"):
        c.cierto(que in bloque, f"se filtra en «{que.split()[0]}»")
    c.cierto("res_status != 'CANCELADA'" in bloque, "y en_casa sigue filtrando")


def el_capitan_y_el_ayudante_se_eligen_en_transporte(c):
    """Los dos selectores nuevos, y que salgan de la misma lista de capitanes."""
    html = _html()
    i = html.find("function seccionTraslados(")
    bloque = _sin_comentarios(html[i:html.find("async function asignarTraslado(", i)])
    for campo in ("capitan", "ayudante"):
        c.cierto(f"'{campo}'" in bloque, f"la corrida tiene selector de {campo}")
    c.cierto("Capitán" in bloque and "Ayudante" in bloque,
             "y las dos columnas tienen su titulo")
    # Se le quita al selector quien ya esta en el OTRO puesto: ofrecer algo que el
    # servidor va a rechazar es peor que no ofrecerlo.
    c.cierto("c.nombre !== ocupado" in bloque,
             "no se ofrece a quien ya esta en el otro puesto de esa corrida")

    # Y el catalogo tiene su seccion de capitanes.
    c.cierto("Catálogo — Capitanes" in html, "el catalogo tiene seccion de capitanes")
    c.cierto("crearCapitan" in html and "estadoCapitan" in html,
             "con crear y activar/desactivar, como el resto del catalogo")


def las_canceladas_no_salen_en_transporte(c):
    """Lo reporto el lodge: «el dia 8 la habitacion 13 aparece como cancelada y en Opera
    hay una reserva nueva en esa misma fecha y habitacion».

    Las dos existian de verdad. La pantalla de Transporte no filtraba canceladas, asi
    que la hab 13 salia DOS veces el dia 8 —la reserva viva y una de mayo, cancelada—.
    Quien arma el bote no tiene forma de saber cual de las dos filas es la buena."""
    with open(os.path.join(RAIZ, "backend", "main.py"), encoding="utf-8") as f:
        servidor = f.read()
    i = servidor.find("LAS CANCELADAS NO VIAJAN")
    c.cierto(i > 0, "la consulta de transporte dice por que excluye a las canceladas")
    bloque = servidor[i:i + 1400]
    c.igual(bloque.count("res_status != 'CANCELADA'"), 2,
            "y lo filtran las DOS consultas, la de entradas y la de salidas")


def en_el_telefono_nada_se_sale_de_la_pantalla(c):
    """Lo que reporto el hotel: al navegar, la pantalla se hacia grande o chica y al
    deslizar a la derecha quedaba una franja en blanco.

    La causa era una sola y esta medida: la barra de filtros es hija de un flex y por
    omision un hijo de flex NO se encoge por debajo de su contenido (min-width: auto).
    Con los filtros en una fila que no envuelve, su contenido mide ~1030 px, asi que la
    barra se plantaba en 1030 sobre una pantalla de 390 y estiraba la hoja entera. Su
    `overflow-x: auto` no llegaba a actuar nunca porque la caja no estaba limitada.

    Medido antes del arreglo: Reservas 1022 px, Amenidades 1168, Spa 1020, con el body
    en 390. Despues: las 15 pantallas caben a 320, 360 y 390.
    """
    html = _html()
    movil = _bloque_movil(html)
    c.cierto(movil is not None, "existe el bloque de estilos del telefono")
    if not movil:
        return

    # El min-width: 0 es lo que hace que la barra se pueda encoger. Sin el, el
    # overflow-x de la linea siguiente es decorativo.
    m = re.search(r"\.filterbar\s*\{([^}]*)\}", movil, re.S)
    c.cierto(m is not None, "la barra de filtros tiene su regla en el telefono")
    if m:
        regla = m.group(1)
        c.cierto(re.search(r"min-width:\s*0", regla),
                 "la barra de filtros puede encogerse (min-width: 0)")
        c.cierto("overflow-x: auto" in regla,
                 "y lo que no quepa se desliza dentro de ella, no en la pagina")

    # Las rejillas de cifras traen su numero de columnas en el `style=` de cada pantalla
    # —4, 5, 6...— y en el telefono no caben ni tres. La del Resumen de operacion usa
    # otra clase y se habia quedado fuera: sus cifras salian de 53 px y la hoja se
    # pasaba 13.
    m = re.search(r"\.stats[^{]*\{[^}]*grid-template-columns:[^;]*!important", movil)
    c.cierto(m is not None,
             "las rejillas de cifras se fuerzan a dos columnas en el telefono")
    if m:
        c.cierto("summary-grid" in m.group(0),
                 "incluida la del Resumen de operacion (.summary-grid)")

    # Y la red general: ninguna caja del contenido se pasa del ancho de la pantalla.
    c.cierto(re.search(r"\.header\s*>\s*\*,\s*\.card\s*>\s*\*\s*\{[^}]*min-width:\s*0",
                       movil),
             "los hijos de las tarjetas tampoco estiran a su madre")
    c.cierto(re.search(r"input,\s*select,\s*textarea,\s*img[^{]*\{[^}]*max-width:\s*100%",
                       movil),
             "y ningun campo ni imagen se pasa del ancho")


def _bloque_movil(html):
    """El contenido del @media del telefono, para mirar solo lo que aplica ahi.

    Hay DOS «@media (max-width: 760px)»: uno de una linea suelta y el bloque grande. Se
    busca el que abre con salto de linea, que es el bloque; quedarse con el primero que
    aparezca hace que las comprobaciones miren un trozo que no tiene nada de esto.
    """
    m = re.search(r"@media \(max-width: 760px\)\s*\{\s*\n", html)
    if not m:
        return None
    i = m.start()
    j = html.find("@media", m.end())
    return html[i:j if j > 0 else i + 12000]


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
    en_el_telefono_nada_se_sale_de_la_pantalla,
    quien_se_va_hoy_no_esta_en_casa,
    el_filtro_de_fecha_manda_en_toda_la_pantalla,
    las_canceladas_no_salen_en_transporte,
    las_canceladas_no_salen_en_reservas,
    el_bote_se_elige_en_transporte_y_el_guia_en_la_agenda,
    el_guia_no_se_edita_en_transporte_ni_el_bote_en_la_agenda,
    el_tour_privado_se_ve_y_se_cuenta_aparte,
    la_alergia_se_puede_corregir_desde_la_hoja_de_cocina,
    las_canceladas_no_salen_en_ningun_modulo,
    el_capitan_y_el_ayudante_se_eligen_en_transporte,
    reservas_muestra_los_ingresos_de_la_fecha_elegida,
]


if __name__ == "__main__":
    sys.exit(comun.correr("pantallas del menu", PRUEBAS))
