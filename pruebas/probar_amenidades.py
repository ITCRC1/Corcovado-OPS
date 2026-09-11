"""Fija lo que se reconoce en el texto de una reserva: amenidades, bebidas y regimen.

POR QUE ESTA SUITE. Todo esto se reconoce leyendo texto libre que escribe gente, y
falla en silencio: una amenidad que no se detecta no genera tarea, nadie pone la cuna y
se descubre cuando el huesped llega. No da ningun error.

LOS TEXTOS DE ABAJO SON REALES. Salieron de leer las reservas de Opera, no de imaginar
como se escribiria. Esa diferencia importa: el patron que se escribio "a ojo" perdia
«Bebida natural» —que no dice «incluida» en ninguna parte— y marcaba como incluidas las
de «bebidas no incluidas», que dice exactamente lo contrario.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                     # noqa: E402
import importer                                  # noqa: E402


def reserva_con(texto):
    """Una reserva con ese texto, en la forma que recibe el importador."""
    return {"conf_no": "1", "texto_completo": texto, "adicionales_raw": "", "notas": ""}


def detecta(texto, amenidad):
    return amenidad in importer.detectar_amenidades(reserva_con(texto))


def hay_bebidas(texto):
    return importer.detectar_bebidas(reserva_con(texto)) is not None


def hay_cortesia(texto):
    return importer.detectar_cortesia(reserva_con(texto)) is not None


# --- Textos REALES de Opera, copiados tal cual ---
REAL_JUGO_O_GASEOSA = (
    "PNC CPL Paquete 2N/3D+Pensión completa, incluyendo jugo del día o gaseosa PNC "
    "Entrada: Via Sierpe ocupan parqueo Salida: Via Sierpe")
REAL_JUGO_NATURAL = (
    "ISLA, PNC PAQUETE 4D/3N+FULL BOARD+JUGO NATURAL DEL DIA - COMPLEMENTARY PNC+SNK "
    "CPL BOAT TRANSFER CPL")
REAL_BEBIDA_NATURAL = (
    "ISLA, PNC Paquete 3N/4D + Pensión completa + Bebida natural + PNC + SNK "
    "30% OFF EN SPA")
REAL_NO_INCLUIDAS = (
    "RESERVA CPL SOLICITDA POR ANA ARTAVIA + FULLBOARD ( bebidas no incluidas)")
REAL_ALERGIAS = (
    "1 person is gluten free 1 person is vegetarian (no meat, no fish, no seafood)")
REAL_VEGETARIANA = (
    "Restricciones: Mariel es vegetariana pero come pescado, queso, leche y huevos.")


# ---------------------------------------------------------------------------
# Bebidas incluidas
# ---------------------------------------------------------------------------

def se_reconocen_las_tres_formas_reales(c):
    """Las tres maneras en que el PMS lo escribe hoy. Si alguna deja de reconocerse, a
    ese huesped se le cobra algo que traia pagado y reclama en el check-out."""
    c.cierto(hay_bebidas(REAL_JUGO_O_GASEOSA), "«incluyendo jugo del día o gaseosa»")
    c.cierto(hay_bebidas(REAL_JUGO_NATURAL), "«JUGO NATURAL DEL DIA»")
    c.cierto(hay_bebidas(REAL_BEBIDA_NATURAL),
             "«Bebida natural» — sin la palabra «incluida» en ninguna parte")


def las_bebidas_NO_son_una_amenidad(c):
    """Una amenidad es algo que hay que PREPARAR —la cuna, la canasta de frutas—. Esto
    no se prepara, se sabe. Estuvo un dia como amenidad y aparecia en la lista de tareas
    pendientes de cocina sin nada que hacer, y eso enseña a ignorar esa lista."""
    c.igual(detecta(REAL_JUGO_NATURAL, "Bebidas incluidas"), False,
            "no sale como amenidad")
    nombres = {n for n, _ in importer.AMENIDADES_PATRONES}
    c.igual("Bebidas incluidas" in nombres, False,
            "y ya no esta en la lista de amenidades")
    import init_db
    c.igual("Bebidas incluidas" in {n for n, _, _ in init_db.AMENIDADES}, False,
            "ni en el catalogo")


def bebidas_NO_incluidas_no_se_marca_como_incluidas(c):
    """La que mas importa. «( bebidas no incluidas)» dice lo CONTRARIO, y marcarla es
    peor que no marcar nada: el salonero regalaria bebidas, o le diria al huesped que
    trae algo que no trae."""
    c.igual(hay_bebidas(REAL_NO_INCLUIDAS), False,
            "«bebidas no incluidas» NO se marca como incluidas")
    c.igual(hay_bebidas("FULLBOARD sin bebidas"), False, "«sin bebidas» tampoco")
    c.igual(hay_bebidas("Package without beverages"), False,
            "«without beverages» tampoco")


def una_negacion_no_tapa_una_mencion_buena_mas_adelante(c):
    """Una reserva puede decir las dos cosas: que el paquete no las trae y que igual se
    le incluye el jugo del dia. Vale la que no esta negada."""
    texto = "FULLBOARD ( bebidas no incluidas) pero se le agrega jugo natural del día"
    c.cierto(hay_bebidas(texto),
             "se reconoce la mención buena aunque antes haya una negada")


def otras_formas_que_conviene_reconocer(c):
    c.cierto(hay_bebidas("Paquete + refresco"), "refresco")
    c.cierto(hay_bebidas("Rate includes beverages"), "includes beverages")
    c.cierto(hay_bebidas("Paquete con barra libre"), "barra libre")
    c.cierto(hay_bebidas("Package with open bar"), "open bar")
    c.cierto(hay_bebidas("Soft drinks"), "soft drinks")


def no_se_marca_cualquier_cosa(c):
    """El agua de la habitacion o un cafe mencionado al pasar no son una tarifa con
    bebidas incluidas. Marcarlo todo convertiria el aviso en ruido, y un aviso que
    aparece siempre deja de leerse."""
    for texto in ("Paquete 3N/4D + Pensión completa",
                  "Llega en taxi a las 12:00 MD",
                  "PAQUETE 3D/2N+ FULLBOARD CPL EN HOSPEDAJE Y BOTE"):
        c.igual(hay_bebidas(texto), False, f"no se marca: {texto[:42]}…")


def se_guarda_el_texto_de_la_reserva_no_un_si_o_no(c):
    """El reconocimiento es generoso, asi que se muestra la FUENTE y decide la persona.
    Un si/no obligaria a confiar en el patron, y el patron se equivoca."""
    d = importer.detectar_bebidas(reserva_con(REAL_BEBIDA_NATURAL))
    c.cierto(d and "Bebida natural" in d, "se guarda el texto que lo dice")
    c.cierto(len(d) <= importer.DETALLE_MAXIMO, "recortado, no la reserva entera")


# ---------------------------------------------------------------------------
# Cortesia (CPL)
# ---------------------------------------------------------------------------

def se_reconoce_la_cortesia(c):
    """El salonero tiene que saber antes de pasar una cuenta que no se cobra."""
    c.cierto(hay_cortesia("PAQUETE 3D/2N+ FULLBOARD CPL EN HOSPEDAJE Y BOTE"),
             "«CPL EN HOSPEDAJE»")
    c.cierto(hay_cortesia(REAL_JUGO_NATURAL), "«COMPLEMENTARY ... CPL BOAT TRANSFER»")
    c.cierto(hay_cortesia("Reserva de cortesía para prensa"), "«cortesía» en palabras")
    c.cierto(hay_cortesia("Complimentary stay"), "«Complimentary» en ingles")


def se_guarda_QUE_es_cortesia_y_no_solo_que_lo_es(c):
    """«CPL en hospedaje» y «CPL boat transfer» no son lo mismo: uno dice que no se
    cobra la habitacion y el otro que no se cobra el bote. Un si/no los confundiria y
    quien pasa la cuenta no tendria como distinguirlos."""
    d = importer.detectar_cortesia(
        reserva_con("PAQUETE 3D/2N+ FULLBOARD CPL EN HOSPEDAJE Y BOTE AUTORIZADO"))
    c.cierto(d and "HOSPEDAJE" in d.upper(), "dice de que es la cortesia")


def no_se_marca_cortesia_donde_no_la_hay(c):
    """'CPL' con limite de palabra: sin eso cazaria cualquier palabra que lo contenga."""
    for texto in ("Paquete 3N/4D + Pensión completa",
                  "CPLUSTER es un nombre inventado",
                  "Llega a las 12:00"):
        c.igual(hay_cortesia(texto), False, f"no se marca: {texto[:38]}…")


# ---------------------------------------------------------------------------
# Que el guardia de la negacion NO rompa las alergias
# ---------------------------------------------------------------------------

def las_alergias_siguen_usando_el_no_como_senal(c):
    """En una alergia el «no» es la señal —«no seafood», «no meat»— y descartar por
    negacion ahi perderia justo lo mas grave. El guardia solo aplica a las bebidas."""
    c.cierto(detecta(REAL_ALERGIAS, "Restricción alimentaria / alergia"),
             "«no meat, no fish, no seafood» se sigue detectando")
    c.cierto(detecta(REAL_VEGETARIANA, "Restricción alimentaria / alergia"),
             "«es vegetariana» también")
    c.cierto(detecta("Dietary restriction: no pork", "Restricción alimentaria / alergia"),
             "«no pork» también")


def una_reserva_puede_traer_las_dos_cosas(c):
    texto = REAL_JUGO_NATURAL + " " + REAL_ALERGIAS
    c.cierto(hay_bebidas(texto), "se detecta la bebida")
    c.cierto(detecta(texto, "Restricción alimentaria / alergia"),
             "y la alergia, en la misma")
    c.cierto(hay_cortesia(texto), "y la cortesía también")


# ---------------------------------------------------------------------------
# El detalle: de que es la alergia, que bebida trae
# ---------------------------------------------------------------------------

def se_guarda_el_trozo_por_el_que_se_reconocio(c):
    """Antes el detalle quedaba VACIO y a cocina le llegaba «Restricción alimentaria /
    alergia» sin decir de que. El dato venia en el reporte y se perdia en el camino."""
    d2 = importer.detallar_amenidades(reserva_con(REAL_ALERGIAS))
    texto = d2.get("Restricción alimentaria / alergia", "")
    c.cierto("gluten" in texto or "vegetarian" in texto,
             "en la alergia dice de que es, no solo que hay una")


def el_detalle_no_es_la_reserva_entera(c):
    """Entero no cabe en la hoja del dia, y ahi dentro va tambien informacion de otras
    cosas que no tienen que ver."""
    largo = "relleno " * 200 + REAL_ALERGIAS + " relleno" * 200
    d = importer.detallar_amenidades(reserva_con(largo))
    trozo = d.get("Restricción alimentaria / alergia", "")
    c.cierto(0 < len(trozo) <= importer.DETALLE_MAXIMO,
             f"el detalle se recorta ({len(trozo)} <= {importer.DETALLE_MAXIMO})")
    c.cierto("gluten" in trozo.lower(),
             "y conserva lo que se reconocio, no un trozo cualquiera")


def el_corte_del_detalle_se_ve(c):
    """Un corte sin marcar miente. El caso real: la reserva dice «FULLBOARD ( bebidas no
    incluidas)» y el trozo terminaba en «( bebidas no», que se lee como frase completa y
    dice lo contrario. La marca «…» le avisa a quien pasa la cuenta que hay mas."""
    largo = "relleno " * 60 + REAL_ALERGIAS + " relleno" * 60
    d = importer.detallar_amenidades(reserva_con(largo))
    trozo = d.get("Restricción alimentaria / alergia", "")
    c.cierto(trozo.startswith("…"), "se marca que hay texto antes")
    c.cierto(trozo.endswith("…"), "y que hay texto despues")
    c.cierto(len(trozo) <= importer.DETALLE_MAXIMO,
             "las marcas caben dentro del maximo, no lo estiran")

    corto = importer.detallar_amenidades(reserva_con(REAL_ALERGIAS))
    entero = corto.get("Restricción alimentaria / alergia", "")
    c.cierto("…" not in entero,
             "y cuando NO se corto nada no se marca nada")


def sin_texto_no_hay_detalle_inventado(c):
    c.igual(importer.detallar_amenidades(reserva_con("")), {},
            "sin texto no se inventa nada")
    c.igual(importer.detallar_amenidades(reserva_con("   ")), {},
            "ni con espacios")


# ---------------------------------------------------------------------------
# El regimen, que no debe cambiar
# ---------------------------------------------------------------------------

def el_regimen_sigue_saliendo_de_los_mismos_textos(c):
    """Las bebidas van JUNTO al regimen pero en su propia columna: el regimen es UN
    valor por reserva y una reserva puede incluir jugo Y gaseosa. Meterlas dentro habria
    obligado a elegir uno y perder el otro."""
    c.igual(importer.detectar_regimen(reserva_con(REAL_JUGO_NATURAL)),
            "PENSION_COMPLETA", "«FULL BOARD» sigue siendo pensión completa")
    c.igual(importer.detectar_regimen(reserva_con(REAL_BEBIDA_NATURAL)),
            "PENSION_COMPLETA", "«Pensión completa» también")
    c.igual(importer.detectar_regimen(reserva_con("Paquete 3N/4D+ Breakfast & Dinner")),
            "DESAYUNO_CENA", "«Breakfast & Dinner» es desayuno y cena")
    c.igual(importer.detectar_regimen(reserva_con("Paquete sin comidas")), None,
            "y si no lo dice, no se inventa")


def el_catalogo_y_los_patrones_no_se_desincronizan(c):
    """Una amenidad que se detecta pero no esta en el catalogo entra con una tarea
    generica y sin area de verdad, asi que no le llega a nadie."""
    import init_db
    cat = {n for n, _, _ in init_db.AMENIDADES}
    patrones = {n for n, _ in importer.AMENIDADES_PATRONES}
    c.igual(sorted(patrones - cat), [],
            "toda amenidad que se detecta esta en el catalogo")


def las_bebidas_y_la_cortesia_LLEGAN_A_LA_BASE(c):
    """De punta a punta, por el camino REAL de carga.

    Esto no es una comprobacion de mas. Hay DOS caminos de escritura en el loader: el
    INSERT completo, y uno que arma las columnas segun lo que la fuente manda —el que
    usa Opera—. Las dos columnas nuevas estaban solo en el primero, asi que la deteccion
    funcionaba, el importador las ponia en el diccionario... y llegaban NULL a la base.
    Sin dar ningun error. Se descubrio mirando la pantalla, no las pruebas.
    """
    from comun import base_limpia, cargar, conexion, reserva
    base_limpia().close()
    cargar([
        reserva("700001", "01", "01-01-26", "05-01-26",
                texto_completo=REAL_BEBIDA_NATURAL),
        reserva("700002", "02", "01-01-26", "05-01-26",
                texto_completo="PAQUETE 3D/2N+ FULLBOARD CPL EN HOSPEDAJE Y BOTE"),
        reserva("700003", "03", "01-01-26", "05-01-26",
                texto_completo="Paquete 3N/4D + Pensión completa"),
    ])
    conn = conexion()
    filas = {r["conf_no"]: dict(r) for r in conn.execute(
        "SELECT conf_no, regimen, bebidas_incluidas, cortesia FROM reserva")}
    conn.close()

    c.cierto(filas["700001"]["bebidas_incluidas"],
             "la bebida llega a la base, no solo al diccionario")
    c.cierto("Bebida natural" in (filas["700001"]["bebidas_incluidas"] or ""),
             "y con el texto que lo dice")
    c.cierto(filas["700002"]["cortesia"], "la cortesia tambien llega")
    c.igual(filas["700003"]["bebidas_incluidas"], None,
            "y la que no trae nada queda vacia, no inventada")
    c.igual(filas["700001"]["regimen"], "PENSION_COMPLETA",
            "el regimen sigue guardandose igual")


def toda_columna_nueva_esta_en_las_dos_rutas(c):
    """El guardia contra el fallo de arriba: una columna que se escriba por el INSERT
    completo y no este repartida por area se queda en NULL cuando carga Opera."""
    import loader
    import re as _re
    import inspect as _ins
    src = _ins.getsource(loader)
    m = _re.search(r"INSERT OR REPLACE INTO reserva \((.*?)\)\s*VALUES", src, _re.S)
    c.cierto(m is not None, "se encuentra el INSERT completo")
    if not m:
        return
    cols = {x.strip() for x in m.group(1).replace("\n", " ").split(",")}
    por_area = set()
    for columnas in loader.COLUMNAS_POR_AREA.values():
        por_area.update(columnas)
    # Estas se escriben aparte y a proposito: no pertenecen a ningun area de la fuente.
    aparte = {"conf_no", "grupo_id", "fuente_pdf", "guia_confirmado"}
    huerfanas = sorted(cols - por_area - aparte)
    c.igual(huerfanas, [],
            "toda columna del INSERT esta repartida en COLUMNAS_POR_AREA")


PRUEBAS = [
    se_reconocen_las_tres_formas_reales,
    las_bebidas_NO_son_una_amenidad,
    bebidas_NO_incluidas_no_se_marca_como_incluidas,
    una_negacion_no_tapa_una_mencion_buena_mas_adelante,
    otras_formas_que_conviene_reconocer,
    no_se_marca_cualquier_cosa,
    se_guarda_el_texto_de_la_reserva_no_un_si_o_no,
    se_reconoce_la_cortesia,
    se_guarda_QUE_es_cortesia_y_no_solo_que_lo_es,
    no_se_marca_cortesia_donde_no_la_hay,
    las_alergias_siguen_usando_el_no_como_senal,
    una_reserva_puede_traer_las_dos_cosas,
    se_guarda_el_trozo_por_el_que_se_reconocio,
    el_detalle_no_es_la_reserva_entera,
    el_corte_del_detalle_se_ve,
    sin_texto_no_hay_detalle_inventado,
    el_regimen_sigue_saliendo_de_los_mismos_textos,
    el_catalogo_y_los_patrones_no_se_desincronizan,
    las_bebidas_y_la_cortesia_LLEGAN_A_LA_BASE,
    toda_columna_nueva_esta_en_las_dos_rutas,
]


if __name__ == "__main__":
    sys.exit(comun.correr("amenidades y bebidas", PRUEBAS))
