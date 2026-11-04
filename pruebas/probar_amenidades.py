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


def decir_que_NO_hay_alergias_no_es_una_alergia(c):
    """El caso que reporto el hotel. Real, de Opera: «Los clientes no tienen alergia o
    restricciones alimenticias» salia en la pestana de Alergias de la cocina.

    La trampa: en la restriccion alimentaria el «no» suele ser parte de la senal —«no
    seafood», «no pork»— asi que no se puede descartar cualquier frase con «no». Lo que
    decide es QUE se esta negando: la palabra alergia, o una comida."""
    import restaurantes as rest
    NO_HAY = [
        "Los clientes no tienen alergia o restricciones alimenticias",
        "No known allergies",
        "sin alergias",
        "Sin restricciones alimenticias",
        "no food allergies reported",
        "no dietary restrictions",
        "Ninguna alergia",
    ]
    for texto in NO_HAY:
        c.igual(importer.RESTRICCION in importer.detectar_amenidades(reserva_con(texto)),
                False, f"«{texto}» NO es una restriccion")
        c.igual(rest.es_restriccion_alimentaria("Preferencia", None, texto), False,
                f"«{texto}» tampoco entra a la pestana escrito a mano")

    # Y lo contrario, que es lo que hace que esto no sea un parche: el «no» sobre una
    # COMIDA sigue siendo una restriccion, y es lo mas grave que se puede perder.
    SI_HAY = [
        "*MRS. LORRAINE LAYER 542588211 no shellfish - mild allergy + strong aversion.",
        "Dietary Restrictions: No Pork",
        "no seafood",
        "GUEST We are both vegetarian (no fish, no seafood, no meat)",
        # Una nota puede decir las dos cosas: no hay alergias, pero si una dieta.
        "No tiene alergias pero es vegetariano",
    ]
    for texto in SI_HAY:
        c.igual(importer.RESTRICCION in importer.detectar_amenidades(reserva_con(texto)),
                True, f"«{texto[:46]}» SI es una restriccion")


def dietary_a_secas_tambien_cuenta(c):
    """Real, de Opera: «Dietary: Kate - No chickpeas / garbanzos + Jonathan - No
    Spinach». El patron exigia «dietary restriction» y esa reserva quedaba SIN
    restriccion: a cocina no le llegaba nada."""
    texto = "Dietary: Kate - No chickpeas / garbanzos + Jonathan - No Spinach"
    c.cierto(importer.RESTRICCION in importer.detectar_amenidades(reserva_con(texto)),
             "«Dietary:» a secas cuenta como restriccion")
    d = importer.detallar_amenidades(reserva_con(texto))
    c.cierto("chickpeas" in d.get(importer.RESTRICCION, ""),
             "y el detalle dice de que es")


def el_detalle_de_la_alergia_solo_habla_de_la_alergia(c):
    """Salia con 60 caracteres a cada lado y arrastraba lo que hubiera al lado: tours,
    tarifas, la agencia, el pasaporte. Reales, de Opera."""
    casos = [
        # (nota real, lo que TIENE que decir, lo que NO debe arrastrar)
        ("PAJAREO ~GUEST Vegetarian Food Request GUEST~ Paquete 2N 3D - Breakfast Only",
         "Vegetarian", ["PAJAREO", "Paquete", "Breakfast"]),
        ("in the boat for the Isla del cano snorkel! Linda She is diabetic. "
         "AGENCIA WAY TO GO TOURS, PENDIENTE DE RECIBIR INFORMACION",
         "diabetic", ["snorkel", "AGENCIA", "PENDIENTE"]),
        ("Blakely is gluten free.\n-------------\nOPERACION: 03: IN 04: ISLA 198685",
         "gluten", ["OPERACION", "ISLA", "198685"]),
        ("PNC JODI MINDELL A04340625 Allergy to raw onions and raw garlic",
         "onions", ["PNC"]),
        ("Out\n-----\nNotas: Alergica a los champiñones y a los pimientos\n"
         "Clientes ocupan 2 camas",
         "champiñones", ["Notas", "camas"]),
    ]
    for nota, debe, no_debe in casos:
        d = importer.detallar_amenidades(reserva_con(nota)).get(importer.RESTRICCION, "")
        c.cierto(debe.lower() in d.lower(), f"el detalle conserva «{debe}»")
        for basura in no_debe:
            c.igual(basura.lower() in d.lower(), False,
                    f"y no arrastra «{basura}» — {d[:60]!r}")


def el_detalle_de_CUALQUIER_amenidad_deja_fuera_los_tours(c):
    """Lo mismo que ya se exigia para la alergia, ahora para todas. Lo reporto el lodge:
    «en la parte de amenidades siguen apareciendo notas de tours que no deberian ir ahi».

    El caso real, de la hab 07 del 4 de noviembre: la nota enumera lo que trae el paquete
    en un renglon seguido —«Del chef experience + C-EBT sujeto a dispo + GTT + Regalo de
    bienvenida»— y el corte por asunto no lo parte, porque es un renglon solo. Asi que el
    detalle del regalo de bienvenida eran cuatro tours."""
    casos = [
        ("Del chef experience + C-EBT sujeto a dispo + GTT + Regalo de bienvenida",
         "Tarjeta de bienvenida", "bienvenida",
         ["chef experience", "C-EBT", "GTT", "sujeto a dispo"]),
        ("Tour de aves sujeto a dispo - Experiencia del Jardin a la mesa - "
         "Regalo de bienvenida",
         "Tarjeta de bienvenida", "bienvenida",
         ["aves", "Jardin a la mesa"]),
        ("PNC + CIS + CBE + Botella de vino",
         "Botella de vino cortesía", "vino", ["PNC", "CIS", "CBE"]),
    ]
    for nota, amenidad, debe, no_debe in casos:
        d = importer.detallar_amenidades(reserva_con(nota)).get(amenidad, "")
        c.cierto(debe.lower() in d.lower(),
                 f"el detalle de «{amenidad}» conserva «{debe}» — {d[:50]!r}")
        for basura in no_debe:
            c.igual(basura.lower() in d.lower(), False,
                    f"y no arrastra «{basura}» — {d[:60]!r}")

    # LO QUE NO PUEDE PASAR: que una coma parta una alergia. «Lactose, hazelnut and
    # peanut allergy» es UNA alergia escrita con comas, y cortarla ahi le dejaria a
    # cocina media lista.
    d = importer.detallar_amenidades(
        reserva_con("Lactose, hazelnut and peanut allergy")).get(importer.RESTRICCION, "")
    for parte in ("Lactose", "hazelnut", "peanut"):
        c.cierto(parte.lower() in d.lower(),
                 f"la alergia escrita con comas conserva «{parte}» — {d[:60]!r}")


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


def el_regimen_pegado_al_paquete_con_un_mas(c):
    """La forma del lodge: el regimen va pegado al paquete con un '+'.

    Lo reporto el hotel con la hab 21 del 3 de noviembre (reserva 598887051): la nota
    decia «Paquete 7N/8D+Breakfast» y el sistema la dejaba SIN regimen, asi que en la
    hoja del restaurante no salia ni para incluirla ni para excluirla. Ese huesped solo
    tiene desayuno pagado y se le iba a servir el almuerzo y la cena."""
    c.igual(importer.detectar_regimen(reserva_con("Paquete 7N/8D+Breakfast")),
            "SOLO_DESAYUNO", "«+Breakfast» es solo desayuno")
    c.igual(importer.detectar_regimen(reserva_con("Paquete 5N/6D+Desayuno")),
            "SOLO_DESAYUNO", "y en español tambien")

    # LO QUE NO PUEDE PASAR: que '+Breakfast' le gane a algo mas especifico. Si ganara,
    # a un huesped de pension completa se le negarian el almuerzo y la cena.
    c.igual(importer.detectar_regimen(reserva_con("4N/5D+Breakfast & Dinner")),
            "DESAYUNO_CENA", "«Breakfast & Dinner» sigue ganando")
    c.igual(importer.detectar_regimen(
        reserva_con("Paquete 4N/5D Pension completa + Breakfast incluido")),
        "PENSION_COMPLETA", "y la pension completa tambien")
    c.igual(importer.detectar_regimen(reserva_con("PAQUTE 4N/5D+FULLBOARD")),
            "PENSION_COMPLETA", "«+FULLBOARD» no se confunde con desayuno")


def un_request_del_huesped_es_una_amenidad(c):
    """Lo pidio el lodge: «todo request del cliente que aparezca en la reserva manejarlo
    como amenidad segun corresponda». Aparecia escrito al final de la nota y no lo
    recogia nadie: «C-EBT : 06/11 EXTRA PILLOWS CONTACTADO POR K.S»."""
    PEDIDO = "Almohadas o toallas extra"
    for texto in ("C-EBT : 06/11 EXTRA PILLOWS CONTACTADO POR K.S",
                  "Extra pillows and towels, please",
                  "Favor dejar almohadas extra en la habitacion",
                  "Please provide additional pillows"):
        encontradas = importer.detectar_amenidades(reserva_con(texto))
        c.cierto(PEDIDO in encontradas, f"se detecta en: {texto[:46]}")

    # Y no se confunde con el sofa cama, que ya existia y usa 'extra bed'.
    cama = importer.detectar_amenidades(reserva_con("Please add an extra bed"))
    c.cierto("Sofá cama extra" in cama, "«extra bed» sigue siendo el sofa cama")
    c.cierto(PEDIDO not in cama, "y no se marca tambien como almohadas")


# El texto REAL de la reserva 591649170 (Healey/Emma, hab 18, llega el 06-11-26), tal
# como lo manda Opera. Se copia entero a proposito: lo que rompia el reconocimiento era
# justo la forma de escribirlo —el precio metido entre las dos palabras— y un ejemplo
# limpio no lo habria encontrado.
NOTA_DEL_QUEQUE = (
    "se agrega adicional Sirena $772.92 facturar a la agencia Para el vuelo de salida "
    "deben estar registrando a las 13:45 PM, favor indicar salida del Lodge. "
    "Favor confirmar el queque ($24.6) el de 2 personas y de vainilla para la noche "
    "Agregar unas fresas ($28.25) con chocolate en la habitacion para el check in "
    "con una tarjeta que diga: Dear Ann Happy Birthday!"
)


def el_queque_y_las_fresas_con_chocolate_se_reconocen(c):
    """Lo encontro el lodge: «en esta reserva solicita un queque y fresas pero no se esta
    leyendo».

    Eran TRES fallos a la vez en la misma nota:

      · El queque no existia: ni patron ni ficha en el catalogo. La nota lo pedia y la
        hoja de cocina no decia nada. Es una tarea con antelacion —hay que hornearlo—
        asi que perderla no se arregla el dia del cumpleaños.
      · Las fresas no se reconocian por DOS motivos juntos: el patron pedia «frutas» y
        la nota dice «fresas», y ademas exigia las dos palabras pegadas mientras el PMS
        mete el precio en medio: «fresas ($28.25) con chocolate».
      · La tarjeta tampoco: el patron pedia la palabra «bienvenida» y esta es «una
        tarjeta que diga: Dear Ann…», que es justo la que da trabajo porque hay que
        copiar el texto.
    """
    encontradas = importer.detectar_amenidades(reserva_con(NOTA_DEL_QUEQUE))
    for esperada in ("Pastel / queque", "Frutas con chocolate cortesía",
                     "Tarjeta de bienvenida", "Decoración por cumpleaños"):
        c.cierto(esperada in encontradas, f"se detecta «{esperada}»")


def las_formas_de_pedir_el_queque_y_las_fresas(c):
    """Las variantes que escribe la agencia, y las que NO se pueden confundir."""
    for texto in ("queque de cumpleanos para 4 personas", "Birthday cake, chocolate",
                  "un pastel de vainilla", "bizcocho para la cena"):
        c.cierto("Pastel / queque" in importer.detectar_amenidades(reserva_con(texto)),
                 f"es un queque: {texto[:40]}")
    for texto in ("fresas con chocolate en la habitacion",
                  "fresas ($28.25) con chocolate",
                  "chocolate covered strawberries",
                  "frutas con chocolate"):
        c.cierto("Frutas con chocolate cortesía" in
                 importer.detectar_amenidades(reserva_con(texto)),
                 f"son fresas con chocolate: {texto[:40]}")

    # LO QUE NO PUEDE DISPARARSE. 'cake' va con \b a los dos lados justamente por esto:
    # una amenidad que salta con el menu del desayuno enseña a ignorar la lista, y
    # entonces el dia que hay un queque de verdad tampoco se mira.
    for texto in ("Breakfast includes pancakes and fresh fruit",
                  "Dessert: cheesecake for the table"):
        c.igual("Pastel / queque" in importer.detectar_amenidades(reserva_con(texto)),
                False, f"NO es un queque: {texto[:40]}")


def el_queque_llega_hasta_la_base(c):
    """De punta a punta por el camino REAL de carga: detectarlo no sirve de nada si no
    llega a la hoja de cocina con su ficha y su area."""
    conn = comun.base_limpia()
    r = dict(comun.reserva(690100, "18", "06-11-26", "11-11-26", adl=2),
             notas=NOTA_DEL_QUEQUE)
    comun.cargar([r], vistas=[r])

    guardadas = {f["amenidad"]: dict(f) for f in conn.execute(
        """SELECT amenidad, tarea, area_responsable, detalle FROM amenidad_tarea
           WHERE conf_no = '690100'""")}
    c.cierto("Pastel / queque" in guardadas, "el queque llega a la base")
    if "Pastel / queque" in guardadas:
        q = guardadas["Pastel / queque"]
        c.igual(q["area_responsable"], "Cocina", "y le toca a cocina")
        c.cierto("sabor" in (q["tarea"] or "").lower(),
                 "con la tarea que dice que hay que confirmar sabor y personas")
        c.cierto("queque" in (q["detalle"] or "").lower(),
                 "y el trozo de la nota por el que se reconocio")
    c.cierto("Frutas con chocolate cortesía" in guardadas, "y las fresas tambien")
    conn.close()


# Textos REALES de alertas de Opera del lodge, copiados enteros. Lo que decide si esto
# sirve es como las escriben ellos, no un ejemplo limpio.
AL_TRASPLANTE = ("Andrea es una paciente con trasplante de corazón y tiene el sistema "
                 "inmunitario comprometido, por lo que necesita seguir precauciones "
                 "específicas de higiene y seguridad alimentaria para reducir el riesgo "
                 "de enfermedades transmitidas por los alimentos.")
AL_MEDICAMENTO = ("ATENCION FRONT DESK Andrea toma un medicamento inmunosupresor "
                  "llamado tacrolimus, por lo que debe evitar los siguientes alimentos")
AL_GERENTE = ("ATENCION GUEST SERVICE & OPERATIONS: Andrea solicita amablemente poder "
              "reunirse con el gerente del alojamiento al momento de su llegada")
AL_COBRO = "ATENCION FRONT DESK COBRAR $678 POR EL TOUR DE MANGLAR"


def las_alertas_de_opera_se_reparten_por_lo_que_son(c):
    """Lo pidio el lodge: revisar las alertas de cada reserva y traer lo que importe.

    Medido contra Opera: 44 de 347 reservas traen alerta, y 49 de las 53 NO estaban en
    ninguna otra parte del sistema. Ahi es donde se escribe la condicion medica de un
    huesped, un cobro pendiente o un encargo de recepcion.

    NO todas son lo mismo, y meterlas todas en el mismo sitio las inutiliza: «avisar a
    reservaciones si hay mas interesados» no es una tarea que alguien pueda cerrar."""
    import alertas_opera as al

    # Las que hablan de comida van a cocina.
    c.cierto(al.es_de_cocina("ADDITIONAL_INFO", AL_TRASPLANTE),
             "la seguridad alimentaria de una paciente inmunodeprimida es de cocina")
    c.cierto(al.es_de_cocina("FRONT_DESK", AL_MEDICAMENTO),
             "y los alimentos que debe evitar por su medicamento, tambien")
    # Opera ya las trae clasificadas: ahi la alergia viene MARCADA, no deducida.
    for codigo in ("ALG_SFD", "ALG_NUT", "DIET_VEGN"):
        c.cierto(al.es_de_cocina(codigo, "sin texto util"),
                 f"el codigo {codigo} basta: lo clasifico Opera")

    # Y las que NO hablan de comida, no.
    c.igual(al.es_de_cocina("GUEST_SERVICE", AL_GERENTE), False,
            "reunirse con el gerente NO es de cocina")
    c.igual(al.es_de_cocina("FRONT_DESK", AL_COBRO), False,
            "y un cobro pendiente tampoco")


def la_alerta_de_cocina_llega_a_la_hoja_aunque_no_case_con_ningun_patron(c):
    """El caso que obligo a esto. Los patrones estan escritos para como se anota una
    alergia en una NOTA —«alergia a X», «dietary», «no pork»— y en una ALERTA el lodge
    explica el caso entero, que no se parece en nada. El texto de la paciente
    trasplantada no disparaba NADA, y es justo lo que cocina no puede no tener."""
    # Sin alerta, ese texto no se reconoce: por eso hace falta la via del codigo.
    suelto = importer.detectar_amenidades(reserva_con(AL_TRASPLANTE))
    c.igual("Restricción alimentaria / alergia" in suelto, False,
            "el texto por si solo no casa con ningun patron")

    # Con la alerta marcada, si entra.
    r = dict(comun.reserva(730100, "08", "04-11-26", "07-11-26", adl=2),
             notas="", alertas_opera=[
                 {"codigo": "ADDITIONAL_INFO", "texto": AL_TRASPLANTE,
                  "para_cocina": True}])
    lote = [r]
    importer.build_review_batch_desde_reservas(lote)
    c.cierto("Restricción alimentaria / alergia" in (r.get("amenidades_detectadas") or []),
             "la alerta de cocina entra como restriccion")
    detalle = (r.get("detalles_de_amenidad") or {}).get("Restricción alimentaria / alergia")
    c.cierto("trasplante" in (detalle or "").lower(),
             "con el texto de la alerta, que es lo que cocina tiene que leer")


def lo_que_ya_se_sabia_de_la_nota_no_se_pisa(c):
    """La alerta SUMA, no reemplaza. La nota puede decir algo que la alerta no repite, y
    antes de servir un plato hacen falta las dos cosas."""
    r = dict(comun.reserva(730110, "08", "04-11-26", "07-11-26", adl=2),
             notas="Allergy to shellfish",
             alertas_opera=[{"codigo": "ADDITIONAL_INFO", "texto": AL_TRASPLANTE,
                             "para_cocina": True}])
    importer.build_review_batch_desde_reservas([r])
    detalle = (r.get("detalles_de_amenidad") or {}).get(
        "Restricción alimentaria / alergia") or ""
    c.cierto("shellfish" in detalle.lower(), "sigue lo que decia la nota")
    c.cierto("trasplante" in detalle.lower(), "y se le suma lo de la alerta")


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
    decir_que_NO_hay_alergias_no_es_una_alergia,
    dietary_a_secas_tambien_cuenta,
    el_detalle_de_la_alergia_solo_habla_de_la_alergia,
    el_detalle_de_CUALQUIER_amenidad_deja_fuera_los_tours,
    el_corte_del_detalle_se_ve,
    sin_texto_no_hay_detalle_inventado,
    el_regimen_sigue_saliendo_de_los_mismos_textos,
    el_regimen_pegado_al_paquete_con_un_mas,
    un_request_del_huesped_es_una_amenidad,
    el_queque_y_las_fresas_con_chocolate_se_reconocen,
    las_formas_de_pedir_el_queque_y_las_fresas,
    el_queque_llega_hasta_la_base,
    las_alertas_de_opera_se_reparten_por_lo_que_son,
    la_alerta_de_cocina_llega_a_la_hoja_aunque_no_case_con_ningun_patron,
    lo_que_ya_se_sabia_de_la_nota_no_se_pisa,
    el_catalogo_y_los_patrones_no_se_desincronizan,
    las_bebidas_y_la_cortesia_LLEGAN_A_LA_BASE,
    toda_columna_nueva_esta_en_las_dos_rutas,
]


if __name__ == "__main__":
    sys.exit(comun.correr("amenidades y bebidas", PRUEBAS))
