"""
Catálogo de textos en inglés para el itinerario de bienvenida del huésped.
Traduce cada código de tour del sistema al bloque que aparece en el PDF que
recibe el huésped: nombre de la actividad, horario y recomendaciones.

Fuente: documento "TOUR_INGLES.pdf" del hotel.
"""

# ---------------------------------------------------------------------------
# Horarios del traslado, según lo dispuesto por el lodge
# ---------------------------------------------------------------------------
# Por Sierpe el traslado es en bote y sale a la misma hora todos los días, así que el
# PDF de reservas casi nunca escribe la hora: se da por sabida. Por Drake depende del
# vuelo de cada huésped y se calcula hacia atrás (ver itinerario.calcular_logistica_salida).
# Están aquí, con nombre, porque los usan tanto el itinerario del huésped como la
# pantalla de Transporte: si algún día cambia el horario del bote, se cambia una vez.
SIERPE_BOTE_LLEGADA = "11:30 a.m."
SIERPE_SALIDA = {"equipaje": "7:00 a.m.", "checkout": "7:45 a.m.", "bote": "8:00 a.m."}

# Recomendaciones que se repiten en varios tours, para no duplicarlas
VESTIR_SELVA = "What to wear: Long pants, closed shoes or boots."
LLEVAR_SELVA = ("What to bring: Sunscreen, refillable water bottle, sun hat, "
                "and bug spray.")
VESTIR_AGUA = ("What to wear: Bathing suit, shorts or long pants, and water shoes. "
               "During the rainy season, we recommend bringing a light rain jacket.")
LLEVAR_AGUA = ("What to bring: Camera, sunscreen, sun hat, and a refillable water bottle. "
               "Towels will be provided for your convenience.")
VESTIR_COMODO = "What to wear: Comfortable clothes, a hat, and hiking shoes."
LLEVAR_COMODO = ("What to bring: Sunscreen, refillable water bottle, bug spray, "
                 "and a camera.")

# Cada entrada: código del sistema -> texto para el huésped.
# "variantes" se usa cuando el mismo tour cambia según quién lo guía.
TOURS_ITINERARIO = {
    "PNC": {
        "nombre": "Hike in Corcovado National Park\nSan Pedrillo",
        "duracion": "(5 HOURS TOUR)",
        "horario": "Be at the guide house at 7:00 a.m.\nLunch will be around 12:30 p.m.",
        "detalles": f"{VESTIR_SELVA}\n{LLEVAR_SELVA}",
    },
    "SIRENA": {
        "nombre": "Hike in Corcovado National Park\nSirena Station",
        "duracion": "(5 HOURS TOUR)",
        # El punto y la hora de encuentro cambian según el guía sea del hotel o externo
        "variantes": {
            "HOTEL": "Breakfast at 5:45 a.m. Be at the guide house at 6:15 a.m.\n"
                     "Lunch will be around 1:30 p.m.",
            "EXTERNO": "Breakfast at 5:45 a.m. Be at front desk at 6:10 a.m.\n"
                       "Lunch will be around 1:30 p.m.",
        },
        "horario": "Breakfast at 5:45 a.m. Be at the guide house at 6:15 a.m.\n"
                   "Lunch will be around 1:30 p.m.",
        "detalles": "What to wear: Long pants or shorts, water shoes, closed shoes or boots.\n"
                    f"{LLEVAR_SELVA}",
    },
    "ISLA": {
        "nombre": "Snorkeling at\nCaño Island",
        "duracion": "(5 HOURS TOUR)",
        "horario": "Be at the dive center at 7:15 a.m.\nLunch will be around 1:30 p.m.",
        "detalles": f"{VESTIR_AGUA}\n{LLEVAR_AGUA}",
    },
    "SNORKEL": {
        "nombre": "Snorkeling at\nCaño Island",
        "duracion": "(5 HOURS TOUR)",
        "horario": "Be at the dive center at 7:15 a.m.\nLunch will be around 1:30 p.m.",
        "detalles": f"{VESTIR_AGUA}\n{LLEVAR_AGUA}",
    },
    "BUCEO": {
        "nombre": "Scuba Diving",
        "duracion": "(5 HOURS TOUR)",
        "horario": "Be at the dive center at 7:15 a.m.\nLunch will be around 12:30 p.m.",
        "detalles": f"{VESTIR_AGUA}\n{LLEVAR_AGUA}",
    },
    "NW": {
        "nombre": "Night Walk",
        "duracion": "",
        "horario": "Be at the guide house at 5:45 p.m.\nDinner will be around 7:30 p.m.",
        "detalles": "What to wear: Long pants, closed shoes or rubber boots.\n"
                    "What to bring: Refillable water bottle, camera, flashlight, and bug spray.",
    },
    "PAJAREO": {
        "nombre": "Bird Watching Tour",
        "duracion": "(2 HOURS TOUR)",
        "horario": "Be at the guide house at 6:00 a.m.",
        "detalles": "What to wear: Long pants or shorts, closed shoes or boots.\n"
                    f"{LLEVAR_SELVA}",
    },
    "MANGLAR": {
        "nombre": "Mangrove Tour",
        "duracion": "(5 HOURS TOUR)",
        "horario": "Be at the guide house at 6:30 a.m.\nLunch will be around 1:30 p.m.",
        "detalles": "What to wear: Long pants or shorts, long-sleeve shirt, water shoes.\n"
                    "What to bring: Refillable water bottle, camera, sun hat, bug spray "
                    "and sunscreen.",
    },
    "CABALGATA": {
        "nombre": "Horseback Riding",
        "duracion": "(4 HOURS TOUR)",
        "horario": "Be at the guide house at 7:30 a.m.\nLunch around 12:30 p.m.",
        "detalles": "What to wear: Long pants or shorts, slacks, and closed shoes "
                    "(required for horseback riding).\n"
                    "What to bring: Sunscreen, bug spray, camera, water shoes & sun hat.",
    },
    "BALLENAS": {
        "nombre": "Whale Watching Tour",
        "duracion": "(3 HOURS TOUR)",
        "horario": "Be at the guide house at 7:30 a.m.\nLunch will be around 12:30 p.m.",
        "detalles": "What to wear: Shorts, comfortable sandals or water shoes.\n"
                    "What to bring: Small bags to safeguard belongings, sunscreen, "
                    "sun hat, and a refillable water bottle.",
    },
    "PESCA": {
        "nombre": "Sportfishing Tour",
        "duracion": "(4 HOURS TOUR)",
        "horario": "Be at the guide house at 7:00 a.m.\nLunch will be around 12:30 p.m.",
        "detalles": "What to wear: Shorts, flip flops, and a long-sleeve shirt.\n"
                    f"{LLEVAR_SELVA}",
    },
    "TREENET": {
        "nombre": "Tree Net Experience",
        "duracion": "",
        "horario": "Be at Terra Kitchen at 9:00 a.m. / 4:00 p.m.",
        "detalles": "What to wear: Long pants, closed shoes, and a long-sleeve shirt.\n"
                    "What to bring: Sunscreen, sun hat, refillable water bottle, and bug spray.",
    },
    "GTT": {
        "nombre": "Garden to Table",
        "duracion": "",
        "horario": "Be at the guide house at ___",   # hora variable, la completa recepción
        "detalles": f"{VESTIR_COMODO}\n{LLEVAR_COMODO}",
        "hora_manual": True,
    },
    # Tours que están en el catálogo del huésped pero aún no como código del sistema.
    # Se dejan listos para cuando se agreguen desde la pantalla de Catálogo.
    "SAN JOSECITO": {
        "nombre": "San Josecito Tour",
        "duracion": "(4 HOURS TOUR)",
        "horario": "Be at the guide house at 7:30 a.m.\nLunch will be around 12:30 p.m.",
        "detalles": "What to wear: Bathing suit, water shoes or sandals.\n"
                    "What to bring: Sunscreen, refillable water bottle, sun hat, "
                    "camera in a ziploc bag, and bug spray.",
    },
    "ATV": {
        "nombre": "ATV Tour",
        "duracion": "",
        "horario": "Be at the guide house at 6:50 a.m.\nLunch around 12:30 p.m.",
        "detalles": "What to wear: Swimsuit or comfortable clothes, and a hat.\n"
                    "What to bring: Sunscreen, sun hat, refillable water bottle, "
                    "bug spray, and a camera.",
    },
    "PERMACULTURA": {
        "nombre": "Casa Pequeña\nPermaculture Experience",
        "duracion": "",
        "horario": "Be at the guide house at 6:50 a.m.\nLunch will be around 12:30 p.m.",
        "detalles": f"{VESTIR_COMODO}\n{LLEVAR_COMODO}",
    },
    "CLARO": {
        "nombre": "Claro del Bosque\nExperience",
        "duracion": "",
        "horario": "Be at the guide house at ___",
        "detalles": f"{VESTIR_COMODO}\n{LLEVAR_COMODO}",
        "hora_manual": True,
    },
    "COOKING": {
        "nombre": "Cooking Class",
        "duracion": "",
        "horario": "Be at Terra Kitchen at ___",
        "detalles": "",
        "hora_manual": True,
    },
    "SPA": {
        "nombre": "Spa Treatment",
        "duracion": "",
        "horario": "Be at reception at ___\nBe ready at your room at ___\n"
                   "Be at Bungalow #29 at ___",
        "detalles": "Please avoid wearing earrings, watches, necklaces, bracelets, or rings.",
        "hora_manual": True,
    },
}


def texto_tour(codigo, guia_es_externo=False):
    """Devuelve el bloque de texto del tour para el itinerario del huésped.
    Si el tour tiene variantes según el guía (caso Sirena), usa la que corresponda."""
    base = codigo.replace(" PRIVADO", "").strip().upper()
    info = TOURS_ITINERARIO.get(base)
    if not info:
        # Tour sin texto definido: se muestra el código para que recepción lo complete
        return {
            "nombre": codigo.title(),
            "duracion": "",
            "horario": "___",
            "detalles": "",
            "requiere_revision": True,
        }
    horario = info["horario"]
    if "variantes" in info:
        horario = info["variantes"]["EXTERNO" if guia_es_externo else "HOTEL"]
    return {
        "nombre": info["nombre"],
        "duracion": info.get("duracion", ""),
        "horario": horario,
        "detalles": info.get("detalles", ""),
        "requiere_revision": bool(info.get("hora_manual")),
    }


def texto_llegada(punto, vuelo=None, hora=None):
    """Bloque del día de llegada, distinto según sea por Drake (avión) o Sierpe (bote)."""
    if (punto or "").lower() == "drake":
        horario = f"Flight: {vuelo}\n{hora}" if vuelo else (hora or "___")
        return {
            "nombre": "Arrival Day",
            "duracion": "",
            "horario": horario,
            "detalles": "Drake Bay Airport\nto CWL",
            "requiere_revision": not (vuelo and hora),
        }
    return {
        "nombre": "Arrival Day",
        "duracion": "",
        "horario": f"Boat departure around\n{hora or SIERPE_BOTE_LLEGADA}",
        "detalles": "From La Hacienda, Sierpe\nto CWL",
        "requiere_revision": False,
    }


def texto_salida(punto, vuelo=None, hora=None, logistica=None):
    """Bloque del día de salida. Por Sierpe los horarios son fijos; por Drake dependen
    del vuelo, así que se calculan hacia atrás o los completa recepción."""
    if (punto or "").lower() == "drake":
        if logistica:
            horario = (f"Luggage pick-up in your room at {logistica['equipaje']}\n"
                       f"Check-out at {logistica['checkout']}\n"
                       f"Boat departure at {logistica['bote']}")
        else:
            horario = ("Luggage pick-up in your room at ___\n"
                       "Check-out at ___\nBoat departure at ___")
        detalles = "From CWL to\nDrake Bay Airport"
        if vuelo or hora:
            detalles += f"\nFlight: {vuelo or ''} {hora or ''}".rstrip()
        return {
            "nombre": "Departure Day", "duracion": "", "horario": horario,
            "detalles": detalles, "requiere_revision": logistica is None,
        }
    return {
        "nombre": "Departure Day",
        "duracion": "",
        "horario": (f"Luggage pick-up in your room at {SIERPE_SALIDA['equipaje']}\n"
                    f"Check-out at {SIERPE_SALIDA['checkout']}\n"
                    f"Boat departure at {SIERPE_SALIDA['bote']}"),
        "detalles": "From CWL to\nLa Hacienda, Sierpe",
        "requiere_revision": False,
    }


# Horarios del lodge (segunda página del itinerario)
HORARIOS_LODGE = [
    ("Breakfast", "5:45 a.m. – 9:00 a.m."),
    ("Lunch", "12:00 p.m. – 2:00 p.m."),
    ("Dinner", "6:00 p.m. – 8:30 p.m."),
    ("", ""),
    ("El Bosque Bar", "6:00 a.m. – 9:00 p.m."),
    ("Bar (Terra Kitchen)", "4:30 p.m. – 6:00 p.m."),
    ("", ""),
    ("Spa", "9:00 a.m. – 11:30 a.m. / 12:00 p.m. – 5:00 p.m."),
    ("Reception", "5:30 a.m. – 10:00 p.m."),
    ("Gym", "6:00 a.m. – 6:00 p.m."),
    ("Laundry Service", "6:00 a.m. – 2:00 p.m."),
]

WHATSAPP_RECEPCION = "+506 8665 4540"
