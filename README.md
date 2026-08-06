# Sistema de Operación Hotelera — Corcovado Wilderness Lodge

Sistema local para la operación diaria de Sierpe y Drake. Funciona sin internet
(offline-first) y se sincroniza entre las dos estaciones cuando hay conexión.

## Pantallas

| Pantalla | Para qué sirve |
|---|---|
| **Dashboard** | El día de hoy: quién entra, sale y está en casa, tours, alertas y la preparación de mañana |
| **Reservas** | Listado con colores por estado, búsqueda, detalle completo e itinerario de cada huésped |
| **Agenda de tours** | Asignar guía y bote, dividir salidas en grupos, con aviso de conflictos de horario |
| **Transporte** | Entradas y salidas por Sierpe o Drake, con horas de vuelo |
| **Entradas SINAC** | Control de compra con 15 días de anticipación, por urgencia |
| **Amenidades** | Tareas por área (cocina, housekeeping, recepción), incluidas alergias |
| **Analítica** | Uso de botes y guías, movimiento por punto y ocupación del periodo |
| **Resumen operación** | La hoja del día para todos los departamentos |
| **Importar PDF** | Cargar el reporte "Arrivals: Detailed" del PMS |
| **Usuarios** | Crear y administrar accesos |
| **Catálogo** | Guías, botes y tours del hotel |
| **Publicación** | Publicar los itinerarios que ven los huéspedes por código QR |

## Atajos y detalles de uso

- **Buscador** en la barra superior: nombre de huésped o acompañante, número de habitación o de reserva
- `Ctrl+K` buscar · `←` `→` cambiar de día · `Esc` cerrar ventanas
- Botones **Hoy** y **Mañana** en las pantallas con fecha
- Cada pantalla recuerda **su propia fecha**, sin afectar a las demás
- Las tarjetas de totales **despliegan el detalle** al tocarlas y lo ocultan al segundo toque
- Los botones se pintan de azul al tocarlos, y aparece un aviso al guardar

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
al menos 10 caracteres, y la sesión caduca a las 12 horas.


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
| `HOTEL_SESION_HORAS` | horas que dura la sesión (por defecto `12`) | No |

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

- Respaldo automático programado de la base de datos.
- Bloqueo optimista: hoy, si dos personas editan el mismo registro a la vez, gana
  la última que guarda, sin aviso.
- Integración directa con OTAs, facturación, app móvil nativa (fuera de alcance v1).


