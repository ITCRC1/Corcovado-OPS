# Sistema de Operación Hotelera — Corcovado Wilderness Lodge

Sistema local para la operación diaria de Sierpe y Drake. Funciona sin internet
(offline-first) y se sincroniza entre las dos estaciones cuando hay conexión.

## Pantallas

| Pantalla | Para qué sirve |
|---|---|
| **Dashboard** | El día de hoy: quién entra, sale y está en casa, tours, alertas y la preparación de mañana |
| **Reservas** | Listado con colores por estado, búsqueda, detalle completo e itinerario de cada huésped. Desde el itinerario se le agregan o quitan tours, y quedan cargados en la operación |
| **Agenda de tours** | Asignar guía y bote, dividir salidas en grupos, con aviso de conflictos de horario |
| **Transporte** | Entradas y salidas por Sierpe o Drake, con horas de vuelo |
| **Entradas SINAC** | Control de compra con 15 días de anticipación, por urgencia |
| **Amenidades** | Tareas por área (cocina, housekeeping, recepción…), incluidas alergias. Cada una con su día, su descripción editable y **varios departamentos**, donde cada uno marca su parte |
| **Analítica** | Uso de botes y guías, movimiento por punto y ocupación del periodo |
| **Resumen operación** | La hoja del día para todos los departamentos |
| **Importar PDF** | Cargar el reporte "Arrivals: Detailed" del PMS |
| **Usuarios** | Crear y administrar accesos |
| **Catálogo** | Guías, botes y tours del hotel. Se pueden corregir sin tener que crear uno nuevo |
| **Publicación** | Publicar los itinerarios que ven los huéspedes por código QR |

## Atajos y detalles de uso

- **Buscador** en la barra superior: nombre de huésped o acompañante, número de habitación o de reserva
- `Ctrl+K` buscar · `←` `→` cambiar de día · `Esc` cerrar ventanas
- Botones **Hoy** y **Mañana** en las pantallas con fecha
- Cada pantalla recuerda **su propia fecha**, sin afectar a las demás
- Las tarjetas de totales **despliegan el detalle** al tocarlas y lo ocultan al segundo toque
- Los botones se pintan de azul al tocarlos, y aparece un aviso al guardar

## Agregar un tour que no venía en el reporte

Cuando el huésped decide un tour ya estando en el lodge, se agrega **desde su
itinerario**: Reservas → botón del itinerario → *Tours de la reserva* → **+ Agregar
tour**. La fecha solo admite días de la estadía.

No es una fila de texto: el tour queda **cargado en la operación**. Aparece en la
Agenda del día, cuenta para la capacidad de guía y de bote (con las mismas alertas que
los del reporte), sale en el Resumen de operación y en el Dashboard, entra en los
reportes de Excel y PDF, y el huésped lo ve al escanear su código QR. Si el tour
necesita entrada al parque, **se crea sola** y avisa si el plazo de 15 días ya pasó.

Antes esto no existía: un tour escrito a mano en el itinerario era solo texto. El
huésped lo tenía prometido y la operación no se enteraba — sin guía, sin bote y sin
entrada—, y se descubría el día del tour.

El botón **Quitar** deshace todo: el tour sale de la operación y la entrada del parque
se recalcula. Si esa entrada ya estaba comprada no se borra, se avisa para gestionarla.
Y si el itinerario fue editado a mano, el sistema no borra filas por su cuenta: avisa
para que recepción revise cuál corresponde.

## Un requerimiento con varios departamentos

Al agregar un requerimiento, en **¿A qué departamentos le toca?** se marcan **varios** con
casillas, y hay un campo para escribir uno que no esté en la lista. El que se escriba
queda disponible para todos la próxima vez.

El requerimiento aparece en la lista de **cada** departamento, y **cada uno marca su
parte**: cocina puede cerrar la suya y sigue pendiente para housekeeping hasta que ellos
cierren la suya. En la fila se ve cómo va el resto (*"también: Housekeeping ·pendiente"*),
para que nadie dé por cerrado algo que otra área no hizo. El requerimiento cuenta como
hecho solo cuando lo marcaron todos.

Con el botón **Deptos.** se cambian los departamentos de un requerimiento ya creado. Lo
que ya esté hecho no se reabre; si se quita un departamento, su marca se va con él.

Antes solo se podía elegir uno, y por eso el catálogo llegó a tener etiquetas compuestas
como *"Gerencia/Recepción"*. Esas creaban un grupo propio en la pantalla, así que la tarea
no le aparecía en su lista a ninguna de las dos áreas.

El **resumen del día sigue igual**: la hoja de cocina con sus restricciones y la de
housekeeping con la columna Área, que ahora nombra todos los departamentos. Y una alergia
asignada a cocina más otra área **sigue saliendo en la hoja de cocina**.

## Las cenas privadas se fechan en un solo sitio

La noche de una cena privada se pone en **Amenidades**, en la columna «Para el día».

La pantalla de **Restaurantes** las **muestra**: habitación, huésped, pax y detalle de las
que hay esa noche, si ya están preparadas, y las contratadas a las que todavía nadie les
puso noche. Ya no se elige la noche desde ahí — era el mismo dato con dos puertas, y una
de las dos siempre se quedaba atrás.

Si una cena privada quedó puesta en la **noche de salida**, la pantalla lo advierte: ese
día el huésped desayuna y se va, así que no ocupa mesa en Bar el Bosque.

## Corregir una amenidad

En **Amenidades**, cada fila tiene el botón **Editar** en la columna de la tarea. Se
corrigen dos cosas:

- **Detalle** — lo particular de este huésped: *"sin gluten y sin mariscos"*.
- **Tarea** — la instrucción que lee el área: *"AVISAR A COCINA antes del check-in"*.

Sirve para cuando el huésped llama y cambia lo pedido. Antes había que agregar un
requerimiento nuevo al lado, y quedaban dos filas diciendo cosas distintas de lo mismo.

El **nombre** de la amenidad (la etiqueta azul) no se edita a propósito: es lo que el
sistema usa para reconocer una cena privada y para no perder lo corregido al reimportar.
Si de verdad es otra cosa, se desactiva esta y se agrega la correcta.

Una amenidad tocada a mano queda con una marca ✎.

## Lo hecho a mano NO se pierde al reimportar el PDF

Reimportar el reporte de una reserva **borra y rehace** sus amenidades y sus tours. Esto
se conserva:

| Trabajo hecho a mano | ¿Sobrevive? |
|---|---|
| El día que se le puso a una amenidad (la noche de la cena privada) | sí |
| El detalle y la tarea corregidos | sí |
| Los departamentos asignados a mano, con lo que cada uno ya marcó | sí |
| Las amenidades ya marcadas como hechas | sí |
| Los requerimientos agregados a mano | sí |
| Los tours agregados desde el itinerario | sí |
| Guía, bote y grupo asignados a un tour | sí |

Si el reporte nuevo trae un tour que ya se había agregado a mano, **no se duplica**: pasa
a contarse como del reporte.

Lo que el reporte **sí** vuelve a escribir son los datos de la reserva (fechas, pax,
habitación, vuelos): ahí manda el PMS.

## Corregir el catálogo

En **Catálogo**, cada guía, bote y tour tiene el botón **Editar** en su fila. Antes solo
se podía crear y desactivar, así que para cambiar la capacidad de un bote o arreglar un
nombre había que desactivar el viejo y crear uno nuevo — y eso parte la historia en dos:
los tours ya asignados siguen apuntando al viejo, y la Analítica cuenta al mismo guía
como dos personas.

**Renombrar arrastra todo lo que apuntaba al nombre viejo**: los tours asignados, las
entradas del SINAC, los guías sugeridos en las reservas y los tours privados que usaban
ese código como base. Al guardar, el sistema dice cuántos registros movió.

Dos campos del tour pesan más que los demás:

- **Entrada SINAC** — es la marca por la que el sistema crea sola la entrada al parque
  cuando el tour se agrega a una reserva. Marcarla aquí alcanza; no hay que tocar código.
- **Máx. pax/guía** — es el número con que la Agenda avisa de sobrecupo.

## Al actualizar a una versión nueva

Con el sistema en Railway, actualizar es **subir los cambios a GitHub**: Railway
compila y despliega solo. Los datos no se tocan, porque viven en el volumen montado
en `/data`, aparte del programa.

Antes de un cambio grande (o del primer despliegue de una versión con cambios de
esquema), **descarga un respaldo** de la base — ver *"Respaldos"* más abajo.

## Dónde corre

El sistema vive **en la nube (Railway)**. El personal entra desde el navegador, con
la dirección del hotel, sin instalar nada. Ver *"Publicar en internet con Railway"*
más abajo.

Para **probar cambios en una computadora** antes de subirlos:

1. Instalar Python de https://python.org (marcar "Add Python to PATH")
2. En una terminal dentro de esta carpeta, una sola vez:
   ```
   pip install -r requirements.txt
   ```
3. Doble clic en `iniciar.bat`, o desde `backend/`:
   ```
   py launcher.py
   ```
4. Abre **http://localhost:8000**

Esa copia local usa su propia base de datos (`data/hotel.db`) y no toca la de
producción.

## Usuarios y permisos

El sistema pide iniciar sesión.

| Rol | Permisos |
|---|---|
| Recepción | Lectura y escritura + administrar usuarios |
| Gerencia | Lectura y escritura (no administra usuarios) |
| Staff de campo | Solo lectura (resúmenes del día) |

**Primera cuenta.** Depende de dónde corra el sistema:

- **En la nube o en un servidor** (Railway, o con `HOTEL_ENTORNO=produccion`):
  hay que definir `HOTEL_ADMIN_PASSWORD` — con eso se crea la cuenta de recepción
  inicial (`HOTEL_ADMIN_USER`, por defecto `recepcion`). Si no se define, el
  sistema **no arranca** y avisa por qué.
- **En una computadora del lodge, para probar:** se crean solos tres usuarios de
  demostración (`recepcion`/`recepcion2026`, `gerencia`/`gerencia2026`,
  `staff`/`staff2026`). ⚠️ Son contraseñas públicas: cámbialas antes de meter datos
  reales.

Para agregar, desactivar o cambiar la contraseña de un usuario, entra con una
cuenta de **Recepción** y usa la pantalla **"Usuarios"** dentro del sistema —
no hace falta tocar la base de datos directamente. Las contraseñas deben tener
al menos 10 caracteres.

**La sesión no caduca, salvo que se pida.** De fábrica, quien inicia sesión queda
dentro hasta que aprieta "salir" — así ha funcionado siempre. Para ponerle vencimiento
se define `HOTEL_SESION_HORAS` en el servidor (por ejemplo `12`), y a partir de ahí una
sesión más vieja que ese plazo deja de servir y hay que volver a entrar.

Viene apagado a propósito: encenderlo cierra la sesión a quien esté a media tarea, y el
plazo hay que elegirlo pensando en el turno. Un turno de recepción de 6 a 18 no aguanta
un vencimiento de 8 horas.

Con el vencimiento apagado, si un celular se pierde con la sesión abierta la forma de
cortar el acceso es **desactivar ese usuario** desde la pantalla Usuarios.


## El día de cada amenidad

Cada amenidad lleva el día en que hay que tenerla lista, y se puede cambiar desde la
pantalla **Amenidades** con el selector de la columna *"Para el día"*. Solo se aceptan
días dentro de la estadía del huésped: una tarea puesta en un día en que no está no le
aparecería a nadie.

- **Se pone sola en el día de llegada**, tanto al importar el PDF como al agregar un
  requerimiento a mano. El sofá cama, la cuna, la decoración y la canasta de frutas
  tienen que estar antes del check-in.
- **La cena privada es la excepción y se deja sin día a propósito.** El reporte avisa que
  existe pero casi nunca dice qué noche. Ponerle la llegada sería inventarlo, y apagaría
  el aviso de *"contratadas sin noche asignada"* que es lo que hace que recepción
  pregunte.

**Al ponerle la noche a una cena privada, aparece sola en la hoja de Restaurantes** de
esa noche, fija en Bar el Bosque y contando para sus 45 lugares. Es el mismo dato, así
que no hay nada que sincronizar.

**Las cenas privadas se registran en Amenidades**, con el resto de requerimientos del
huésped. En Restaurantes ya no hay botón para crearlas —era una segunda puerta a lo
mismo, y dos puertas es como se separan los datos—, pero sí queda el botón
*"Elegir noche"* para asignarle el día a una que vino sin él: ese problema se nota en el
comedor y ahí tiene que poder resolverse.


## Alergias en la pantalla de Restaurantes

La pantalla de Restaurantes tiene una tarjeta **Alergias** (junto a Full board) con las
restricciones alimentarias de **todo el que come esa noche**. Se resalta en ámbar cuando
hay alguna.

Se muestran **por estadía, no por fecha**: una alergia no es de un día. Si se filtrara
por la fecha de la amenidad aparecería solo el día que el huésped llega, que es justo
cuando menos falta hace — la cocina necesita saberla **cada noche** que esa persona se
sienta a comer. Quien sale ese día no aparece: el bote va de madrugada.

El reconocimiento es **deliberadamente generoso**: busca palabras de alergia, dieta e
intolerancia en el nombre, la tarea y el detalle, en español y en inglés. Así entra
también la que recepción anotó como *"Preferencia del huésped"* con
*"alérgico a mariscos"* en el detalle. La razón: una alergia que no se muestra puede
mandar a alguien al hospital; una fila de más solo estorba un poco.

La cena privada queda fuera aunque sea de cocina — tiene su propio sitio en la pantalla,
y mezclarlas escondería lo que ahí importa. Las alergias solo se **consultan** desde
Restaurantes; se anotan en Amenidades.


## Avisos al celular

El personal puede recibir una notificación en el teléfono cuando aparece un requerimiento
nuevo, como cualquier otra app.

**No hay nada que configurar en el servidor.** El sistema se genera las llaves solo la
primera vez que arranca y las guarda en `data/llaves_avisos.json` (en Railway, dentro del
volumen). Si `HOTEL_PUSH_PRIVADA` y `HOTEL_PUSH_PUBLICA` están puestas como variables,
esas mandan — sirve para usar las mismas llaves en dos instalaciones o para rotarlas.

⚠️ **Las llaves viven en la carpeta de datos.** Si se borran, todos los teléfonos dejan
de recibir y cada persona tiene que volver a activarlos. Es el mismo sitio donde viven
las suscripciones, así que se pierden juntas o no se pierden.

### Los dos requisitos que hay que entender

**1. Hace falta `https`.** El navegador solo entrega notificaciones por conexión segura.

| Cómo se abre el sistema | ¿Llegan avisos? |
|---|---|
| `https://…` (la dirección de internet del hotel) | **sí**, al teléfono y a la computadora |
| `http://localhost:8000` en la propia computadora | sí, pero solo en **esa computadora** |
| `http://192.168.x.x:8000` desde el teléfono | **no.** El navegador no registra nada |

Por eso **no se pueden probar en el teléfono contra una computadora del lodge**: hace
falta que el sistema esté publicado. La pantalla lo dice cuando la dirección no sirve, en
vez de dejar un botón que no puede funcionar.

**2. En iPhone la app tiene que estar en la pantalla de inicio.** En una pestaña de
Safari, Apple no entrega notificaciones y no hay forma de evitarlo. En Safari: botón de
compartir → *Agregar a inicio*, y abrir el sistema desde ese icono. En Android funcionan
también desde el navegador. La pantalla lo dice cuando detecta ese caso.

### Cómo se activan, paso a paso

1. Abrir el sistema por su **dirección de internet** (`https://…`) e iniciar sesión.
2. En iPhone: **agregar a la pantalla de inicio** y abrirlo desde ese icono.
3. Ir a **Amenidades** → **Activar en este aparato** → aceptar el permiso que pide el
   navegador.
4. Tocar **Probar**: debe llegar una notificación en ese momento. Si no llega, la pantalla
   dice qué falló.

Se activa **por aparato**: cada persona lo hace en su propio teléfono. Activarlo en uno no
lo activa en los demás.

**Qué avisa, y a quién:**

| Cuándo | Qué manda |
|---|---|
| Alguien agrega un requerimiento a mano | Un aviso, a todos menos a quien lo escribió |
| Se importa el reporte del PMS | **Un solo aviso** con el total pendiente para hoy y mañana |
| Cada mañana (6:00 por defecto, `HOTEL_PUSH_HORA_REPASO`) | El repaso de lo pendiente para hoy |

Le llegan a **todo el personal activo**, sin mirar permisos: los de solo lectura y
también quien no tenga la pantalla de Amenidades. En un equipo pequeño, quien tiene que
preparar algo tiene que enterarse, tenga o no ese botón en el sistema. Solo se excluye a
quien hizo el cambio (nadie recibe aviso de lo que acaba de escribir) y a los usuarios
**desactivados**.

Los permisos siguen mandando en lo que cada quien puede ver y hacer dentro del sistema.
Lo que no gobiernan es a quién le suena el teléfono.

Dos consecuencias que conviene tener claras:

- **El texto del aviso lleva datos del huésped** (*"Hab. 12 · Restricción alimentaria"*,
  que además es dato de salud), así que ese texto lo lee todo el personal.
- Si alguien sin acceso a Amenidades toca el aviso, **la app no lo lleva ahí**: le dice
  que esa pantalla no es para su usuario. Sin eso vería una pantalla en blanco y parecería
  que el sistema falla, cuando es su permiso.

Para volver a limitarlo por permisos, se cambia una sola función:
`destinatarios_amenidades()` en `backend/notificaciones.py`.

Del reporte del PMS sale **un aviso, no uno por amenidad**: treinta notificaciones
seguidas hacen que la persona silencie la app el primer día, y entonces tampoco recibiría
la que sí importaba.

Sin señal el aviso no se pierde: se queda en cola en los servidores de Google o Apple y
entra cuando el teléfono vuelve a tener datos.


## Reportes descargables (Excel y PDF)

Reservas, Agenda de tours, Transporte, Entradas SINAC, Analítica y Resumen de
Operación tienen botones **⬇ Excel** y **⬇ PDF** para descargar el reporte tal
como se está viendo en pantalla (con los mismos filtros de fecha aplicados),
con la marca del hotel incluida.


## Publicar en internet con Railway

Se hace **una sola vez**. Después, cada cambio que se suba a GitHub se despliega solo.

### 1. Subir el código a GitHub

Crea un repositorio **privado** (el código no contiene contraseñas, pero no hay razón
para hacerlo público) y sube esta carpeta. La carpeta `data/` no se sube: está
excluida a propósito porque contiene datos de huéspedes.

### 2. Crear el proyecto en Railway

En **railway.app** → *New Project* → *Deploy from GitHub repo* → elige el repositorio.
Railway detecta el `Dockerfile` solo. **El primer despliegue va a fallar** — es lo
esperado: todavía falta la contraseña del paso 4.

### 3. Crear el volumen  ⚠️ antes de nada más

Servicio → pestaña *Variables* → botón *+ New Volume* (o *Settings → Volumes*), con
punto de montaje exactamente:

```
/data
```

**Sin este volumen se pierden todas las reservas en cada despliegue**, porque el disco
del contenedor se borra al reiniciar. Es el error más caro que se puede cometer aquí,
y no da ningún aviso: simplemente un día el sistema aparece vacío.

### 4. Definir las variables de entorno

Servicio → *Variables*:

| Variable | Valor | ¿Obligatoria? |
|---|---|---|
| `HOTEL_ADMIN_PASSWORD` | contraseña de la primera cuenta (mínimo 10 caracteres) | **Sí** |
| `HOTEL_ADMIN_USER` | nombre de esa cuenta (por defecto `recepcion`) | No |
| `HOTEL_SESION_HORAS` | horas que dura la sesión. Sin definir, **no vence** | No |
| `HOTEL_PUSH_PRIVADA` · `HOTEL_PUSH_PUBLICA` | llaves de los avisos. Sin ellas el sistema las genera y las guarda en el volumen | No |
| `HOTEL_PUSH_CONTACTO` | correo de contacto que piden Google y Apple | No |
| `HOTEL_PUSH_HORA_REPASO` | hora del repaso diario (por defecto `6`) | No |
| `HOTEL_PORTAL_TOKEN` | secreto para el portal del huésped. Sin él, esa puerta no existe | No |

`PORT` y `HOTEL_DATA_DIR` los ponen Railway y el `Dockerfile`: no hay que tocarlos.

Si `HOTEL_ADMIN_PASSWORD` falta, el sistema **no arranca** y lo dice en el log. Es a
propósito: sin ella tendría que crear usuarios de prueba con contraseñas públicas.

### 5. Abrirlo

*Settings → Networking → Generate Domain*. Entra con la cuenta del paso 4 y **cámbiale
la contraseña desde la pantalla Usuarios** — así deja de estar guardada en Railway.

### 6. Apuntar los códigos QR

En la pantalla **Publicación**, pon ese dominio como dirección base para que los QR de
las habitaciones apunten al lugar correcto.

### Por qué una sola réplica

Todo se guarda en SQLite, en un solo archivo dentro del volumen. `railway.json` ya fija
`numReplicas: 1` y `overlapSeconds: 0` (que la versión vieja se apague antes de que
arranque la nueva). **No subas ese número:** dos réplicas escribiendo el mismo archivo
corrompen la base. Si algún día el sistema necesita crecer, el cambio correcto es pasar
a PostgreSQL, no agregar réplicas.


## Respaldos

Toda la operación vive en un solo archivo (`/data/hotel.db` en el volumen de
Railway). **No hay respaldo automático**: conviene bajar una copia cada semana y
antes de cualquier cambio grande.

Con la [CLI de Railway](https://docs.railway.com/guides/cli) instalada y sesión
iniciada (`railway login`, `railway link`), son dos pasos:

```bash
# 1. Crear dentro del servidor una copia consistente de la base
railway ssh "python -c \"import sqlite3; o=sqlite3.connect('/data/hotel.db'); d=sqlite3.connect('/data/respaldo.db'); o.backup(d); d.close(); o.close()\""

# 2. Bajarla (en texto, para que no se corrompa al viajar) y reconstruirla
railway ssh "base64 /data/respaldo.db" > respaldo.b64
python -c "import base64; open('hotel-respaldo.db','wb').write(base64.b64decode(open('respaldo.b64').read()))"
```

El paso 1 usa el respaldo propio de SQLite en vez de copiar el archivo: la base corre
en modo WAL, y copiarla en caliente puede dejar afuera los últimos cambios.

Guarda `hotel-respaldo.db` fuera de Railway (Drive, disco externo). Para restaurarlo,
súbelo de vuelta al volumen como `/data/hotel.db` y reinicia el servicio.

## Estructura del proyecto

```
Corcovado-OPS/
├── backend/
│   ├── schema.sql             Esquema de base de datos + triggers de sincronización
│   ├── init_db.py             Crea la BD y carga el catálogo de reglas
│   ├── auth.py                Sesiones, roles y contraseñas
│   ├── pdf_parser.py          Extrae texto estructurado del PDF de reservas
│   ├── importer.py            Aplica reglas de vinculación y entradas SINAC
│   ├── loader.py              Inserta los datos importados en la BD
│   ├── validations.py         Valida capacidad de botes/guías, genera alertas
│   ├── exports.py             Reportes en Excel y PDF
│   ├── itinerario.py          Arma el itinerario del huésped
│   ├── traducciones.py        Catálogo de idiomas
│   ├── qr_huesped.py          Página pública del QR y hoja imprimible
│   ├── qr_huesped.py          Página pública del QR, enlaces y hoja imprimible
│   ├── sync_engine.py         Motor de sincronización Sierpe ↔ Drake
│   ├── launcher.py            Punto de entrada (arranca todo)
│   └── main.py                API (FastAPI)
├── frontend/
│   ├── index.html             Todas las pantallas del sistema
│   └── assets/                Logo, tipografías e imágenes
├── data/                      Base de datos y configuración (se crea al iniciar;
│                              nunca se sube al repositorio)
├── Dockerfile                 Imagen para Railway u otro hosting
├── railway.json               Configuración del despliegue en Railway
├── requirements.txt
└── iniciar.bat                Arranque con doble clic (modo desarrollo, con Python)
```

## Para cargar un nuevo PDF de reservas

Desde la pantalla **Importar PDF**: se elige el archivo "Arrivals: Detailed" del PMS,
se revisa la vista previa y se confirma.

## Qué falta (siguientes pasos del proyecto)

- **Decidir el plazo de sesión.** El vencimiento ya está implementado y apagado
  (`HOTEL_SESION_HORAS`). Lo que falta es la decisión del hotel: cuántas horas, mirando
  los turnos de recepción. Mientras esté apagado, los tokens no vencen.
- **Purga del registro de sincronización.** La tabla `sync_log` anota cada cambio y no
  se vacía nunca. Ya no hace lento el sistema (tiene índice) y el espacio no aprieta
  —unos 80 bytes por fila—, así que no es urgente. Y hay que hacerlo con cuidado: esa
  tabla es también el reloj que usa `sync_engine` para resolver conflictos entre Sierpe
  y Drake (`MAX(creado_en)` por registro), así que borrar historia vieja cambiaría quién
  gana un conflicto si algún día se enciende la sincronización.
- Respaldo automático programado de la base de datos.
- Bloqueo optimista: hoy, si dos personas editan el mismo registro a la vez, gana
  la última que guarda, sin aviso.
- Integración directa con OTAs, facturación, app móvil nativa (fuera de alcance v1).


