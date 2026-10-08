# Operación del wrapper `oceanos`

`python -m oceanos` interpreta el perfil y delega en ACOLITE consulta, descarga, extracción y procesamiento. Arranque manual, una escena a la vez y un único escritor del catálogo. Cada comando tiene ayuda con valores válidos y ejemplos: `oceanos <comando> -h`. Alias y ejemplos rápidos: [README](../README.md).

## Flujo

```text
prepare ─► sync ─► search ─► search --registrar ─► cola ─► run ─► status / sql/consultas.sql
 (una vez)  (opcional)  (solo ver)   (compromete descarga)  (revisar) (procesa la cola)
```

| Comando | Red | Escribe en SQLite | Función |
|---|---|---|---|
| `prepare` | No | No | Verifica la revisión ACOLITE y aplica el parche |
| `sync [CARPETA] [--hash]` | No | Sí | Registra L1R/L2W existentes solo por el nombre |
| `search [--registrar [ESCENA…]] [--json]` | Metadata | Escenas y búsqueda; la cola solo con `--registrar` | Tabla de escenas y explicación de la consulta |
| `cola [--quitar ESCENA…]` | No | Solo con `--quitar` | Ver o retirar escenas de la cola |
| `run` / `run --escena X` / `run --source … --scene …` | Sí | Sí | Procesa la cola (no repite `search`), una escena o un archivo local |
| `derive --l1r … --scene …` | Auxiliares | Sí | Regenera L2W desde L1R |
| `status [N] [--estado E] [--ultimas N]` | No | No | Tabla de procesos o detalle del proceso N |
| `recover`, `cleanup N` | No | Sí | Interrupciones y limpieza de temporales |

Las escenas se nombran por su producto (`S2B_MSIL1C_20260215T150719_…SAFE`); en los comandos basta un fragmento único, por ejemplo `20260215`. Los procesos se numeran 1, 2, 3…

`--sensor {sentinel2,landsat}` elige el perfil (`project.yaml` o `landsat.yaml`). `--satelite` (`S2A,S2B,S2C` o `L8,L9`; acepta minúsculas y `LC08/LC09`) restringe las plataformas. `--start/--end` (`AAAA-MM-DD[THH:MM:SSZ]`, fin excluido) sustituyen el intervalo del YAML. Las cuatro opciones valen antes o después de `search`, `run` y `derive`. Para que `run` procese lo registrado debe usar la misma selección que `search`; lo que queda fuera se conserva `PENDIENTE`.

El CLI valida fechas, productos, sensores, satélites y estados antes de abrir el catálogo y muestra las opciones permitidas; en Python ≥ 3.14 sugiere correcciones (`serch` → `search`). Los errores de validación local se imprimen con su mensaje (código 2); los remotos solo con el tipo de excepción, para no exponer respuestas ni credenciales.

## Estados de una escena (cola)

`search` guarda o actualiza cada escena encontrada, pero **solo `--registrar` compromete una descarga**: sin nombres registra todas las `NUEVA` y `FALLIDA`; con nombres o fragmentos, solo esas. Nunca registra escenas cuya adquisición ya tiene L2W.

| Estado | Significado | Lo toma `run` |
|---|---|---|
| `NUEVA` | Vista en una búsqueda, sin compromiso | No |
| `PENDIENTE` | En la cola (`search --registrar`) | Sí, si cumple la selección vigente |
| `FALLIDA` | Falló el último proceso | Sí (reintento en el próximo `run`) |
| `PROCESADA` | Procesada (`OK`) u omitida por existir un L2W equivalente | No; registrarla de nuevo no la reactiva |
| `DISPONIBLE` | Otra fuente de la misma adquisición ya tiene L2W | No |
| `IMPORTADA` | Sus L1R/L2W se registraron con `sync` | No |

`cola --quitar` devuelve a `NUEVA` una escena pendiente o fallida. `run --escena` procesa esa escena esté o no en la cola. `--force` reprocesa aunque exista L2W. La disponibilidad se decide por **adquisición** (`satélite:día:tile`, columna `adquisicion`) y por región del AOI, comprobando existencia y tamaño del L2W sin recalcular hashes: es lo común entre un producto L1C/L1TP y el nombre de sus salidas ACOLITE.

## Importación por nombre (`sync`)

`sync` registra L1R/L2W existentes sin abrir los NetCDF; interpreta el nombre de salida de ACOLITE:

```text
<sensor>_<AAAA_MM_DD_HH_MM_SS>_<T tile | path+row>[_<región>]_<L1R|L2W>.nc
S2B_MSI_2026_02_15_15_07_58_T19QGV_lapargera_v1_L2W.nc
L9_OLI_2026_08_05_14_57_33_005048_lapargera_v1_L1R.nc
```

- **`storage/importados`** (por defecto, o cualquier subcarpeta de `storage` salvo `catalog` y `temporary`): archivos traídos de otra computadora. Se agrupan L1R/L2W de la misma adquisición y región.
- **`storage/runs`**: cada subcarpeta se adopta como un proceso y se renombra a su nombre legible (`0001_S2C_2026-01-01`), sacando los NetCDF de `output/`. Los procesos adoptados se numeran por fecha de adquisición.

Cada grupo queda como un proceso `IMPORTADO` (validación `SIN_VERIFICAR`, limpieza `NO_APLICA`; SHA-256 solo con `--hash`) y su escena como `IMPORTADA`. La escena es la del proveedor con la misma adquisición; si aún no existe, se crea una `LOCAL` (p. ej. `S2C_20260101_19QGV`) que se unifica sola con la escena real cuando una búsqueda la encuentra. Los importados **nunca** se reutilizan como L1R padre ni como salida omitible y nunca se borran. `sync` es idempotente: omite lo registrado, marca `FALTAN` los procesos cuyos archivos desaparecieron y los devuelve a `PRESENTES` cuando vuelven con el mismo tamaño. El instante del nombre es el de sensado del gránulo, distinto del instante del producto L1C; por eso la relación se hace por día.

## Información de `search`

La tabla muestra fecha y hora UTC, satélite, tile o path/row, tamaño L1, nubosidad, estado y nombre de la escena, seguida de totales y de una explicación de la consulta.

| Dato | Sentinel-2 (CDSE) | Landsat (USGS) |
|---|---|---|
| Fecha y hora | `ContentDate.Start` | `Start Time` de la metadata de escena |
| Tamaño L1 | `ContentLength` del SAFE (exacto; además verifica la descarga) | `filesize` del Product Bundle Level-1: `download-options` de M2M o, si USGS lo rechaza, la página de opciones de EarthExplorer (redondeado a 0,01 MiB). Referencial: no verifica la descarga |
| Nubosidad | Atributo `cloudCover` | `Scene Cloud Cover L1` |
| Completitud | `COMPLETE`: la función nativa sigue `@odata.nextLink` | `totalHits` frente a `recordsReturned` de `scene-search` |
| Descartadas | Motivo por tile, satélite o intervalo | Motivo por path/row, satélite, intervalo o producto no L1TP T1 |

**Completitud.** `COMPLETE`: el proveedor devolvió todas las coincidencias. `INCOMPLETE`: tiene más de las devueltas (la función nativa USGS pide hasta 1000 sin paginar): acotar el intervalo. `UNKNOWN`: no se pudo leer el total o USGS lo informó como aproximado. OCEANOS lee esos contadores envolviendo temporalmente `requests.Session.post` dentro del proceso aislado, **sin modificar ACOLITE**.

**Descartadas por el perfil:** escenas que el proveedor devuelve porque tocan el rectángulo del AOI pero no cumplen el perfil (en La Parguera, USGS devuelve también el path/row **005/047**, vecino del **005/048**). No aparecen en la tabla ni se pueden registrar; quedan con su motivo en `busquedas.descartadas`.

**Tamaño Landsat.** `download-options` de M2M (campos `productName`, `filesize`, `available`) requiere el rol MACHINE; la cuenta actual recibe HTTP 403. El respaldo inicia sesión en EROS, igual que `ac.api.earthexplorer.download`, y lee el botón "Download Product" de la misma página que usa la descarga nativa, sin descargar escenas. Si ninguna vía responde, la tabla muestra "no informado" y `busquedas.tamanos` guarda el motivo. Los campos de M2M se confirmaron en una implementación pública de la API ([callusgs](https://pypi.org/project/callusgs)), porque la referencia oficial requiere sesión.

## Progreso y tiempos

Durante `run` una línea por escena muestra `[i/n]`, la etapa, el porcentaje, los MB, la velocidad y el tiempo restante; sin terminal interactiva se imprime una línea cada 30 s. La descarga nativa CDSE acumula el ZIP en memoria y lo escribe al final, por lo que se miden los bytes leídos por el proceso aislado (`/proc/<pid>/io`, `rchar`) desde una línea base que el worker escribe tras cargar ACOLITE; al superar el tamaño esperado la etapa pasa a verificación de checksum. Extracción y ACOLITE se comparan con la mediana histórica de esa etapa (máximo 99 %).

Cada proceso guarda `descarga_min` (intento exitoso), `descarga_mb` e `intentos` (fallidos + exitoso; cada fallo queda como evento `INTENTO_FALLIDO`). Al terminar, `run` imprime escenas por estado y con reintentos, tiempo total del lote, tiempo, volumen y velocidad de descarga, disco de L1R/L2W generado en ese run y total, y una línea por proceso.

## Ejecución de una escena

1. Se comprueba que la escena cumple el perfil y se crea el proceso `EN_CURSO` con su carpeta `storage/runs/<NNNN>_<satélite>_<fecha>` y su temporal `storage/temporary/<N>`.
2. **Reutilización:** si otro proceso `OK` tiene un L2W verificado con la misma `clave_resultado` (fuente, AOI, settings científicos, grilla, motor y productos), el proceso queda `OMITIDO`. Si hay un L1R con la misma `clave_correccion` (igual, sin productos) se regenera desde él sin descargar (`tipo` `DERIVADO`, `l1r_padre`). Ambas exigen el SHA-256 de la fuente: si el checksum MD5/BLAKE3 de CDSE no cambió, se conserva el SHA comprobado en una descarga anterior; sin esa evidencia (habitual en USGS) primero hay que descargar.
3. **Adquisición:** descarga nativa con hasta 3 intentos (esperas 60 y 300 s), verificación de tamaño y checksums del proveedor y SHA-256 propio, que se guarda en la escena. Si el checksum del proveedor cambia, se descarta el SHA anterior y queda un evento `CONTENIDO_CAMBIADO`.
4. **Extracción** en el temporal, rechazando rutas fuera de la carpeta y enlaces.
5. **Procesamiento** ACOLITE en un proceso aislado que escribe directamente en la carpeta del proceso, con límite de tiempo y control del presupuesto de 50 GB cada 2 s (suma de `storage`, `acolite/data` y `acolite/scratch`).
6. **Validación técnica:** ejes y EPSG de L1R/L2R/L2W, tipo de archivo, `rhot`/`rhos`, `l2_flags` enteros, presencia de cada producto (todas las bandas `Rrs_*`) y fracción de píxeles finitos. Un producto totalmente enmascarado es un éxito técnico con ciencia pendiente.
7. **Registro y limpieza:** se registran L1R y L2W en la fila del proceso, la metadata atmosférica del L2R va a `detalle`, y se borran L2R, settings, RAW y extracción. El proceso queda `OK` / `TECNICA_OK`.

## Retención y limpieza

- Persisten **L1R y L2W** (`storage/runs/<carpeta>/`), el catálogo y los importados. La aceptación científica es independiente de la limpieza técnica.
- `cleanup N` borra temporales si L1R y L2W están verificados, si se agotaron los reintentos de una fuente recuperable o si el proceso fue interrumpido; en otro caso queda `APLAZADA`. Toda ruta se resuelve dentro de la carpeta del proceso. Un fallo de borrado deja `limpieza FALLIDA` sin convertir en fallido un proceso exitoso.
- `recover` (automático al iniciar `search`, `run` y `derive`) marca `INTERRUMPIDO` lo que quedó `EN_CURSO` y limpia sus parciales. Un nuevo `run` vuelve a descargar desde cero.
- Los importados nunca se borran (`cleanup` responde `NO_APLICA`). Nunca se borran fuentes externas, el AOI, credenciales ni productos de otro proceso; los flags de borrado nativo de ACOLITE están desactivados.

## Catálogo SQLite (esquema v4)

`storage/catalog/catalog.sqlite` es el único registro operativo: no hay JSON por etapa, manifiestos, logs de éxito ni backups por comando. Fechas `AAAA-MM-DD HH:MM:SS` UTC, tamaños en MB y tiempos en minutos; los comentarios de cada columna quedan en la base y los muestran los visores (DB Browser for SQLite, `python -m sqlite3`). Un catálogo de versiones anteriores se guarda como `catalog/catalog_vN_respaldo_<fecha>.sqlite` y se empieza uno nuevo.

| Tabla | Una fila por | Columnas principales |
|---|---|---|
| `escenas` | Producto del proveedor (clave: su nombre) | sensor, satélite, `fecha_utc`, tile, proveedor, `tamano_mb`, nubosidad, estado (cola), registrada, vista, `adquisicion`; `fuente` (JSON para descargar y verificar) |
| `procesos` | Descarga/procesamiento o importación (id 1, 2, 3…) | escena, aoi, tipo (`DESCARGA`, `LOCAL`, `DERIVADO`, `IMPORTADO`), estado (`EN_CURSO`, `OK`, `OMITIDO`, `FALLIDO`, `INTERRUMPIDO`, `IMPORTADO`), inicio, fin, `duracion_min`, `descarga_min`, `descarga_mb`, intentos, error, carpeta, `l1r`/`l1r_mb`, `l2w`/`l2w_mb`, archivos, validación, limpieza; al final las claves de reutilización, bytes/SHA-256 y `detalle` (JSON: métricas, QA, ciencia, settings, entorno y perfil) |
| `busquedas` | Intento de `search` | fecha, proveedor, sensor, satélites, desde, hasta, estado, devueltas, cumplen, `total_proveedor`, completitud, tamaños, descartadas (JSON con motivo), error |
| `eventos` | Hecho relevante | fecha, proceso, escena, tipo, mensaje legible |

Vistas: `v_resumen` (cantidades por estado), `v_cola`, `v_descargas` (procesos OK con tiempos y tamaños), `v_fallidas` (escenas sin éxito posterior) y `v_disco` (GB de L1R/L2W propios e importados). [`sql/consultas.sql`](../sql/consultas.sql) agrega reintentos con su motivo, historial por escena, velocidad de descarga, duración por etapa, archivos faltantes, búsquedas con descartes y últimos eventos.

## Pruebas

```bash
/home/antho/.local/bin/micromamba run -p /home/antho/micromamba/envs/acolite python -m unittest discover -s tests -v
```

53 pruebas en `tests/test_wrapper.py`, con dobles para red y ACOLITE y un intervalo fijo propio (agosto de 2026). Cubren: catálogo legible y respaldo del anterior, estados y detalle, contenido cambiado, idempotencia y reutilización L1R, regeneración sin reproyección, fechas, productos, integridad y grilla, exclusión mutua, interrupción y limpieza, reintentos, cola, `sync` (importados, adopción de `runs`, unificación de escenas), tiempos de descarga, progreso, selección por sensor/satélite, validación de argumentos y consulta USGS. No replican algoritmos científicos.
