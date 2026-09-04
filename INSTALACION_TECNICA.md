# Guía técnica de instalación
## Sistema de Operación Hotelera — Corcovado Wilderness Lodge

Documento para la persona que administre el sistema.

**Despliegue actual: Railway** (contenedor Docker, una sola instancia, volumen
persistente en `/data`). El resto del documento sirve igual si algún día se mueve a
un servidor propio.

---

## 1. Qué es

Aplicación web autocontenida para la operación diaria del lodge (reservas, tours,
transporte, entradas a parques nacionales, itinerarios de huéspedes).

- **Backend:** Python + FastAPI, servido con Uvicorn
- **Base de datos:** SQLite en un archivo, modo WAL
- **Frontend:** una sola página HTML servida por el mismo proceso
- **Dependencias externas:** ninguna en operación normal

El acceso es **solo por navegador**: no se instala nada en los equipos de los
usuarios.

---

## 2. Requisitos

| | |
|---|---|
| Python | 3.9 o superior (probado en 3.12 y 3.14) |
| Sistema | Windows, Linux o macOS |
| RAM | 512 MB son suficientes |
| Disco | ~50 MB el programa + la base de datos (unos pocos MB al año) |
| Puerto | 8000 por defecto, configurable |

---

## 3. Instalación

```bash
# 1. Descomprimir el proyecto en la ruta deseada
# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Arrancar
cd backend
python launcher.py
```

El servidor queda escuchando en `0.0.0.0:8000` y sirve tanto la API como el frontend.

### Variables de entorno

| Variable | Por defecto | Para qué |
|---|---|---|
| `PORT` | — | Puerto de escucha. Lo inyecta Railway; tiene prioridad sobre `HOTEL_PORT` |
| `HOTEL_PORT` | `8000` | Puerto de escucha |
| `HOTEL_HOST` | `0.0.0.0` | Interfaz de escucha |
| `HOTEL_ABRIR_NAVEGADOR` | `1` (`0` en servidor) | Poner en `0` en un servidor sin pantalla |
| `HOTEL_DATA_DIR` | `<carpeta del programa>/data` | Ubicación de la base de datos y la configuración |
| `HOTEL_ENTORNO` | — | `produccion` activa las reglas de seguridad estrictas (ver §6) |
| `HOTEL_ADMIN_USER` | `recepcion` | Nombre de la cuenta inicial |
| `HOTEL_ADMIN_PASSWORD` | — | Contraseña de la cuenta inicial. **Obligatoria en producción**. También se usa para recuperar el acceso (§6.12) |
| `HOTEL_RESET_ADMIN` | — | `1` repone la contraseña de la cuenta de administración en el próximo arranque. Borrarla después |
| `HOTEL_SESION_HORAS` | `12` | Horas que dura una sesión antes de caducar |
| `HOTEL_SYNC_TOKEN` | — | Secreto compartido entre estaciones. Sin él la sincronización queda apagada |
| `HOTEL_CORS_ORIGINS` | — | Orígenes extra permitidos, separados por coma. Vacío = solo el propio dominio |

#### Opera Cloud (OHIP)

Sin estas variables la conexión con Opera queda apagada y el sistema funciona igual con
el PDF. Los valores salen de la ficha de la aplicación en el portal de OHIP. **Se
definen como variables de entorno, nunca dentro del sistema**: así no quedan escritas en
la base de datos ni viajan en un respaldo.

| Variable | En la ficha de OHIP | Obligatoria |
|---|---|---|
| `OPERA_BASE_URL` | Gateway URL | Sí |
| `OPERA_APP_KEY` | App Key | Sí |
| `OPERA_CLIENT_ID` | Client ID | Sí |
| `OPERA_CLIENT_SECRET` | Client Secret | Sí |
| `OPERA_HOTEL_ID` | Código del hotel en Opera | Sí |
| `OPERA_SCOPE` | Scope | Solo si OHIP lo entregó |
| `OPERA_ENTERPRISE_ID` | Enterprise ID | Solo si OHIP lo entregó |
| `OPERA_GRANT_TYPE` | Authentication Scheme | Solo si la deducción automática falla |
| `OPERA_USER` / `OPERA_PASSWORD` | Usuario de integración | Solo con esquema `password` |

El esquema de autenticación se deduce solo: si hay `OPERA_USER` y `OPERA_PASSWORD` se
usa `password`, y si no `client_credentials`. `OPERA_GRANT_TYPE` sirve para forzarlo
cuando la propiedad usa otro.

##### Qué pedirle a Oracle / al partner de Opera

El conector está terminado y probado; lo único que falta son estas credenciales, que
solo puede emitir Oracle. Texto para reenviarles:

> Necesitamos registrar una aplicación en OHIP (Oracle Hospitality Integration Platform)
> para nuestra propiedad, con acceso de **solo lectura** a reservas. Les pedimos:
>
> 1. **Gateway URL** del entorno (y si es de producción o de pruebas)
> 2. **App Key**
> 3. **Client ID** y **Client Secret**
> 4. **Hotel ID** (el código de la propiedad en Opera)
> 5. **Scope** y **Enterprise ID**, si su configuración los requiere
> 6. **Authentication Scheme**: ¿`client_credentials` o `password`? Si es `password`,
>    el usuario de integración y su contraseña
>
> Y que la aplicación tenga habilitada la API de reservas
> (`GET /rsv/v1/hotels/{hotelId}/reservations`) con estos bloques en
> `fetchInstructions`: `Reservation`, `ReservationPackages`, `ReservationComments`,
> `GuestComments`, `ReservationPreferences`, `ReservationTransportation`,
> `ReservationMemberships`, `ReservationAlerts`, `ReservationTraces`,
> `ReservationLinkedReservations`, `ReservationGuestList`.
>
> No necesitamos permisos de escritura: el sistema solo lee.

Si algún bloque no está contratado, la conexión funciona igual: ese dato llega vacío y
la vista previa lo señala. Los tours salen de `ReservationPackages` y las amenidades de
los bloques de comentarios y preferencias, así que esos dos son los que más pesan.

##### Con las credenciales en mano: `conectar_opera.bat`

Doble clic en **`conectar_opera.bat`**, en la carpeta del proyecto. Hace el diagnóstico
completo y no escribe nada en la base:

1. La primera vez deja `data/credenciales_opera.json` listo para rellenar y dice dónde
   está. Se abre con el Bloc de notas, se reemplazan los huecos `<...>` y se guarda. Lo
   que Oracle no haya entregado se deja como está.
2. Comprueba que autentican. Si no, muestra la respuesta literal de Oracle y la lista de
   causas por orden de frecuencia.
3. Pregunta a Opera qué bloques de datos responde, **uno por uno** — si un módulo no
   está contratado, Oracle rechaza la petición entera, así que probarlos juntos no dice
   cuál falla.
4. Descarga reservas y dice, campo por campo, qué llegó y qué no.
5. Muestra qué entraría al sistema.

Se aceptan los nombres con prefijo (`OPERA_APP_KEY`) o cortos (`app_key`), y el archivo
se lee aunque el Bloc de notas lo guarde con marca de orden de bytes.

**Las variables de entorno mandan sobre el archivo.** En el servidor de producción se
usan variables y el archivo no se lee; el archivo existe porque definir siete variables
de entorno en Windows para una prueba es un trámite que se hace mal y se ve igual que
una credencial equivocada.

El paso 4 es el que decide. Si algún campo llega vacío en **todas** las reservas, en esta
propiedad ese dato viene con otro nombre, y hay que corregir la ruta en `opera_mapeo.py`
(están todas juntas arriba del archivo, con varias alternativas cada una).

Para eso se comparte `data/opera_muestras/estructura_*.txt`, que trae **solo nombres y
tipos de campo**. El otro archivo de esa carpeta, `reservas_*.json`, **sí trae datos de
huéspedes**: ese no se comparte.

##### Lo aprendido contra el OHIP real de Corcovado (2026-09-02 al 2026-09-04)

Lo que costó un rato y queda escrito para no volver a descubrirlo.
Instalación: `mtcu11pr.hospitality-api.us-ashburn-1`, hub `ECRWLG`, hotel **`COWLCR`**.

> **Lo primero de todo: el código de hotel es `COWLCR`.** Durante dos días se probó con
> `CRWLG`, que **nunca fue** la propiedad de Corcovado. Eso —y nada más— era el
> `403 OPERAWS-GEN01244` del punto 3. Con el código correcto la consulta responde
> `200 OK` y baja las reservas. Antes de sospechar de un permiso, comprobar el código.
> El punto 3 se conserva porque el diagnóstico que describe sigue siendo válido: si
> algún día vuelve el 403 con el código bueno, entonces sí es permiso.

**1. El "Authentication Scheme" se copia mal.** La ficha de OHIP lo muestra como
*"Client Credentials"*, con mayúsculas y espacio. OAuth exige `client_credentials`.
Enviado tal cual, Oracle responde un `HTTP 401 Unauthorized` pelado —idéntico al de una
credencial equivocada—. Ya se normaliza solo (`normalizar_grant`), así que se puede
pegar como venga.

**2. La cabecera del Enterprise ID va SIN el prefijo `x-`.** Con `x-enterpriseId` —el
nombre de los ejemplos— Oracle responde:

```
HTTP 400   Enterprise ID is required
```

aunque el dato viaje en la cabecera **y** en el cuerpo. El mensaje engaña: dice que
falta cuando está, pero con otro nombre. Se probaron nueve variantes; la única que
entrega el token es la cabecera `enterpriseId` pelada. Ya está corregido.

**3. Autenticar y poder LEER son dos permisos distintos.** Con el token ya funcionando,
la consulta de reservas devolvía:

| Cabecera usada | Respuesta |
|---|---|
| `x-hotelid: CRWLG` *(código equivocado)* | 403 · `OPERAWS-GEN01244` · *User is not authorized to access data for resort* |
| `x-hubid: ECRWLG` | 403 · `OPERAWS-GEN01265` · *User is not authorized to access data for hub* |
| `x-hotelid: COWLCR` *(el correcto)* | **200 OK** |

Ese 403 era el código de hotel, no el permiso. Pero el mensaje de Oracle es exactamente
el mismo en los dos casos —*"not authorized"*—, así que la tabla queda como referencia:
si aparece con el código bueno, entonces sí es lo que dice.

Y da 403 **incluso sin ningún parámetro en la consulta**, lo que descarta que sea un
problema de parámetros. La ruta es la correcta: `/rsv/v1/hotels/{hotel}/reservations`
responde 403 mientras que las rutas inventadas responden 404.

Eso se concede en Opera/OHIP, no en este sistema: al **usuario de integración** hay que
asignarle la propiedad, darle a su rol las tareas de lectura de reservas, y suscribir la
aplicación a esa propiedad. El asistente ya reconoce estos códigos y lo dice en vez de
mandar a revisar credenciales que están bien.

**4. Los bloques van en parámetros REPETIDOS, no separados por comas.**

```
?fetchInstructions=Reservation&fetchInstructions=ReservationPreferences     ✅
?fetchInstructions=Reservation,ReservationPreferences                       ❌
```

Con comas, OHIP toma `Reservation,ReservationPreferences` como **un solo valor** que no
existe y rechaza la petición entera con `400 · OPERAWS-GEN01346 · Invalid value of:
Query`. Ya está corregido.

**5. Ese 400 se dispara ANTES del control de permisos, y por eso engaña.** Un bloque
válido con permiso faltante da 403; uno inválido da 400. Mandando los once bloques con
comas, el 400 salía siempre y **tapaba el 403** — parecía que el permiso ya estaba
concedido cuando no lo estaba. Costó dos vueltas de diagnóstico.

Se aprovecha: `descubrir` cuenta el 403 como *"el bloque existe, falta el permiso"*, así
que el inventario de bloques se puede levantar **antes** de tener acceso de lectura.

**6. Esta instalación solo expone dos bloques.** Probados 40 nombres, uno por uno:

| Bloque | ¿Lo expone? |
|---|---|
| `Reservation` | **sí** |
| `ReservationPreferences` | **sí** |
| `ReservationPackages`, `ReservationComments`, `GuestComments`, `ReservationTransportation`, `ReservationGuestList`, `ReservationTraces`, `ReservationAlerts`, `ReservationMemberships`, `ReservationLinkedReservations` | no |

Eso importa: sin `ReservationPackages` no vienen los **tours**, sin los de comentarios no
vienen las **amenidades**, sin `ReservationTransportation` no viene el **punto de
embarque** y sin `ReservationGuestList` no vienen los **acompañantes**. Con solo esos dos
bloques, Opera entregaría la reserva (fechas, habitación, titular, pax, estado) y nada de
la operación.

Desde fuera **no se puede distinguir** "esta versión no tiene ese bloque" de "la
aplicación no está suscrita a ese bloque": las dos cosas dan el mismo `GEN01346`. Oracle
sí lo puede ver, así que va en la misma petición que el permiso.

**7. Un bloque de más tumba la consulta ENTERA.** No devuelve ese bloque vacío y el
resto lleno: devuelve `400` y nada. Por eso la sincronización pedía los once y fallaba
siempre, aunque la descarga de diagnóstico —que sí filtraba— funcionara. Ya se corrigió:
los bloques concedidos se aprenden en la primera consulta y quedan en
`data/opera_bloques.json`; si Oracle cambia lo que concede, se vuelven a averiguar solos
y se reintenta. Se aprende **a partir del error**, así que el caso normal no paga ni una
petición de más.

##### LAS RESERVATION NOTES SÍ SE LEEN: el bloque se llama `Comments`

> **Este es el punto más importante de toda la sección.** Durante un buen rato se dio
> por imposible leer las notas, porque `fetchInstructions=ReservationComments` responde
> `400 GEN01346` y `/reservations/{id}/comments` responde 404 — y eso parece decir que
> la propiedad no las expone. **No es cierto: el nombre del bloque es `Comments`, a
> secas.** Se probaron 70 nombres hasta dar con él.

```
GET /rsv/v1/hotels/COWLCR/reservations/{id}
      ?fetchInstructions=Reservation&fetchInstructions=Comments

reservations.reservation[0].comments[].comment.text.value
reservations.reservation[0].comments[].comment.notificationLocation   'RESERVATION' | 'CASHIER'
```

Y el texto es **exactamente el que imprime el PDF**:

```
Paquete 4D/3N -Full board
PNC e ISLA
Entrada: Via Sierpe
Salida: Via Drake RZ1116 9:25am
---------------------------------------------------
Rooming:
<nombre> <pasaporte>
-------------------------------------------------
Operacion:
09: In
10: PNC 199536
11: ISLA 199528
12: Out
-------------------------------------------------
Notas:
Viene con rsv 594008465
```

Por eso **lo lee el MISMO lector que el PDF**: `pdf_parser.leer_texto_de_reserva()`,
que antes estaba enterrado dentro del bucle de `parse_reservations`. Ese formato lo
escribe recepción a mano y tiene mil variantes —`Operación` con tilde y sin, `ROOMING`
con o sin dos puntos, el punto de embarque vacío o con texto libre—; todas están
resueltas ahí, y ahora cada corrección le sirve a las dos fuentes.

La nota del área **`CASHIER`** se descarta a propósito: es el total y la fuente de la
venta (`Total $2,830.47`), no operación, y su texto solo ensuciaría los detectores.

##### Lo que se creía que faltaba

Confirmado con una captura de Opera. En la reserva, botón **Notes → Reservation Notes**,
hay una nota de tipo `RESERVATION` que dice, literalmente:

```
Paquete 3N/4D+PENSION COMPLETA PNC (San Pedrillo) + SIRENA
              ENTRADA: Via Sierpe
SALIDA: Via Drake RZ1116 a las 09:25
ROOMING: <nombres>
```

**Eso es exactamente lo que imprime el PDF**, y de ahí salen los tours, el régimen, el
punto de embarque y los acompañantes. Es el 100% de lo que falta.

Y es justo lo que el API no entrega:

| Camino | Resultado |
|---|---|
| bloque `ReservationComments` (búsqueda y una reserva) | `400 GEN01346` · no existe en el esquema de esta versión |
| `/reservations/{id}/comments` | 404 · y 8 variantes más (`notes`, `reservationNotes`, `notifications`…) también |

**Lo que sí funciona** (probado en reservas de huéspedes que pagan, no en cuartos de
cortesía):

| Sub-recurso | Qué trae |
|---|---|
| `/traces` | **sí trae contenido**: las tareas de recepción por departamento — `traceText`, `departmentId` (RESE, FRONT), `traceOn`. Ej.: "Comprar entradas", "follow up info pendiente: entrada, salida y pasaportes". Útil, pero **no son los tours** |
| `/routingInstructions` | quién paga (`payeeName`: ARA TOURS, GREEN WORLD ADVENTURES) y qué códigos de cargo se enrutan. Los tours aparecen como **códigos** (`3400 Corcovado Hike Tour`, `3670 Snorkeling Caño Island`, `3412 Private Guide`), pero es la configuración de facturación, **no el itinerario por día** |
| `/alerts` | responde; con contenido en 1 de 5 |
| `/csh/…/folios` | responde (~10 KB), sin cargos de tour |

> **La trampa de muestreo que costó dos conclusiones equivocadas:** las primeras pruebas
> se hicieron sobre reservas del 5 de septiembre, todas con tarifa `HUSR` y garantía
> `STAFF`/`COMP`/`HOUSE` — cuartos de cortesía y de personal, que no tienen ni notas ni
> tours. Con esa muestra `/traces` y `/alerts` parecían "siempre vacíos" y los paquetes
> "inexistentes". **Al sondear OHIP hay que usar reservas de huéspedes que pagan y con
> llegada lo bastante lejana como para que ya les hayan repartido los tours.**

##### LOS TOURS SÍ SE PUEDEN LEER: entrando a cada reserva

**La búsqueda de reservas no trae los paquetes, pero la consulta de UNA reserva sí, y
con su fecha.** Es la pieza que hacía falta:

```
GET /rsv/v1/hotels/COWLCR/reservations/{id}?fetchInstructions=Reservation

reservationPackages[].packageCode                     'CIS30'
reservationPackages[].…primaryDetails.description      'Caño Island Snorkeling 30%'
reservationPackages[].scheduleList[].consumptionDate   '2026-11-04'
reservationPackages[].scheduleList[].totalQuantity     2
```

La búsqueda devuelve 84 campos; entrar a la reserva devuelve **117**, y no hace falta
ningún bloque extra. Medido sobre **80 reservas**: 69 códigos de paquete distintos y
**ninguno sin fecha**.

El sufijo de los códigos es el descuento comercial (`CIS20`, `CIS25`, `CIS30`,
`CIS3027`, `CISWEB`), así que se identifica por la raíz — **pero solo después de probar
el código exacto**, por un caso que lo rompe:

| Código | Descripción | Es |
|---|---|---|
| `DINP` | Cena para paquetes web o reservaciones | una **comida** |
| `DINP30` | Cena Privada (setting especial y menú) | una **amenidad** |

Quitándole el sufijo, `DINP30` se volvería `DINP` y una cena privada entraría como una
cena normal. Sin ningún error: la cocina no montaría la cena, y nadie sabría por qué.
El orden está en `opera_paquetes.clasificar()`.

**Y lo que no se reconoce no se adivina.** Un código nuevo genera una alerta
`PAQUETE_SIN_MAPEAR` en vez de "algo parecido". Eso ya sirvió: al medir 223 reservas
aparecieron `CNW` (Complementary Night Walk → NW) y `WWE` (Whale Watching → BALLENAS),
que estaban sin mapear.

> **La trampa de muestreo que costó dos conclusiones equivocadas:** los primeros
> barridos se hicieron sobre reservas del 5 de septiembre, todas con tarifa `HUSR` y
> garantía `STAFF`/`COMP`/`HOUSE` — cuartos de cortesía y de personal, que no tienen ni
> notas ni tours. Con esa muestra los paquetes parecían "inexistentes" y `/traces`
> "siempre vacío". **Al sondear OHIP hay que usar reservas de huéspedes que pagan y con
> llegada lo bastante lejana como para que ya les hayan repartido los tours.** La vista
> previa reparte su muestra a lo largo de la ventana justo por esto.

##### CUIDADO: la fecha del paquete NO es la del tour

Parece razonable usar `scheduleList[].consumptionDate` para agendar los tours —es un
dato del sistema, no un texto escrito a mano—. **Es un error, y se midió:** en 15
reservas que tenían las dos cosas, la fecha del paquete **no coincidió con la del
itinerario ni una sola vez.**

| Reserva | Llega | El itinerario dice | Los paquetes dicen |
|---|---|---|---|
| 75067234 | 04-11 | PNC el 05, ISLA el 06 | PNC el 04, CLARO y SNORKEL el 07 |
| 56770981 | 20-11 | PNC el 21, ISLA el 22 | PNC el 20, CLARO y SNORKEL el 23 |
| 52702756 | 29-11 | PNC el 01, ISLA el 30 | PNC el 01, SNORKEL el 01 |

La `consumptionDate` es la fecha de **facturación**: cae el día de llegada o el último
de la estadía. Y el paquete tampoco usa los códigos del lodge —llama `SNORKEL` a lo que
el itinerario llama `ISLA`—.

**Manda el itinerario de la nota.** Los paquetes se usan para el **régimen de comidas**,
para las amenidades que Opera registra como servicio, y para saber **qué** tours están
vendidos (`tours_vendidos`), que no es lo mismo que cuándo.

##### Cobertura medida (224 reservas activas, septiembre a diciembre)

| Dato | Llega | |
|---|---|---|
| reserva, huésped, fechas, habitación, tipo, pax, estado | 100% | |
| **texto de la nota** | **98%** | |
| agencia | 97% | |
| **itinerario escrito** | **87%** | la sección existe |
| acompañantes con pasaporte | 81% | |
| **régimen de comidas** | **63%** | |
| **punto Sierpe/Drake** | **52%** | +85 reservas con entrada por confirmar |
| **tours ya repartidos** | 56 reservas | 99 tours: ISLA 43, PNC 43, BUCEO 6, NW 2, PAJAREO 2, SIRENA 2, PESCA 1 |
| amenidades detectadas del texto | 60 | 32 tarjeta de bienvenida, **14 alergias**, 6 sofá cama, 4 cumpleaños… |

**Los huecos son huecos del dato, no de la conexión.** Solo 56 reservas tienen los tours
repartidos porque eso se hace después de que entra la reserva; el PDF mostraría
exactamente lo mismo, porque imprime esta misma nota.

Dos consecuencias en el código:

- **Si la nota no tiene sección de operación, no se borran los tours que ya haya.** No
  poder leer el itinerario no es lo mismo que leerlo vacío. Si la sección existe y no
  tiene tours, eso sí es autoritativo (`reserva["itinerario_leido"]`).
- **El pax del tour sale del itinerario, no del paquete.** El `totalQuantity` del
  paquete cuenta lo facturado y no coincide con el día ni con el código, así que
  cruzarlo sería adivinar.

##### Lo que se le podría pedir a Oracle (ya no es urgente)

Con el bloque `Comments` ya no falta nada para apagar el PDF. Lo de abajo queda por si
alguna vez se quiere el dato estructurado en vez del texto — sería más robusto que
depender de cómo lo escriba recepción, pero **hoy no hace falta**. Texto para el ticket:

> Property `COWLCR` (chain `ECRWLG`), OHIP gateway `mtcu11pr`.
>
> **We need to read Reservation Notes over the API.** Our integration user authenticates
> and reads reservations fine, and `/reservations/{id}/traces`,
> `/reservations/{id}/routingInstructions` and `/csh/v1/.../folios` all return real data
> — so this is not a user-permission problem. But the reservation's own Notes are
> unreachable:
>
> - `fetchInstructions=ReservationComments` (on both `GET /reservations` and
>   `GET /reservations/{id}`) → `400 OPERAWS-GEN01346 · Invalid value of: Query`
> - `GET /rsv/v1/hotels/COWLCR/reservations/{id}/comments` → `404`
>
> Those Notes (type RESERVATION, notification area RESERVATION) hold the guest's tour
> itinerary, board plan, boat entry/exit point and rooming list. It is the information
> our operation runs on, and today the only way to get it is exporting the Arrivals
> Detailed report by hand.
>
> Please tell us how to read Reservation Notes on this subscription — enabling the
> `ReservationComments` fetch instruction, or whichever operation replaces it in the API
> version we are subscribed to.
>
> Same request, lower priority: `GuestComments`, `ReservationPackages`,
> `ReservationTransportation`, `ReservationGuestList`, `ReservationAlerts`.
>
> For context, this gateway serves only 5 modules (`rsv`, `crm`, `evm`, `act`, `rtp`) and
> `/rpt/v1/*` returns 404 on every path, so fetching the report itself is not an option
> either.

**Una sola cosa importa: las Reservation Notes.** Sin ese texto no hay tours ni
amenidades ni punto de embarque, y es el 100% de lo que falta para apagar el PDF. Los
demás bloques son secundarios. Y el argumento fuerte para Oracle es que `/traces` y
`/routingInstructions` **sí** devuelven datos: el usuario tiene permiso de lectura, así
que lo que falta es que la suscripción exponga las notas.

##### Dónde NO están las cosas (probado, para no volver a buscar)

Antes de dar por perdidos los tours y las notas se sondeó la instalación entera. Queda
escrito porque cada una de estas puertas parece la buena hasta que se prueba:

| Dónde se buscó | Qué pasó |
|---|---|
| La misma consulta de UNA reserva, 37 bloques | acepta 3: `Reservation`, `GuestComments`, `ReservationAwards`. **La lista de bloques cambia según la operación**: `GuestComments` funciona aquí y no en la búsqueda; `ReservationPreferences`, al revés |
| `/reservations/{id}/comments` | 404 · y otros 8 nombres (`notes`, `remarks`, `specialRequests`…) también |
| `/reservations/{id}/alerts`, `/traces`, `/preferences` | **200, pero vacíos en las 12 reservas probadas** |
| `/reservations/{id}/packages` | pide `productCode`: hay que preguntar tour por tour. Contesta —el paquete `SPA` aparece— pero **`scheduleList` viene vacío: sin fecha**. Un tour sin fecha no se puede agendar |
| `/act/v1/…/activities` (módulo de actividades) | 200 y `totalResults: 0` — el módulo está, el hotel no lo usa |
| `/rpt/v1/…` (API de reportes) | **404 en las 9 rutas**: el reporte de arrivals NO se puede pedir por API |
| Room Diary | no existe en OHIP; es una pantalla, no un endpoint |
| `/evm/v1/…/events` | responde, pero es el módulo de eventos de banquetes, no un registro de cambios |
| `modifiedFromDate`, `modifiedStartDate`, `lastModifiedDate` | **se ignoran EN SILENCIO**: responden 200 y devuelven reservas de 2025 ya salidas. Peor que un error, porque parecen funcionar |
| `/crm/v1/profiles/{id}` + `Comments` | 400 · solo acepta el bloque `Profile` |

**La conclusión práctica:** las amenidades y las alergias solo pueden estar en
`ReservationComments`, que es justo el bloque que Oracle no concede. Los endpoints de
alertas y trazas sí responden y vienen vacíos, así que ahí no están. Eso hace de
`ReservationComments` **lo más valioso que se le puede pedir a Oracle**.

##### Cómo queda la automatización con lo que hay

Se puede encender, y es seguro. La clave es que **cada fuente manda solo en lo que de
verdad trae** (`loader.load_batch(..., manda_en=...)`):

**Opera manda en todo**, porque trae todo:
`{nucleo, tours, regimen, amenidades, rooming, textos, transporte}`. Lo decide
`opera_sync.alcance_de_opera()` mirando si el bloque `Comments` está en la lista que se
le pide a cada reserva; si algún día dejara de entregarse, quita `textos` y
`transporte` y deja de pisar el trabajo del PDF en vez de vaciarlo.

Dos reglas hacen que convivir sea seguro, y las dos salieron de medir:

- **Cada fuente administra solo sus propias amenidades** (`amenidad_tarea.origen`:
  `PDF` | `MANUAL` | `OPERA`). Si Opera borrara las del PDF para poner las suyas,
  borraría casi todas: sus paquetes traen una amenidad en **1 de 223** reservas.
- **Opera no borra los tours de una reserva en la que no ve ninguno.** Trae paquetes en
  145 de 223; en las otras, "no veo tours" no es "no tiene tours", es "no puedo
  saberlo". El PDF sí borra, porque él trae la hoja completa
  (`_guardar_tours(borrar_si_vacio=)`).

Por qué importa tanto: medido antes de existir esto, una reserva real con trabajo hecho
**perdía sus 3 tours, sus 2 amenidades, el régimen, las notas y el punto de embarque** en
el primer ciclo. Y sin dar ningún error: la reserva quedaba ahí, correcta, y el resto en
blanco. Fijado en `probar_automatico.py`.

**Solo se reprocesa lo que cambió.** Como Opera no deja filtrar por fecha de
modificación, la comparación se hace de este lado contra `reserva.opera_modificado_en`.
Un ciclo sin cambios devuelve `SIN_CAMBIOS` y no escribe nada — así la marca de
actualización de una reserva significa algo, en vez de moverse cada media hora para
todas.

**Y si mueven las fechas después de repartir los tours**, `validar_tours_fuera_de_la_estadia()`
avisa de los que quedaron fuera. Está callado mientras todo esté bien: medido sobre la
base real, de 1.164 tours ninguno caía fuera de su estadía.

##### Y después

1. Con la vista previa limpia: pantalla **Importar** → **Sincronizar ahora**, una vez.
2. Revisar la Agenda y las Amenidades del día contra lo que ya se sabe.
3. Recién entonces **Encender la sincronización**.
4. Para producción, poner las credenciales como variables de entorno en Railway.

El PDF sigue funcionando igual todo el tiempo: son dos caminos hacia el mismo sitio, no
uno o el otro.

El resto de la configuración —encendido, cada cuántos minutos y qué ventana de fechas—
se maneja desde la pantalla **Importar**, y se guarda en `config_opera.json` dentro de
la carpeta de datos. No hace falta redesplegar para encenderla o apagarla.

Herramientas de línea de comandos, para ajustar el mapeo contra la respuesta real:

```bash
python backend/opera_cloud.py probar                          # ¿autentica?
python backend/opera_cloud.py descubrir 2026-08-10 2026-08-12 # ¿qué campos llegan?
python backend/opera_sync.py preview                          # ¿qué entraría? (no guarda)
```

`descubrir` deja dos archivos en `data/opera_muestras/`: la respuesta completa —que
**trae datos de huéspedes y no se sube a ningún lado**— y un `estructura_….txt` con solo
los nombres y tipos de campo, que sí se puede compartir para corregir el mapeo.

Ejemplo para un servidor:

```bash
HOTEL_PORT=8080 HOTEL_ABRIR_NAVEGADOR=0 HOTEL_ENTORNO=produccion \
HOTEL_ADMIN_PASSWORD='una-clave-larga' python launcher.py
```

### Despliegue en contenedor (Railway y similares)

El repositorio trae `Dockerfile` y `railway.json`. Puntos a respetar:

- **Volumen persistente montado en `/data`** (`HOTEL_DATA_DIR` ya apunta ahí). Sin
  volumen, cada despliegue arranca con la base vacía.
- **Una sola réplica.** La base es SQLite en un archivo; con dos réplicas cada una
  tendría su propia copia.
- `HOTEL_ADMIN_PASSWORD` definida antes del primer arranque, o el proceso se detiene
  con un mensaje explicando qué falta.
- El contenedor corre como usuario sin privilegios (uid 10001).

---

## 4. Ejecutar como servicio (solo si se sale de Railway)

En Railway no aplica: el contenedor ya es el servicio y se reinicia solo. Esto queda
documentado por si algún día el sistema se mueve a un servidor propio.

### Linux (systemd)

```ini
# /etc/systemd/system/hotel-corcovado.service
[Unit]
Description=Sistema de Operacion Hotelera Corcovado
After=network.target

[Service]
Type=simple
User=hotel
WorkingDirectory=/opt/corcovado-ops/backend
Environment=HOTEL_ABRIR_NAVEGADOR=0
Environment=HOTEL_PORT=8000
Environment=HOTEL_DATA_DIR=/var/lib/hotel_corcovado
ExecStart=/usr/bin/python3 launcher.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now hotel-corcovado
```

### Windows

Con NSSM (`nssm install HotelCorcovado`), apuntando a `python.exe` con argumento
`launcher.py`, directorio de trabajo `...\Corcovado-OPS\backend`, y las variables de
entorno anteriores.

---

## 5. Datos y respaldo

Todo el estado vive en **una sola carpeta** (`HOTEL_DATA_DIR`; en Railway, el volumen
montado en `/data`):

| Archivo | Contenido |
|---|---|
| `hotel.db` | Base de datos completa |
| `hotel.db-wal`, `hotel.db-shm` | Archivos de trabajo de SQLite (WAL) |
| `config_publicacion.json` | Credenciales de publicación de itinerarios |
| `sync_config.json` | Configuración de sincronización Sierpe ↔ Drake |
| `cache_itinerarios/` | PDF en caché, se puede borrar sin consecuencias |

En Railway esta carpeta debe ser un **volumen montado en `/data`**; si no, se pierde
en cada despliegue.

**Respaldar: pantalla Usuarios → «Descargar respaldo».** Baja un archivo `.db` con
toda la base. Es un clic, y por eso existe: antes el respaldo estaba solo documentado
como tres comandos encadenados con `railway ssh` y base64, y algo así no se hace nunca.

Usa `sqlite3.backup()`, no una copia del archivo. **No es un detalle:** la base corre en
modo WAL y los últimos cambios viven en `hotel.db-wal` hasta que SQLite los integra;
copiar `hotel.db` tal cual puede dejar afuera justo lo más reciente. Un respaldo al que
le falta el último día es peor que ninguno, porque nadie lo sabe hasta que hace falta.
Está fijado en `probar_respaldo.py`, que además comprueba que el archivo bajado abra
como base SQLite válida y traiga las mismas filas que el original.

El mismo respaldo, por línea de comandos (si hiciera falta sin pasar por la pantalla):

```bash
railway ssh "python -c \"import sqlite3; o=sqlite3.connect('/data/hotel.db'); d=sqlite3.connect('/data/respaldo.db'); o.backup(d); d.close(); o.close()\""
railway ssh "base64 /data/respaldo.db" > respaldo.b64
python -c "import base64; open('hotel-respaldo.db','wb').write(base64.b64decode(open('respaldo.b64').read()))"
```

⚠️ **Sigue sin haber respaldo automático, y el volumen de Railway no se respalda solo.**
La descarga hay que hacerla y **guardarla fuera de Railway** —en una computadora del
lodge o en Drive—: un respaldo que vive en el mismo servidor no protege de perder el
servidor. Conviene una copia semanal, y siempre una antes de desplegar.

**Del código no hay respaldo automático tampoco**, y en la máquina del lodge no hay
git: sin una copia no habría forma de volver atrás. Antes de tocar el código conviene
duplicar `backend/`, `frontend/` y los `.md` en una carpeta con la fecha, fuera del
repositorio (`Documentos\Respaldos-Corcovado\codigo_AAAA-MM-DD_HHMM`). **Nunca copiar
`data/`**: ahí viven las credenciales de Opera y las llaves de los avisos.

---

## 6. Seguridad — revisar antes de poner en producción

**1. Usuarios iniciales.** Con `HOTEL_ENTORNO=produccion` (o corriendo en Railway) el
sistema **no crea** los usuarios de demostración —sus contraseñas están publicadas en
esta documentación— y exige `HOTEL_ADMIN_PASSWORD` para crear la primera cuenta de
recepción. Si falta, el proceso se detiene con un mensaje explicándolo. Fuera de
producción sí se crean (`recepcion`, `gerencia`, `staff`): cambiarles la contraseña
desde la pantalla *Usuarios* antes de meter datos reales.

**2. Hay una ruta pública sin autenticación:** `GET /i/{habitacion}`. Es
intencional: la usan los huéspedes al escanear el código QR de su habitación, y no
pueden tener credenciales. Solo expone el itinerario de esa habitación (nombre y
actividades). Todo lo demás requiere token.

**3. La autenticación es por token** enviado en `Authorization: Bearer`. Las
contraseñas se guardan con hash PBKDF2-SHA256 (200 000 iteraciones) y salt por
usuario, con un mínimo de 10 caracteres. Las sesiones caducan según
`HOTEL_SESION_HORAS` (12 por defecto), y cambiar una contraseña cierra las sesiones
abiertas de esa cuenta.

**4. Intentos de login limitados:** 8 fallos seguidos desde el mismo origen y para el
mismo usuario bloquean el acceso 5 minutos (respuesta 429).

**5. Administrar usuarios es exclusivo del rol `recepcion`.** Quien puede cambiar la
contraseña de otro puede tomar su rol, así que gerencia —que sí escribe en el resto
del sistema— no llega a esa pantalla. Tampoco se puede desactivar la última cuenta de
recepción activa.

**6. Sincronización entre estaciones.** `GET /api/sync/pending` y `POST /api/sync/apply`
los usa la otra máquina, no una persona, así que no llevan sesión de usuario. Van
protegidos por el secreto compartido `HOTEL_SYNC_TOKEN` (cabecera `X-Sync-Token`). Si
la variable no está definida, ambas rutas responden 404 y la sincronización queda
apagada — que es lo correcto cuando hay una sola instalación.

**7. CORS cerrado por omisión.** El frontend lo sirve el mismo proceso, así que no se
necesita. `HOTEL_CORS_ORIGINS` permite listar orígenes concretos si algún día se sirve
desde otro dominio; nunca poner `*` en una instalación expuesta a internet.

**8. No hay HTTPS integrado.** En una intranet cerrada suele ser aceptable. Si se
publica hacia internet, ponerlo detrás de un proxy inverso (nginx, Caddy) con TLS —
Railway ya lo hace por su cuenta.

**9. Salida a internet:** por omisión el sistema no hace ninguna conexión saliente. Solo
las hace si se configura una de estas tres, y cada una queda apagada mientras falten sus
variables: la sincronización entre estaciones, el buzón de correo y Opera Cloud. Ninguna
es necesaria para operar: sin ellas el sistema funciona igual importando el PDF a mano.

**10. Nada de la carpeta de datos se sube al repositorio** (`.gitignore`): contiene
la base con los datos de huéspedes. Los reportes del PMS en PDF y las hojas de cálculo
también quedan excluidos, igual que las muestras crudas de Opera
(`data/opera_muestras/`), que traen nombres de huéspedes tal como los devuelve Oracle.

**13. Credenciales de Opera Cloud.** Viven únicamente en variables de entorno: no se
guardan en la base, no se escriben en ningún archivo de configuración y no se muestran
en pantalla. La API de estado devuelve solo los **nombres** de las variables que faltan,
nunca sus valores, ni siquiera a un usuario con todos los permisos. El token de acceso
que devuelve Oracle se guarda en memoria y se renueva solo; nunca toca el disco, así que
no puede filtrarse por un respaldo. Las cuatro rutas `/api/opera/*` exigen sesión con
permiso sobre la pantalla *Importar*.

**14. Opera nunca cancela reservas por dudas.** Al cargar un lote, el sistema marca como
canceladas las reservas del rango que Opera ya no reporta. Eso solo se aplica si se pudo
comprobar que la descarga vino completa; si la paginación quedó a medias o hubo un
corte, se cargan las reservas nuevas y **no se cancela ninguna**. Una reserva que falta
por un error de red no es una reserva cancelada, y sacar de la agenda a un huésped que
sí llega es un fallo mucho más caro que dejar una cancelada de más.

**12. Recuperar el acceso si nadie puede entrar.** En cada arranque el sistema
comprueba que exista al menos una cuenta de Recepción **activa**. Si no la hay —porque
se desactivó, se borró, o la base se recreó— la restaura desde `HOTEL_ADMIN_PASSWORD`:
reactiva la cuenta, le repone esa contraseña y cierra sus sesiones abiertas. Basta con
redesplegar. Si el problema es que nadie recuerda la contraseña pero la cuenta sí está
activa, se define `HOTEL_RESET_ADMIN=1`, se redespliega y **se borra la variable**
(si queda puesta, la contraseña se repone en cada despliegue). Ninguna de las dos cosas
toca reservas, huéspedes, tours ni itinerarios: solo las tablas `usuario` y `sesion`.

**11. Enlaces de los itinerarios.** Por omisión son `/i/05`, adivinables por número de
habitación. Solo muestran el itinerario del ocupante actual (nombre y actividades), sin
datos de contacto ni de pago. Si se quiere cerrar eso, la pantalla *Itinerarios QR*
tiene la opción **enlaces con código** (`/i/05-a1b2c3d4`): el sistema exige el código
correcto y `/i/05` deja de funcionar. Al activarla hay que reimprimir los códigos QR.

---

## 7. Puntos de comprobación

Con el servicio arriba (`SERVIDOR` = el dominio que asignó Railway):

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://SERVIDOR/api/salud   # 200 (base accesible)
curl -s -o /dev/null -w "%{http_code}\n" https://SERVIDOR/            # 200 (frontend)
curl -s -o /dev/null -w "%{http_code}\n" https://SERVIDOR/i/01        # 200 (página pública)
curl -s -o /dev/null -w "%{http_code}\n" https://SERVIDOR/api/reservas # 401 (exige sesión)
curl -s -X POST https://SERVIDOR/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"recepcion","password":"..."}'                    # devuelve token
```

**Que el volumen quedó bien montado** se comprueba importando un PDF, forzando un
redespliegue y verificando que las reservas siguen ahí. Vale la pena hacerlo una vez,
antes de empezar a usarlo de verdad.

---

## 8. Notas de rendimiento

Medido con 77 reservas y un mes de operación:

| Operación | Tiempo |
|---|---|
| Cualquier pantalla | < 30 ms |
| Búsqueda | ~3 ms |
| Generar el PDF de un itinerario | ~110 ms |
| Importar el PDF de reservas | ~3.5 s (extracción de texto) |

Concurrencia probada: 20 escrituras simultáneas de dos usuarios, todas exitosas, la
más lenta 0.74 s. Lecturas y escrituras en paralelo sin bloqueos (SQLite en WAL).

**Limitación conocida:** si dos usuarios editan el mismo registro al mismo tiempo,
prevalece el último que guarda, sin aviso. No hay bloqueo optimista.

---

## 9. Estructura del proyecto

```
Corcovado-OPS/
├── backend/
│   ├── launcher.py          Punto de entrada
│   ├── main.py              Rutas de la API
│   ├── init_db.py           Creación de la base y catálogo inicial
│   ├── schema.sql           Esquema
│   ├── auth.py              Autenticación y roles
│   ├── pdf_parser.py        Extracción del PDF del PMS
│   ├── buzon_pdf.py         Recoge el PDF de un buzón de correo
│   ├── opera_cloud.py       Conexión con Opera Cloud (OHIP): token y descarga
│   ├── opera_mapeo.py       Traduce el JSON de Opera al formato del sistema
│   ├── opera_sync.py        Ciclo automático de sincronización con Opera
│   ├── importer.py          Reglas de negocio de la importación
│   ├── loader.py            Carga a la base
│   ├── validations.py       Capacidades y conflictos de asignación
│   ├── grupos.py            Vínculos entre reservas que viajan juntas
│   ├── restaurantes.py      Turnos y cambios de comidas
│   ├── exports.py           Reportes en Excel y PDF
│   ├── itinerario.py        Generación del itinerario del huésped
│   ├── catalogo_itinerario.py  Actividades que se ofrecen al huésped
│   ├── traducciones.py      Catálogo de idiomas
│   ├── qr_huesped.py        Página pública por QR y enlaces por habitación
│   ├── publicador.py        Publicación de las páginas de huésped
│   └── sync_engine.py       Sincronización Sierpe ↔ Drake
├── frontend/
│   ├── index.html           Toda la interfaz
│   └── assets/              Logo, tipografías e imágenes
├── data/                    Base de datos y configuración (se crea al arrancar)
├── Dockerfile               Imagen para Railway u otro hosting con contenedores
└── railway.json             Configuración del despliegue en Railway
```

---

## 10. Actualizaciones

Subir los cambios a la rama `main` de GitHub: Railway compila la imagen y despliega
solo. `railway.json` fija `overlapSeconds: 0`, así que la versión vieja se apaga antes
de que arranque la nueva — necesario porque las dos usarían el mismo archivo SQLite.

El esquema se aplica con `CREATE TABLE IF NOT EXISTS` al arrancar: agregar tablas es
transparente. **Cambiar o eliminar columnas de una tabla existente no migra solo** —
eso hay que resolverlo con un script antes de desplegar.

Bajar un respaldo (§5) antes de cualquier despliegue que toque el esquema.

Si un despliegue queda mal, el *healthcheck* (`/api/salud`) lo detecta y Railway
mantiene arriba la versión anterior. También se puede volver a una versión previa
desde *Deployments → ⋯ → Redeploy*.

---

## 11. Sincronización entre sedes (hoy sin usar)

Con el sistema en la nube y una sola instalación, **esto no se usa**: todos entran al
mismo servidor por navegador. El motor queda apagado por omisión (sin
`HOTEL_SYNC_TOKEN` las rutas responden 404 y el hilo de fondo no arranca), y al
arrancar se podan las filas de `sync_log` de más de 7 días para que la tabla no crezca
sin fin.

Se documenta por si algún día se instala un nodo en el lodge para operar sin internet.
Mantiene sincronizadas dos instalaciones que operan en redes distintas. Se configura en
`data/sync_config.json`:

```json
{ "nombre_estacion": "Sierpe", "peer_url": "http://<ip-o-dominio-de-la-otra-sede>:8000" }
```

Además hay que definir `HOTEL_SYNC_TOKEN` con **el mismo valor en ambas sedes**: sin
esa variable el motor queda apagado y las rutas de sincronización responden 404.

Funciona por diferencias, en segundo plano cada 30 segundos, con resolución
*último cambio gana*. Si una sede está sin conexión, acumula y envía al reconectar.
El hilo de fondo solo se levanta si hay un `peer_url` configurado.

**No usar esto para computadoras de la misma sede** — esas deben apuntar todas al
mismo servidor por navegador.
