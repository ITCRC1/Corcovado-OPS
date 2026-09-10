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
    c.cierto(detecta(REAL_JUGO_O_GASEOSA, "Bebidas incluidas"),
             "«incluyendo jugo del día o gaseosa»")
    c.cierto(detecta(REAL_JUGO_NATURAL, "Bebidas incluidas"),
             "«JUGO NATURAL DEL DIA»")
    c.cierto(detecta(REAL_BEBIDA_NATURAL, "Bebidas incluidas"),
             "«Bebida natural» — sin la palabra «incluida» en ninguna parte")


def bebidas_NO_incluidas_no_se_marca_como_incluidas(c):
    """La que mas importa. «( bebidas no incluidas)» dice lo CONTRARIO, y marcarla es
    peor que no marcar nada: el salonero regalaria bebidas, o le diria al huesped que
    trae algo que no trae."""
    c.igual(detecta(REAL_NO_INCLUIDAS, "Bebidas incluidas"), False,
            "«bebidas no incluidas» NO se marca como incluidas")
    c.igual(detecta("FULLBOARD sin bebidas", "Bebidas incluidas"), False,
            "«sin bebidas» tampoco")
    c.igual(detecta("Package without beverages", "Bebidas incluidas"), False,
            "«without beverages» tampoco")


def una_negacion_no_tapa_una_mencion_buena_mas_adelante(c):
    """Una reserva puede decir las dos cosas: que el paquete no las trae y que igual se
    le incluye el jugo del dia. Vale la que no esta negada."""
    texto = "FULLBOARD ( bebidas no incluidas) pero se le agrega jugo natural del día"
    c.cierto(detecta(texto, "Bebidas incluidas"),
             "se reconoce la mención buena aunque antes haya una negada")


def otras_formas_que_conviene_reconocer(c):
    c.cierto(detecta("Paquete + refresco", "Bebidas incluidas"), "refresco")
    c.cierto(detecta("Rate includes beverages", "Bebidas incluidas"),
             "includes beverages")
    c.cierto(detecta("Paquete con barra libre", "Bebidas incluidas"), "barra libre")
    c.cierto(detecta("Package with open bar", "Bebidas incluidas"), "open bar")
    c.cierto(detecta("Soft drinks", "Bebidas incluidas"), "soft drinks")


def no_se_marca_cualquier_cosa(c):
    """El agua de la habitacion o un cafe mencionado al pasar no son una tarifa con
    bebidas incluidas. Marcarlo todo convertiria el aviso en ruido, y un aviso que
    aparece siempre deja de leerse."""
    for texto in ("Paquete 3N/4D + Pensión completa",
                  "Llega en taxi a las 12:00 MD",
                  "PAQUETE 3D/2N+ FULLBOARD CPL EN HOSPEDAJE Y BOTE"):
        c.igual(detecta(texto, "Bebidas incluidas"), False,
                f"no se marca: {texto[:42]}…")


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
    a = importer.detectar_amenidades(reserva_con(texto))
    c.cierto("Bebidas incluidas" in a, "se detecta la bebida")
    c.cierto("Restricción alimentaria / alergia" in a, "y la alergia, en la misma")


# ---------------------------------------------------------------------------
# El detalle: de que es la alergia, que bebida trae
# ---------------------------------------------------------------------------

def se_guarda_el_trozo_por_el_que_se_reconocio(c):
    """Antes el detalle quedaba VACIO y a cocina le llegaba «Restricción alimentaria /
    alergia» sin decir de que. El dato venia en el reporte y se perdia en el camino."""
    d = importer.detallar_amenidades(reserva_con(REAL_BEBIDA_NATURAL))
    c.cierto("Bebidas incluidas" in d, "hay detalle para la bebida")
    c.cierto("Bebida natural" in d.get("Bebidas incluidas", ""),
             "y dice cual: menciona «Bebida natural»")

    d2 = importer.detallar_amenidades(reserva_con(REAL_ALERGIAS))
    texto = d2.get("Restricción alimentaria / alergia", "")
    c.cierto("gluten" in texto or "vegetarian" in texto,
             "en la alergia dice de que es, no solo que hay una")


def el_detalle_no_es_la_reserva_entera(c):
    """Entero no cabe en la hoja del dia, y ahi dentro va tambien informacion de otras
    cosas que no tienen que ver."""
    largo = "relleno " * 200 + REAL_JUGO_NATURAL + " relleno" * 200
    d = importer.detallar_amenidades(reserva_con(largo))
    trozo = d.get("Bebidas incluidas", "")
    c.cierto(0 < len(trozo) <= importer.DETALLE_MAXIMO,
             f"el detalle se recorta ({len(trozo)} <= {importer.DETALLE_MAXIMO})")
    c.cierto("JUGO NATURAL" in trozo.upper(),
             "y conserva lo que se reconocio, no un trozo cualquiera")


def sin_texto_no_hay_detalle_inventado(c):
    c.igual(importer.detallar_amenidades(reserva_con("")), {},
            "sin texto no se inventa nada")
    c.igual(importer.detallar_amenidades(reserva_con("   ")), {},
            "ni con espacios")


# ---------------------------------------------------------------------------
# El regimen, que no debe cambiar
# ---------------------------------------------------------------------------

def el_regimen_sigue_saliendo_de_los_mismos_textos(c):
    """Las bebidas van como amenidad y NO como regimen: el regimen es UN valor por
    reserva y una reserva puede incluir jugo Y gaseosa. Meterlas ahi habria obligado a
    elegir uno y perder el otro."""
    c.igual(importer.detectar_regimen(reserva_con(REAL_JUGO_NATURAL)),
            "PENSION_COMPLETA", "«FULL BOARD» sigue siendo pensión completa")
    c.igual(importer.detectar_regimen(reserva_con(REAL_BEBIDA_NATURAL)),
            "PENSION_COMPLETA", "«Pensión completa» también")
    c.igual(importer.detectar_regimen(reserva_con("Paquete 3N/4D+ Breakfast & Dinner")),
            "DESAYUNO_CENA", "«Breakfast & Dinner» es desayuno y cena")
    c.igual(importer.detectar_regimen(reserva_con("Paquete sin comidas")), None,
            "y si no lo dice, no se inventa")


def la_bebida_esta_en_el_catalogo_con_area_cocina(c):
    """El area tiene que ser EXACTAMENTE 'Cocina': la hoja del dia busca ese texto y no
    lo parte por la barra, asi que con 'Cocina/Servicio' esto no aparecería en el bloque
    de cocina —le pasa hoy a la cena privada—."""
    import init_db
    cat = {n: (t, a) for n, t, a in init_db.AMENIDADES}
    c.cierto("Bebidas incluidas" in cat, "está en el catálogo")
    c.igual(cat.get("Bebidas incluidas", (None, None))[1], "Cocina",
            "con el área exactamente 'Cocina'")
    # Y que el catálogo y los patrones no se desincronicen: una amenidad que se detecta
    # pero no está en el catálogo entra con una tarea genérica y sin área de verdad.
    patrones = {n for n, _ in importer.AMENIDADES_PATRONES}
    faltan = patrones - set(cat)
    c.igual(sorted(faltan), [], "toda amenidad que se detecta está en el catálogo")


PRUEBAS = [
    se_reconocen_las_tres_formas_reales,
    bebidas_NO_incluidas_no_se_marca_como_incluidas,
    una_negacion_no_tapa_una_mencion_buena_mas_adelante,
    otras_formas_que_conviene_reconocer,
    no_se_marca_cualquier_cosa,
    las_alergias_siguen_usando_el_no_como_senal,
    una_reserva_puede_traer_las_dos_cosas,
    se_guarda_el_trozo_por_el_que_se_reconocio,
    el_detalle_no_es_la_reserva_entera,
    sin_texto_no_hay_detalle_inventado,
    el_regimen_sigue_saliendo_de_los_mismos_textos,
    la_bebida_esta_en_el_catalogo_con_area_cocina,
]


if __name__ == "__main__":
    sys.exit(comun.correr("amenidades y bebidas", PRUEBAS))
