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
| `HOTEL_ADMIN_PASSWORD` | — | Contraseña de la cuenta inicial. **Obligatoria en producción** |
| `HOTEL_SESION_HORAS` | `12` | Horas que dura una sesión antes de caducar |
| `HOTEL_SYNC_TOKEN` | — | Secreto compartido entre estaciones. Sin él la sincronización queda apagada |
| `HOTEL_CORS_ORIGINS` | — | Orígenes extra permitidos, separados por coma. Vacío = solo el propio dominio |

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

**Respaldar en caliente** (la base corre en modo WAL, así que copiar el archivo tal
cual puede dejar afuera los últimos cambios — hay que usar el respaldo propio de
SQLite):

```bash
railway ssh "python -c \"import sqlite3; o=sqlite3.connect('/data/hotel.db'); d=sqlite3.connect('/data/respaldo.db'); o.backup(d); d.close(); o.close()\""
railway ssh "base64 /data/respaldo.db" > respaldo.b64
python -c "import base64; open('hotel-respaldo.db','wb').write(base64.b64decode(open('respaldo.b64').read()))"
```

⚠️ **Hoy no hay respaldo automático, y el volumen de Railway no se respalda solo.**
Es el hueco operativo más importante que queda abierto: conviene bajar una copia
semanal y guardarla fuera de Railway.

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

**9. Salida a internet:** el sistema no hace ninguna conexión saliente, salvo que se
configure la sincronización entre estaciones. No depende de ningún servicio externo.

**10. Nada de la carpeta de datos se sube al repositorio** (`.gitignore`): contiene
la base con los datos de huéspedes. Los reportes del PMS en PDF y las hojas de cálculo
también quedan excluidos.

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
│   ├── importer.py          Reglas de negocio de la importación
│   ├── loader.py            Carga a la base
│   ├── validations.py       Capacidades y conflictos de asignación
│   ├── exports.py           Reportes en Excel y PDF
│   ├── itinerario.py        Generación del itinerario del huésped
│   ├── traducciones.py      Catálogo de idiomas
│   ├── qr_huesped.py        Página pública por código QR
│   ├── qr_huesped.py        Página pública por QR y enlaces por habitación
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
