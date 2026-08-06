"""
Traducciones del itinerario del huésped.

Se usa un catálogo fijo en vez de un traductor automático por tres razones:
funciona sin internet (el lodge tiene conexión intermitente), el texto es siempre
el mismo y revisado, y en un documento de bienvenida una traducción improvisada
se nota.

Lo que recepción escriba a mano en el editor NO se traduce: queda en el idioma en
que lo escribió, porque traducir texto libre al momento sería impredecible.
"""

IDIOMAS = {
    "en": "English",
    "es": "Español",
    "pt": "Português",
    "fr": "Français",
    "ru": "Русский",
}

# Los idiomas que necesitan tipografía con alfabeto cirílico
IDIOMAS_CIRILICOS = {"ru"}

MESES = {
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
           "agosto", "setembro", "outubro", "novembro", "dezembro"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"],
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
           "августа", "сентября", "октября", "ноября", "декабря"],
}

# Cómo se escribe la fecha en cada idioma: en inglés va el mes primero,
# en los demás el día primero, y en ruso con el mes en genitivo.
FORMATO_FECHA = {
    "en": "{mes} {dia:02d}",
    "es": "{dia} de {mes}",
    "pt": "{dia} de {mes}",
    "fr": "{dia} {mes}",
    "ru": "{dia} {mes}",
}

# --- Encabezados y textos fijos del documento ---
TEXTOS = {
    "dia": {"en": "Day", "es": "Día", "pt": "Dia", "fr": "Jour", "ru": "День"},
    "actividad": {"en": "Activity", "es": "Actividad", "pt": "Atividade",
                  "fr": "Activité", "ru": "Программа"},
    "horario": {"en": "Schedule", "es": "Horario", "pt": "Horário",
                "fr": "Horaire", "ru": "Расписание"},
    "detalles": {"en": "Details", "es": "Detalles", "pt": "Detalhes",
                 "fr": "Détails", "ru": "Подробности"},
    "bienvenida": {"en": "Welcome", "es": "Bienvenidos", "pt": "Bem-vindos",
                   "fr": "Bienvenue", "ru": "Добро пожаловать"},
    "sub1": {
        "en": "Welcome to Corcovado Wilderness Lodge by SCP.",
        "es": "Bienvenidos a Corcovado Wilderness Lodge by SCP.",
        "pt": "Bem-vindos ao Corcovado Wilderness Lodge by SCP.",
        "fr": "Bienvenue au Corcovado Wilderness Lodge by SCP.",
        "ru": "Добро пожаловать в Corcovado Wilderness Lodge by SCP.",
    },
    "sub2": {
        "en": "It will be our pleasure to assist you with anything you may need during your stay.",
        "es": "Será un placer atenderle en todo lo que necesite durante su estadía.",
        "pt": "Será um prazer atendê-lo em tudo o que precisar durante a sua estadia.",
        "fr": "Ce sera un plaisir de vous accompagner pour tout ce dont vous aurez besoin durant votre séjour.",
        "ru": "Мы будем рады помочь вам во всём, что понадобится во время вашего пребывания.",
    },
    "lema": {
        "en": "Where luxury meets the wild nature of Corcovado.",
        "es": "Donde el lujo se encuentra con la naturaleza salvaje de Corcovado.",
        "pt": "Onde o luxo encontra a natureza selvagem de Corcovado.",
        "fr": "Là où le luxe rencontre la nature sauvage de Corcovado.",
        "ru": "Там, где роскошь встречается с дикой природой Корковадо.",
    },
    "titulo_horarios": {"en": "SCHEDULE", "es": "HORARIOS", "pt": "HORÁRIOS",
                        "fr": "HORAIRES", "ru": "РАСПИСАНИЕ"},
    "snacks": {
        "en": "Craving a snack? You can purchase snacks at El Bosque Bar!",
        "es": "¿Se le antoja algo? Puede comprar snacks en el Bar El Bosque.",
        "pt": "Com vontade de um petisco? Você pode comprar snacks no Bar El Bosque.",
        "fr": "Une petite faim ? Vous pouvez acheter des en-cas au Bar El Bosque.",
        "ru": "Захотелось перекусить? Снеки можно купить в баре El Bosque.",
    },
    "whatsapp": {
        "en": "Reception WhatsApp (for any questions or requests):",
        "es": "WhatsApp de recepción (para cualquier consulta o solicitud):",
        "pt": "WhatsApp da recepção (para qualquer dúvida ou pedido):",
        "fr": "WhatsApp de la réception (pour toute question ou demande) :",
        "ru": "WhatsApp стойки регистрации (для любых вопросов и просьб):",
    },
    "cierre": {
        "en": "WE HOPE YOU ENJOY THIS 2.5% OF PARADISE!\nWE WILL DO EVERYTHING POSSIBLE TO MAKE YOUR STAY TRULY UNFORGETTABLE.",
        "es": "¡ESPERAMOS QUE DISFRUTE ESTE 2.5% DEL PARAÍSO!\nHAREMOS TODO LO POSIBLE PARA QUE SU ESTADÍA SEA INOLVIDABLE.",
        "pt": "ESPERAMOS QUE APROVEITE ESTES 2,5% DO PARAÍSO!\nFAREMOS TUDO O POSSÍVEL PARA QUE A SUA ESTADIA SEJA INESQUECÍVEL.",
        "fr": "NOUS ESPÉRONS QUE VOUS PROFITEREZ DE CES 2,5 % DE PARADIS !\nNOUS FERONS TOUT POUR QUE VOTRE SÉJOUR SOIT INOUBLIABLE.",
        "ru": "НАДЕЕМСЯ, ВАМ ПОНРАВЯТСЯ ЭТИ 2,5% РАЯ!\nМЫ СДЕЛАЕМ ВСЁ, ЧТОБЫ ВАШЕ ПРЕБЫВАНИЕ СТАЛО НЕЗАБЫВАЕМЫМ.",
    },
    "sin_itinerario": {
        "en": "No itinerary is available for this room at the moment.",
        "es": "No hay un itinerario disponible para esta habitación en este momento.",
        "pt": "Não há itinerário disponível para este quarto neste momento.",
        "fr": "Aucun itinéraire n'est disponible pour cette chambre pour le moment.",
        "ru": "Для этого номера пока нет программы пребывания.",
    },
    "consultar_recepcion": {
        "en": "Please check with reception.",
        "es": "Por favor consulte en recepción.",
        "pt": "Por favor, consulte a recepção.",
        "fr": "Veuillez vous adresser à la réception.",
        "ru": "Пожалуйста, обратитесь на стойку регистрации.",
    },
    "descargar_pdf": {"en": "Download PDF", "es": "Descargar PDF", "pt": "Baixar PDF",
                      "fr": "Télécharger le PDF", "ru": "Скачать PDF"},
    "habitacion": {"en": "Room", "es": "Habitación", "pt": "Quarto",
                   "fr": "Chambre", "ru": "Номер"},
}

# --- Horarios del lodge ---
SERVICIOS = {
    "Breakfast": {"es": "Desayuno", "pt": "Café da manhã", "fr": "Petit-déjeuner", "ru": "Завтрак"},
    "Lunch": {"es": "Almuerzo", "pt": "Almoço", "fr": "Déjeuner", "ru": "Обед"},
    "Dinner": {"es": "Cena", "pt": "Jantar", "fr": "Dîner", "ru": "Ужин"},
    "El Bosque Bar": {"es": "Bar El Bosque", "pt": "Bar El Bosque",
                      "fr": "Bar El Bosque", "ru": "Бар El Bosque"},
    "Bar (Terra Kitchen)": {"es": "Bar (Terra Kitchen)", "pt": "Bar (Terra Kitchen)",
                            "fr": "Bar (Terra Kitchen)", "ru": "Бар (Terra Kitchen)"},
    "Spa": {"es": "Spa", "pt": "Spa", "fr": "Spa", "ru": "Спа"},
    "Reception": {"es": "Recepción", "pt": "Recepção", "fr": "Réception", "ru": "Стойка регистрации"},
    "Gym": {"es": "Gimnasio", "pt": "Academia", "fr": "Salle de sport", "ru": "Тренажёрный зал"},
    "Laundry Service": {"es": "Lavandería", "pt": "Lavanderia",
                        "fr": "Service de blanchisserie", "ru": "Прачечная"},
}

# --- Nombres de las actividades ---
ACTIVIDADES = {
    "Arrival Day": {"es": "Día de llegada", "pt": "Dia de chegada",
                    "fr": "Jour d'arrivée", "ru": "День заезда"},
    "Departure Day": {"es": "Día de salida", "pt": "Dia de partida",
                      "fr": "Jour du départ", "ru": "День отъезда"},
    "Hike in Corcovado National Park\nSan Pedrillo": {
        "es": "Caminata en el Parque Nacional Corcovado\nSan Pedrillo",
        "pt": "Caminhada no Parque Nacional Corcovado\nSan Pedrillo",
        "fr": "Randonnée au parc national Corcovado\nSan Pedrillo",
        "ru": "Поход в национальный парк Корковадо\nСан-Педрильо"},
    "Hike in Corcovado National Park\nSirena Station": {
        "es": "Caminata en el Parque Nacional Corcovado\nEstación Sirena",
        "pt": "Caminhada no Parque Nacional Corcovado\nEstação Sirena",
        "fr": "Randonnée au parc national Corcovado\nStation Sirena",
        "ru": "Поход в национальный парк Корковадо\nстанция Сирена"},
    "Snorkeling at\nCaño Island": {
        "es": "Snorkeling en\nla Isla del Caño",
        "pt": "Snorkeling na\nIlha do Caño",
        "fr": "Snorkeling à\nl'île du Caño",
        "ru": "Снорклинг\nу острова Каньо"},
    "Scuba Diving": {"es": "Buceo", "pt": "Mergulho", "fr": "Plongée sous-marine",
                     "ru": "Дайвинг"},
    "Night Walk": {"es": "Caminata nocturna", "pt": "Caminhada noturna",
                   "fr": "Randonnée nocturne", "ru": "Ночная прогулка"},
    "Bird Watching Tour": {"es": "Tour de observación de aves",
                           "pt": "Tour de observação de aves",
                           "fr": "Sortie d'observation des oiseaux",
                           "ru": "Наблюдение за птицами"},
    "Mangrove Tour": {"es": "Tour por el manglar", "pt": "Tour pelo manguezal",
                      "fr": "Excursion dans la mangrove", "ru": "Тур по мангровым лесам"},
    "Horseback Riding": {"es": "Cabalgata", "pt": "Cavalgada",
                         "fr": "Randonnée à cheval", "ru": "Конная прогулка"},
    "Whale Watching Tour": {"es": "Avistamiento de ballenas",
                            "pt": "Observação de baleias",
                            "fr": "Observation des baleines",
                            "ru": "Наблюдение за китами"},
    "Sportfishing Tour": {"es": "Pesca deportiva", "pt": "Pesca esportiva",
                          "fr": "Pêche sportive", "ru": "Спортивная рыбалка"},
    "Tree Net Experience": {"es": "Experiencia Tree Net", "pt": "Experiência Tree Net",
                            "fr": "Expérience Tree Net", "ru": "Tree Net"},
    "Garden to Table": {"es": "Del jardín a la mesa", "pt": "Da horta à mesa",
                        "fr": "Du jardin à la table", "ru": "От сада до стола"},
    "San Josecito Tour": {"es": "Tour a San Josecito", "pt": "Tour a San Josecito",
                          "fr": "Excursion à San Josecito", "ru": "Тур в Сан-Хосесито"},
    "ATV Tour": {"es": "Tour en cuadraciclo", "pt": "Tour de quadriciclo",
                 "fr": "Excursion en quad", "ru": "Тур на квадроциклах"},
    "Casa Pequeña\nPermaculture Experience": {
        "es": "Casa Pequeña\nExperiencia de permacultura",
        "pt": "Casa Pequeña\nExperiência de permacultura",
        "fr": "Casa Pequeña\nExpérience de permaculture",
        "ru": "Casa Pequeña\nпермакультура"},
    "Cooking Class": {"es": "Clase de cocina", "pt": "Aula de cozinha",
                      "fr": "Cours de cuisine", "ru": "Кулинарный класс"},
    "Spa Treatment": {"es": "Tratamiento de spa", "pt": "Tratamento de spa",
                      "fr": "Soin au spa", "ru": "Спа-процедура"},
}

# --- Frases de horarios y recomendaciones ---
# Se traducen por frase completa para que el resultado suene natural en cada idioma.
FRASES = {
    "(5 HOURS TOUR)": {"es": "(TOUR DE 5 HORAS)", "pt": "(TOUR DE 5 HORAS)",
                       "fr": "(EXCURSION DE 5 HEURES)", "ru": "(5 ЧАСОВ)"},
    "(4 HOURS TOUR)": {"es": "(TOUR DE 4 HORAS)", "pt": "(TOUR DE 4 HORAS)",
                       "fr": "(EXCURSION DE 4 HEURES)", "ru": "(4 ЧАСА)"},
    "(3 HOURS TOUR)": {"es": "(TOUR DE 3 HORAS)", "pt": "(TOUR DE 3 HORAS)",
                       "fr": "(EXCURSION DE 3 HEURES)", "ru": "(3 ЧАСА)"},
    "(2 HOURS TOUR)": {"es": "(TOUR DE 2 HORAS)", "pt": "(TOUR DE 2 HORAS)",
                       "fr": "(EXCURSION DE 2 HEURES)", "ru": "(2 ЧАСА)"},
    "Be at the guide house at": {
        "es": "Preséntese en la casa de guías a las",
        "pt": "Compareça à casa dos guias às",
        "fr": "Présentez-vous à la maison des guides à",
        "ru": "Просим прийти к дому гидов в"},
    "Be at the dive center at": {
        "es": "Preséntese en el centro de buceo a las",
        "pt": "Compareça ao centro de mergulho às",
        "fr": "Présentez-vous au centre de plongée à",
        "ru": "Просим прийти в дайв-центр в"},
    "Be at front desk at": {
        "es": "Preséntese en recepción a las",
        "pt": "Compareça à recepção às",
        "fr": "Présentez-vous à la réception à",
        "ru": "Просим прийти на стойку регистрации в"},
    "Be at Terra Kitchen at": {
        "es": "Preséntese en Terra Kitchen a las",
        "pt": "Compareça ao Terra Kitchen às",
        "fr": "Présentez-vous à Terra Kitchen à",
        "ru": "Просим прийти в Terra Kitchen в"},
    "Be at reception at": {
        "es": "Preséntese en recepción a las",
        "pt": "Compareça à recepção às",
        "fr": "Présentez-vous à la réception à",
        "ru": "Просим прийти на стойку регистрации в"},
    "Be ready at your room at": {
        "es": "Esté listo en su habitación a las",
        "pt": "Esteja pronto no seu quarto às",
        "fr": "Soyez prêt dans votre chambre à",
        "ru": "Будьте готовы в своём номере в"},
    "Be at Bungalow #29 at": {
        "es": "Preséntese en el Bungalow #29 a las",
        "pt": "Compareça ao Bangalô #29 às",
        "fr": "Présentez-vous au bungalow n° 29 à",
        "ru": "Просим прийти в бунгало №29 в"},
    "Breakfast at": {"es": "Desayuno a las", "pt": "Café da manhã às",
                     "fr": "Petit-déjeuner à", "ru": "Завтрак в"},
    "Lunch will be around": {"es": "El almuerzo será alrededor de las",
                             "pt": "O almoço será por volta das",
                             "fr": "Le déjeuner sera servi vers",
                             "ru": "Обед примерно в"},
    "Lunch around": {"es": "Almuerzo alrededor de las", "pt": "Almoço por volta das",
                     "fr": "Déjeuner vers", "ru": "Обед примерно в"},
    "Dinner will be around": {"es": "La cena será alrededor de las",
                              "pt": "O jantar será por volta das",
                              "fr": "Le dîner sera servi vers",
                              "ru": "Ужин примерно в"},
    "Flight:": {"es": "Vuelo:", "pt": "Voo:", "fr": "Vol :", "ru": "Рейс:"},
    "Boat departure around": {"es": "Salida del bote alrededor de las",
                              "pt": "Saída do barco por volta das",
                              "fr": "Départ du bateau vers",
                              "ru": "Отправление лодки примерно в"},
    "Boat departure at": {"es": "Salida del bote a las", "pt": "Saída do barco às",
                          "fr": "Départ du bateau à", "ru": "Отправление лодки в"},
    "Luggage pick-up in your room at": {
        "es": "Recogida de equipaje en su habitación a las",
        "pt": "Recolha da bagagem no seu quarto às",
        "fr": "Récupération des bagages dans votre chambre à",
        "ru": "Багаж заберут из номера в"},
    "Check-out at": {"es": "Check-out a las", "pt": "Check-out às",
                     "fr": "Départ (check-out) à", "ru": "Выезд в"},
    "Drake Bay Airport\nto CWL": {
        "es": "Aeropuerto de Bahía Drake\nal lodge",
        "pt": "Aeroporto de Bahía Drake\nao lodge",
        "fr": "Aéroport de Bahía Drake\nvers le lodge",
        "ru": "Аэропорт Баия-Драке\nв отель"},
    "From La Hacienda, Sierpe\nto CWL": {
        "es": "Desde La Hacienda, Sierpe\nal lodge",
        "pt": "De La Hacienda, Sierpe\nao lodge",
        "fr": "De La Hacienda, Sierpe\nvers le lodge",
        "ru": "От La Hacienda, Сьерпе\nв отель"},
    "From CWL to\nDrake Bay Airport": {
        "es": "Del lodge al\naeropuerto de Bahía Drake",
        "pt": "Do lodge ao\naeroporto de Bahía Drake",
        "fr": "Du lodge à\nl'aéroport de Bahía Drake",
        "ru": "Из отеля в\nаэропорт Баия-Драке"},
    "From CWL to\nLa Hacienda, Sierpe": {
        "es": "Del lodge a\nLa Hacienda, Sierpe",
        "pt": "Do lodge a\nLa Hacienda, Sierpe",
        "fr": "Du lodge à\nLa Hacienda, Sierpe",
        "ru": "Из отеля в\nLa Hacienda, Сьерпе"},
    # Recomendaciones
    "What to wear:": {"es": "Qué vestir:", "pt": "O que vestir:",
                      "fr": "Tenue conseillée :", "ru": "Что надеть:"},
    "What to bring:": {"es": "Qué llevar:", "pt": "O que levar:",
                       "fr": "À emporter :", "ru": "Что взять с собой:"},
    "Long pants, closed shoes or boots.": {
        "es": "Pantalón largo, zapato cerrado o botas.",
        "pt": "Calça comprida, sapato fechado ou botas.",
        "fr": "Pantalon long, chaussures fermées ou bottes.",
        "ru": "Длинные брюки, закрытая обувь или сапоги."},
    "Long pants or shorts, water shoes, closed shoes or boots.": {
        "es": "Pantalón largo o short, zapato de agua, zapato cerrado o botas.",
        "pt": "Calça comprida ou shorts, sapato aquático, sapato fechado ou botas.",
        "fr": "Pantalon long ou short, chaussures d'eau, chaussures fermées ou bottes.",
        "ru": "Длинные брюки или шорты, обувь для воды, закрытая обувь или сапоги."},
    "Bathing suit, shorts or long pants, and water shoes. During the rainy season, we recommend bringing a light rain jacket.": {
        "es": "Traje de baño, short o pantalón largo, y zapato de agua. En temporada de lluvia recomendamos una chaqueta impermeable liviana.",
        "pt": "Traje de banho, shorts ou calça comprida e sapato aquático. Na época de chuvas, recomendamos uma capa de chuva leve.",
        "fr": "Maillot de bain, short ou pantalon long et chaussures d'eau. En saison des pluies, nous conseillons une veste imperméable légère.",
        "ru": "Купальный костюм, шорты или длинные брюки и обувь для воды. В сезон дождей рекомендуем лёгкую дождевую куртку."},
    "Camera, sunscreen, sun hat, and a refillable water bottle. Towels will be provided for your convenience.": {
        "es": "Cámara, protector solar, sombrero y botella reutilizable. Las toallas las proveemos nosotros.",
        "pt": "Câmera, protetor solar, chapéu e garrafa reutilizável. As toalhas são fornecidas por nós.",
        "fr": "Appareil photo, crème solaire, chapeau et gourde réutilisable. Les serviettes sont fournies.",
        "ru": "Фотоаппарат, солнцезащитный крем, шляпа и многоразовая бутылка для воды. Полотенца предоставляем мы."},
    "Sunscreen, refillable water bottle, sun hat, and bug spray.": {
        "es": "Protector solar, botella reutilizable, sombrero y repelente.",
        "pt": "Protetor solar, garrafa reutilizável, chapéu e repelente.",
        "fr": "Crème solaire, gourde réutilisable, chapeau et anti-moustiques.",
        "ru": "Солнцезащитный крем, многоразовая бутылка, шляпа и средство от насекомых."},
    "Long pants or shorts, closed shoes or boots.": {
        "es": "Pantalón largo o short, zapato cerrado o botas.",
        "pt": "Calça comprida ou shorts, sapato fechado ou botas.",
        "fr": "Pantalon long ou short, chaussures fermées ou bottes.",
        "ru": "Длинные брюки или шорты, закрытая обувь или сапоги."},
    "Long pants, closed shoes or rubber boots.": {
        "es": "Pantalón largo, zapato cerrado o botas de hule.",
        "pt": "Calça comprida, sapato fechado ou botas de borracha.",
        "fr": "Pantalon long, chaussures fermées ou bottes en caoutchouc.",
        "ru": "Длинные брюки, закрытая обувь или резиновые сапоги."},
    "Refillable water bottle, camera, flashlight, and bug spray.": {
        "es": "Botella reutilizable, cámara, linterna y repelente.",
        "pt": "Garrafa reutilizável, câmera, lanterna e repelente.",
        "fr": "Gourde réutilisable, appareil photo, lampe torche et anti-moustiques.",
        "ru": "Многоразовая бутылка, фотоаппарат, фонарик и средство от насекомых."},
    "Long pants or shorts, long-sleeve shirt, water shoes.": {
        "es": "Pantalón largo o short, camisa de manga larga, zapato de agua.",
        "pt": "Calça comprida ou shorts, camisa de manga longa, sapato aquático.",
        "fr": "Pantalon long ou short, chemise à manches longues, chaussures d'eau.",
        "ru": "Длинные брюки или шорты, рубашка с длинным рукавом, обувь для воды."},
    "Refillable water bottle, camera, sun hat, bug spray and sunscreen.": {
        "es": "Botella reutilizable, cámara, sombrero, repelente y protector solar.",
        "pt": "Garrafa reutilizável, câmera, chapéu, repelente e protetor solar.",
        "fr": "Gourde réutilisable, appareil photo, chapeau, anti-moustiques et crème solaire.",
        "ru": "Многоразовая бутылка, фотоаппарат, шляпа, средство от насекомых и крем от солнца."},
    "Long pants or shorts, slacks, and closed shoes (required for horseback riding).": {
        "es": "Pantalón largo o short y zapato cerrado (obligatorio para cabalgar).",
        "pt": "Calça comprida ou shorts e sapato fechado (obrigatório para cavalgar).",
        "fr": "Pantalon long ou short et chaussures fermées (obligatoires pour l'équitation).",
        "ru": "Длинные брюки или шорты и закрытая обувь (обязательна для верховой езды)."},
    "Sunscreen, bug spray, camera, water shoes & sun hat.": {
        "es": "Protector solar, repelente, cámara, zapato de agua y sombrero.",
        "pt": "Protetor solar, repelente, câmera, sapato aquático e chapéu.",
        "fr": "Crème solaire, anti-moustiques, appareil photo, chaussures d'eau et chapeau.",
        "ru": "Крем от солнца, средство от насекомых, фотоаппарат, обувь для воды и шляпа."},
    "Shorts, comfortable sandals or water shoes.": {
        "es": "Short, sandalias cómodas o zapato de agua.",
        "pt": "Shorts, sandálias confortáveis ou sapato aquático.",
        "fr": "Short, sandales confortables ou chaussures d'eau.",
        "ru": "Шорты, удобные сандалии или обувь для воды."},
    "Small bags to safeguard belongings, sunscreen, sun hat, and a refillable water bottle.": {
        "es": "Bolsas pequeñas para proteger sus pertenencias, protector solar, sombrero y botella reutilizable.",
        "pt": "Sacos pequenos para proteger seus pertences, protetor solar, chapéu e garrafa reutilizável.",
        "fr": "Petits sacs pour protéger vos affaires, crème solaire, chapeau et gourde réutilisable.",
        "ru": "Небольшие сумки для защиты вещей, крем от солнца, шляпа и многоразовая бутылка."},
    "Shorts, flip flops, and a long-sleeve shirt.": {
        "es": "Short, sandalias y camisa de manga larga.",
        "pt": "Shorts, chinelos e camisa de manga longa.",
        "fr": "Short, tongs et chemise à manches longues.",
        "ru": "Шорты, шлёпанцы и рубашка с длинным рукавом."},
    "Long pants, closed shoes, and a long-sleeve shirt.": {
        "es": "Pantalón largo, zapato cerrado y camisa de manga larga.",
        "pt": "Calça comprida, sapato fechado e camisa de manga longa.",
        "fr": "Pantalon long, chaussures fermées et chemise à manches longues.",
        "ru": "Длинные брюки, закрытая обувь и рубашка с длинным рукавом."},
    "Sunscreen, sun hat, refillable water bottle, and bug spray.": {
        "es": "Protector solar, sombrero, botella reutilizable y repelente.",
        "pt": "Protetor solar, chapéu, garrafa reutilizável e repelente.",
        "fr": "Crème solaire, chapeau, gourde réutilisable et anti-moustiques.",
        "ru": "Крем от солнца, шляпа, многоразовая бутылка и средство от насекомых."},
    "Comfortable clothes, a hat, and hiking shoes.": {
        "es": "Ropa cómoda, sombrero y zapato de caminata.",
        "pt": "Roupas confortáveis, chapéu e sapato de caminhada.",
        "fr": "Vêtements confortables, chapeau et chaussures de randonnée.",
        "ru": "Удобная одежда, шляпа и обувь для походов."},
    "Sunscreen, refillable water bottle, bug spray, and a camera.": {
        "es": "Protector solar, botella reutilizable, repelente y cámara.",
        "pt": "Protetor solar, garrafa reutilizável, repelente e câmera.",
        "fr": "Crème solaire, gourde réutilisable, anti-moustiques et appareil photo.",
        "ru": "Крем от солнца, многоразовая бутылка, средство от насекомых и фотоаппарат."},
    "Bathing suit, water shoes or sandals.": {
        "es": "Traje de baño, zapato de agua o sandalias.",
        "pt": "Traje de banho, sapato aquático ou sandálias.",
        "fr": "Maillot de bain, chaussures d'eau ou sandales.",
        "ru": "Купальный костюм, обувь для воды или сандалии."},
    "Sunscreen, refillable water bottle, sun hat, camera in a ziploc bag, and bug spray.": {
        "es": "Protector solar, botella reutilizable, sombrero, cámara en bolsa hermética y repelente.",
        "pt": "Protetor solar, garrafa reutilizável, chapéu, câmera em saco hermético e repelente.",
        "fr": "Crème solaire, gourde réutilisable, chapeau, appareil photo dans un sac étanche et anti-moustiques.",
        "ru": "Крем от солнца, многоразовая бутылка, шляпа, фотоаппарат в герметичном пакете и средство от насекомых."},
    "Swimsuit or comfortable clothes, and a hat.": {
        "es": "Traje de baño o ropa cómoda, y sombrero.",
        "pt": "Traje de banho ou roupas confortáveis, e chapéu.",
        "fr": "Maillot de bain ou vêtements confortables, et un chapeau.",
        "ru": "Купальный костюм или удобная одежда и шляпа."},
    "Sunscreen, sun hat, refillable water bottle, bug spray, and a camera.": {
        "es": "Protector solar, sombrero, botella reutilizable, repelente y cámara.",
        "pt": "Protetor solar, chapéu, garrafa reutilizável, repelente e câmera.",
        "fr": "Crème solaire, chapeau, gourde réutilisable, anti-moustiques et appareil photo.",
        "ru": "Крем от солнца, шляпа, многоразовая бутылка, средство от насекомых и фотоаппарат."},
    "Please avoid wearing earrings, watches, necklaces, bracelets, or rings.": {
        "es": "Le pedimos no usar aretes, reloj, collares, pulseras ni anillos.",
        "pt": "Pedimos que não use brincos, relógio, colares, pulseiras ou anéis.",
        "fr": "Merci d'éviter boucles d'oreilles, montre, colliers, bracelets et bagues.",
        "ru": "Просим не надевать серьги, часы, цепочки, браслеты и кольца."},
}


def t(clave, idioma):
    """Texto fijo en el idioma pedido, con el inglés como respaldo."""
    d = TEXTOS.get(clave, {})
    return d.get(idioma) or d.get("en") or ""


def traducir_actividad(nombre, idioma):
    if idioma == "en":
        return nombre
    d = ACTIVIDADES.get(nombre)
    return (d.get(idioma) if d else None) or nombre


def traducir_servicio(nombre, idioma):
    if idioma == "en":
        return nombre
    d = SERVICIOS.get(nombre)
    return (d.get(idioma) if d else None) or nombre


def traducir_texto(texto, idioma):
    """Traduce un bloque de texto reemplazando las frases conocidas.

    Se hace por frases completas (no palabra por palabra) para que el resultado
    suene natural. Lo que no está en el catálogo —por ejemplo lo que recepción
    escribió a mano— se deja tal cual.
    """
    if idioma == "en" or not texto:
        return texto
    resultado = texto
    # Se reemplaza de la frase más larga a la más corta, para que
    # "Lunch will be around" no sea alterado por una coincidencia parcial.
    for frase in sorted(FRASES, key=len, reverse=True):
        if frase in resultado:
            traduccion = FRASES[frase].get(idioma)
            if traduccion:
                resultado = resultado.replace(frase, traduccion)
    return resultado


def formatear_fecha(iso, idioma):
    """'2026-08-05' -> 'August 05' / '5 de agosto' / '5 августа'."""
    import datetime
    try:
        d = datetime.date.fromisoformat(iso)
    except (ValueError, TypeError):
        return iso or ""
    mes = MESES.get(idioma, MESES["en"])[d.month - 1]
    return FORMATO_FECHA.get(idioma, FORMATO_FECHA["en"]).format(dia=d.day, mes=mes)


def fuentes_para(idioma):
    """Qué archivos de tipografía usar. El ruso necesita las que traen cirílico."""
    if idioma in IDIOMAS_CIRILICOS:
        return {"titulo": "Playfair-Bold-Cyr.ttf", "encabezado": "Playfair-Regular-Cyr.ttf",
                "cuerpo": "PTSansNarrow-Cyr.ttf", "cuerpo_bold": "PTSansNarrow-Cyr.ttf",
                "italica": "Playfair-Regular-Cyr.ttf"}
    return {"titulo": "Playfair-Bold.ttf", "encabezado": "Playfair-Regular.ttf",
            "cuerpo": "ArchivoNarrow-Regular.ttf", "cuerpo_bold": "ArchivoNarrow-SemiBold.ttf",
            "italica": "Cormorant-Italic.ttf"}


# --- Formato de la hora según el idioma ---
# El ruso y el francés no usan a.m./p.m.: en ruso es estándar el reloj de 24 horas
# y en francés se escribe "7h00". Dejarlo en inglés se leería raro.
FORMATO_HORA = {"en": "12h", "es": "12h", "pt": "24h", "fr": "fr", "ru": "24h"}

import re as _re

_HORA_RE = _re.compile(r"\b(\d{1,2}):(\d{2})\s*([ap])\.?\s?m\.?", _re.IGNORECASE)


def formatear_horas(texto, idioma):
    """Reescribe las horas del texto al formato propio del idioma."""
    estilo = FORMATO_HORA.get(idioma, "12h")
    if estilo == "12h" or not texto:
        return texto

    def convertir(m):
        h, mm, ap = int(m.group(1)), m.group(2), m.group(3).lower()
        if ap == "p" and h < 12:
            h += 12
        if ap == "a" and h == 12:
            h = 0
        if estilo == "fr":
            return f"{h}h{mm}"
        return f"{h:02d}:{mm}"

    return _HORA_RE.sub(convertir, texto)
