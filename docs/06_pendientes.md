# Pendientes, riesgos y trabajo futuro

Estado al 08-10-2026. Ninguna fase nueva se inicia sin orden explícita del usuario, y no se descargan escenas, LUT ni auxiliares sin autorización.

## Pendientes científicos

| Tema | Estado y siguiente paso |
|---|---|
| Productos acuáticos enmascarados | El umbral SWIR nativo enmascara casi todo el AOI ([resultados](05_resultados.md)). Investigar glint y máscara en un experimento separado y trazable, sin relajar umbrales arbitrariamente |
| Datos in situ | Necesarios para aceptar cualquier producto: observaciones coincidentes de clorofila y turbidez con ubicación, hora, profundidad y control de calidad |
| Salida solo oceánica | FAI/NDVI conservan tierra; evaluar `masking.land_water_mask` de ACOLITE (GSHHG/HydroLAKES), con atención a cayos y lagunas. Natural Earth no sirve como máscara a 10 m |

## Riesgos y limitaciones técnicas

| Tema | Detalle |
|---|---|
| RAW retenido tras `SKIPPED` | Si la salida reutilizable se reconoce **después** de descargar, el intento queda `SKIPPED`, conserva el RAW y `cleanup` lo aplaza. Corrección pendiente |
| Completitud USGS | La función nativa pide hasta 1000 resultados y no pagina. El wrapper informa `INCOMPLETE` si hay más: acotar el intervalo |
| Tamaño Landsat | `download-options` de M2M requiere el rol MACHINE (la cuenta recibe HTTP 403). El respaldo lee el HTML de EarthExplorer y puede romperse si USGS cambia la página; es solo informativo |
| Descarga en memoria | CDSE y USGS descargan sin streaming; el pico de RAM incluye el archivo completo |
| Fuente sin checksum comparable | Sin MD5/SHA del proveedor (USGS), decidir si se omite el cálculo exige descargar primero |
| Importación por nombre | `sync` no abre los NetCDF; un nombre engañoso marcaría la adquisición como disponible. Usar `--hash` si los archivos serán evidencia |
| Recursos | Presupuesto de 50 GB supervisado por muestreo, sin cuota instantánea; no se registra qué auxiliares consumió cada escena |
| Reintentos | Esperas fijas de 60 y 300 s; no se interpreta `Retry-After` |
| Respaldo externo | No hay backups automáticos del catálogo ni de `storage/runs`; definir destino y procedimiento |
| Cambio de ACOLITE | Cambiar revisión o parche invalida la reutilización de todas las salidas previas (ver [ACOLITE](02_acolite.md#instalación-y-prepare)) |

## Paralelo: resuelto y pendiente

Resuelto (08-10-2026, [operación](04_operacion.md#paralelo)): una conexión SQLite (WAL) y una copia de `Pipeline` por hilo dentro del mismo comando (`exclusive()` sigue impidiendo dos comandos); el lote reparte la lista de escenas en memoria, sin estado "en proceso" en la cola; reservas de RAM por etapa con la RAM libre del equipo menos una reserva (13-10-2026: antes 70 % fijo); hilos numéricos limitados; barra con un espacio por escena; `scratch` propio por etapa y primer ACOLITE en solitario.

Pendiente:
- **Sin ensayo real.** Probado con dobles y con un proceso aislado real sin red; falta un lote real con descargas para medir la ganancia y confirmar que CDSE/USGS aceptan descargas simultáneas.
- **Descarga en memoria.** La descarga nativa reserva ≈2,6 GB por escena; con streaming propio bajaría a pocos cientos de MB y en 8 GB podría solaparse con ACOLITE. Implica reemplazar la descarga nativa.
- **Presupuesto de disco.** `disk_bytes()` se muestrea cada 2 s por proceso y no reserva espacio; el número de escenas a la vez se limita al inicio con 3,5 GB por escena.
- **Auxiliares del mismo día.** Dos escenas de la misma fecha (varios tiles) descargarían el mismo auxiliar a la vez a `acolite/data`; con un único tile no ocurre.
- **Proveedores.** CDSE/USGS tienen límites de sesión y descarga; los reintentos usan esperas fijas (60 y 300 s) sin `Retry-After`.
- **Identidad compuesta.** `clave_resultado`/`clave_correccion` dependen de la identidad del motor; cualquier cambio del parche ACOLITE invalida la reutilización de todas las salidas previas.
- **Importados sin verificar.** Los 14 L1R/L2W actuales son procesos `IMPORTADO`: evitan descargas repetidas, pero no se reutilizan como padre para regenerar productos. Para eso hay que reprocesar la escena (o validar los archivos y marcarlos `TECNICA_OK`).

## Trabajo futuro (no iniciado)

- **Docker y Airflow (fase 12).** Flujo: catálogo → selección → adquisición → ACOLITE → validación → registro → limpieza. Cada tarea con identificador y estado; reanudar desde resultados válidos; no repetir AC por un fallo de limpieza ni multiplicar reintentos entre Airflow, wrapper y cliente nativo. Persistir solo L1R/L2W y un catálogo. Inventariar dependencias reales (GDAL con JP2OpenJPEG y netCDF, pyproj, pyresample, netCDF4) antes de contenerizar.
- **Cubo temporal (fase 13).** Alimentado por los L2W retenidos, particionado por AOI y versión de grilla, con vínculo a proceso, configuración y fuente; sin mezclar algoritmos o grillas incompatibles y sin borrar NetCDF hasta decidir una política. Es distinto de usar Zarr como entrada de ACOLITE.
- **Nuevos AOI y varios tiles.** Cada AOI necesita su propio análisis; no heredar EPSG, grilla ni algoritmos de `lapargera_v1`. Para varios tiles auditar `merge_tiles`, `merge_full_tiles`, `extend_region`, cruces UTM y proyección. Un L1R recortado no permite ampliar el AOI. Volver a descargar una escena para otro AOI es aceptable.
- **Productos propios (fase 14).** Solo donde ACOLITE no cubra la necesidad.
