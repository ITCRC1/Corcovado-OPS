"""Fija que de una nota de reserva solo pase a la hoja del dia lo que sirve para operar.

POR QUE ESTA SUITE. Lo pidio el lodge: «en la parte de notas solo colocar notas
relevantes (no tarifas, no upgrades, no negociaciones)». La columna de notas del PDF
corta a 110 caracteres, asi que un «FACTURAR A CXC $7.775,19 - MONTO TOTAL DE LA RSV
SOURCE: CR SUN TOURS» por delante se come el renglon y tapa el «reservar el Sunset
Drinks a las 5:30pm» que venia detras. La plata no solo sobra: desplaza.

LO QUE DE VERDAD VIGILA ESTA SUITE ES LO QUE NO SE PUEDE PERDER. Filtrar es esconder, y
esconder de mas no da error: la hoja sale limpia, nadie echa de menos lo que no ve, y la
cuna que habia que poner no se pone. Los dos casos que fija, los dos reales:

  · «Favor confirmar el queque ($24.6) y unas fresas ($28.25) con chocolate» — una
    instruccion para cocina con el precio metido dentro. Es LA MISMA nota que el lodge
    pidio rescatar hace unas semanas porque no se estaba leyendo; tirarla por llevar una
    cifra seria volver a perderla por el otro lado.
  · «...facturar a la agencia Para el vuelo de salida deben estar registrando a las
    13:45» — la factura y la hora del vuelo pegadas sin un punto en medio. La primera
    version de este filtro dejaba esa nota VACIA.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun                                      # noqa: E402

import notas as N                                 # noqa: E402


# ---------------------------------------------------------------------------
# Lo que NO se puede perder
# ---------------------------------------------------------------------------

def una_cifra_suelta_no_tira_la_instruccion(c):
    """EL CASO DEL QUEQUE. Lleva precios dentro y es una tarea de cocina."""
    texto = ("Favor confirmar el queque ($24.6) el de 2 personas y de vainilla para la "
             "noche Agregar unas fresas ($28.25) con chocolate en la habitación para el "
             "check in con una tarjeta que diga: Dear Ann Happy Birthday!")
    salida = N.solo_lo_operativo(texto)
    for esperado in ("queque", "vainilla", "fresas", "chocolate", "Happy Birthday"):
        c.cierto(esperado in salida, f"se queda «{esperado}»")
    for cifra in ("$24.6", "$28.25"):
        c.cierto(cifra not in salida, f"y se va la cifra {cifra}")


def la_factura_pegada_a_una_hora_no_se_lleva_la_hora(c):
    """LA OTRA MITAD. El PMS pega dos frases sin puntuacion; juzgando la nota entera
    habria que tirar la hora del vuelo con la factura del Sirena."""
    texto = ("se agrega adicional Sirena $772.92 facturar a la agencia Para el vuelo de "
             "salida deben estar registrando a las 13:45 PM, favor indicar salida del "
             "Lodge.")
    salida = N.solo_lo_operativo(texto)
    c.cierto("13:45" in salida, "la hora de registro se queda")
    c.cierto("salida del Lodge" in salida,
             "y la frase entera, sin partirse en «salida del» y «Lodge»")
    c.cierto("772.92" not in salida and "facturar" not in salida, "la factura se va")
    c.cierto(salida.strip() != "", "y la nota NO queda vacia")
    # Y con la factura se va su arranque: «se agrega adicional» solo no dice nada y se
    # comia diecinueve de los ciento diez caracteres que caben en la columna.
    c.cierto(not salida.startswith("se agrega adicional"),
             "el arranque colgado de la frase comercial tambien se va")


def una_instruccion_corta_delante_de_un_cobro_se_queda(c):
    """La contraparte del arranque colgado, que es la que evita pasarse.

    «RECOGER EL EQUIPAJE» delante de un cobro es igual de corto, pero es una instruccion
    de verdad: empieza en mayuscula y nadie la escribio como principio de la frase
    siguiente. Sin esta distincion, limpiar la nota costaria el equipaje de alguien.
    """
    salida = N.solo_lo_operativo("RECOGER EL EQUIPAJE COBRAR $50 AL INGRESO")
    c.cierto("RECOGER EL EQUIPAJE" in salida, "la instruccion se queda")
    c.cierto("COBRAR" not in salida and "$50" not in salida, "y el cobro se va")


def una_alergia_no_se_va_por_parecerse_a_una_tarifa(c):
    """«Separate beds» y «separate fryers» llevan «rate» dentro. Las dos son de verdad y
    una es de una alergia, que es justo lo que no se puede perder."""
    for texto in ("Separate beds",
                  "any foods cooked need to be made in separate fryers, with clean "
                  "cookware, to minimize any risks to my health"):
        c.igual(N.es_comercial(texto), False, f"«{texto[:28]}…» no es comercial")
        c.cierto(N.solo_lo_operativo(texto) != "", "y se queda en la hoja")


def lo_que_hay_que_preparar_se_queda(c):
    """Un tour de cortesia y una amenidad de contrato son cosas que alguien monta. Suenan
    comerciales y no lo son para esto: el que las prepara necesita leerlas."""
    for texto in ("Incluido en la reserva: Tour de cortesía",
                  "Viaje por celebracion del cumpleaños de Mr James, favor agregar "
                  "alguna amenidad de contrato."):
        c.cierto(N.solo_lo_operativo(texto) != "", f"se queda «{texto[:34]}…»")
    salida = N.solo_lo_operativo("Viaje por celebracion del cumpleaños de Mr James, "
                                 "favor agregar alguna amenidad de contrato.")
    c.cierto("Mr James" in salida, "y «Mr James» no se parte en dos")


# ---------------------------------------------------------------------------
# Lo que si se va
# ---------------------------------------------------------------------------

def la_plata_se_va(c):
    comerciales = [
        "FACTURAR A CXC $7,775.19 - MONTO TOTAL DE LA RSV",
        "SOURCE: CR SUN TOURS",
        "Upgrade de Sirena a corcovado por reservar directo",
        "Se le honoro tarifas de tour book 2025",
        "Clientes tiene un credito de $759.36 por reserva adicional de PNC",
        "SE LE COBRA MGS POR 4 PAX PARA CUMPLIR EL MINIMO",
        "cobrar 50% solicitar que el pago sea con mastercard para aplicar la oferta",
        "Tarifa neta + 10% por que no hay tarifas 2027",
        "TRANSBORDO YA QUEDÓ CARGADO DESDE FIXED CHARGES, NO VOLVER A POSTEAR",
        "Se le da freeupgrade de Corcovado a Treehouse",
    ]
    for texto in comerciales:
        c.igual(N.solo_lo_operativo(texto), "", f"se va «{texto[:40]}…»")


def una_etiqueta_con_una_cifra_no_es_una_nota(c):
    """Quitada la cifra no queda nota, queda la etiqueta."""
    for texto in ("TOTAL $1,182.51", "TOTAL BOOKING RSV: $9,166.72"):
        c.igual(N.solo_lo_operativo(texto), "", f"se va «{texto}»")


def el_encabezado_solo_no_es_una_nota(c):
    """«ATENCION FRONT DESK» a secas no dice nada en una columna que ya se llama NOTAS."""
    c.igual(N.solo_lo_operativo("ATENCION FRONT DESK: COLOCAR NOTA DE ATTACHMENTS EN LA "
                                "HABITACIÓN EL DÍA DEL CHECK IN"),
            "COLOCAR NOTA DE ATTACHMENTS EN LA HABITACIÓN EL DÍA DEL CHECK IN",
            "se queda la instruccion, no el encabezado")
    c.igual(N.solo_lo_operativo("ATENCION FRONT DESK"), "", "el encabezado solo se va")
    # Pero una nota de verdad que EMPIECE parecido no se toca.
    c.cierto(N.solo_lo_operativo("Salida del lodge a las 7:00 a.m.") != "",
             "«Salida del lodge a las 7:00» no es un encabezado")


def lo_repetido_se_dice_una_vez(c):
    """El PMS copia el mismo aviso en dos campos; en la hoja ocuparia el doble para decir
    lo mismo, y el doble de una columna que corta a 110 caracteres son 110 perdidos."""
    texto = ("AGENCIA INDICA QUE SE DEBE DE COORDINAR CON ELLOS LA SALIDA DEL HOTEL "
             "| ATENCION FRONT DESK: AGENCIA INDICA QUE SE DEBE DE COORDINAR CON ELLOS "
             "LA SALIDA DEL HOTEL")
    salida = N.solo_lo_operativo(texto)
    c.igual(salida.count("AGENCIA INDICA"), 1, "una sola vez")


def sin_nota_no_pasa_nada(c):
    for vacio in (None, "", "   ", " - ", "·"):
        c.igual(N.solo_lo_operativo(vacio), "", f"«{vacio}» no revienta")


PRUEBAS = [
    una_cifra_suelta_no_tira_la_instruccion,
    la_factura_pegada_a_una_hora_no_se_lleva_la_hora,
    una_instruccion_corta_delante_de_un_cobro_se_queda,
    una_alergia_no_se_va_por_parecerse_a_una_tarifa,
    lo_que_hay_que_preparar_se_queda,
    la_plata_se_va,
    una_etiqueta_con_una_cifra_no_es_una_nota,
    el_encabezado_solo_no_es_una_nota,
    lo_repetido_se_dice_una_vez,
    sin_nota_no_pasa_nada,
]


if __name__ == "__main__":
    sys.exit(comun.correr("Notas de la hoja del dia", PRUEBAS))
