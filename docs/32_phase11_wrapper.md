# Fase 11 — wrapper mínimo y catálogo operativo

Estado al 30 de septiembre de 2026: implementado y verificado técnicamente en WSL Ubuntu. La aceptación científica sigue pendiente. Fase 12 no iniciada. Rige la [política L1R/L2W y reinicio](33_retention_and_reset.md).

## Comportamiento actual

La interfaz `python -m oceanos` interpreta los perfiles y delega consulta, descarga, extracción y procesamiento en ACOLITE. El arranque es manual y la ejecución secuencial. Sentinel-2 usa actualmente [2026-08-01,2026-08-15) UTC; Landsat conserva [2026-08-01,2026-08-21). Ambos tienen la nubosidad del catálogo desactivada.

SQLite, esquema v2, contiene consultas, versiones de producto, observaciones, ejecuciones, artefactos y eventos. Los snapshots JSON viven dentro de la base. Se registran hashes, configuración, metadata científica seleccionada y métricas breves; no hay manifiestos ni backups por comando.

Las llamadas nativas se aíslan en procesos. El supervisor limita el tiempo y revisa el presupuesto compartido de 50 GB cada dos segundos; registra duración y RSS informados por el worker. El bloqueo de escritor evita operaciones concurrentes sobre el mismo catálogo. `recover` marca intentos abandonados como interrumpidos y conserva sus fuentes.

`status` consulta solo SQLite. Sin argumentos lista las ejecuciones con escena, estado, validación, limpieza, error y ruta/disponibilidad del L2W; `--estado` y `--ultimas N` filtran. Con un id o prefijo único (`status 38d623c4`) muestra el detalle: claves de procesamiento y corrección, padre L1R, métricas por etapa, artefactos con hash y la línea de eventos. Se agregó el 01-10-2026 (`Catalog.runs` y `Catalog.run_detail`).

La idempotencia compara contenido, configuración y revisión efectiva del procesador, y verifica los archivos disponibles. Un checksum remoto comparable permite recuperar el SHA local comprobado. Sin esa evidencia —habitual en USGS— puede necesitar descargar antes de decidir. SAFE y Zarr sin equivalencia demostrada mantienen identidades distintas.

Se busca **L1R** compatible antes de adquirir de nuevo cuando hay identidad comprobada. La regeneración ejecuta L1R → AC → L2R temporal → L2W, registra el padre y verifica grilla, EPSG, productos y flags. Un L1R registrado se referencia sin copiarlo; una fuente externa se copia al espacio propio. En Landsat no se reproyecta de nuevo el L1R retenido.

Después de verificar y registrar L1R/L2W se retiran L2R y archivos duplicados, y se evalúa la limpieza del RAW propio. La validación técnica permite esa limpieza aunque la aceptación científica siga pendiente. Fuentes externas, AOI y credenciales no se eliminan automáticamente.

## Adaptación nativa delimitada

El [parche](../patches/acolite-catalog.patch) añade retorno opcional de metadata CDSE, detección de respuestas inválidas, timeout de consultas CDSE y detección de error explícito USGS. El bloque STAC se quitó el 01-10-2026 al retirar Zarr ([documento 34](34_acolite_installation.md#huella-vigente-01-10-2026)). El retorno CDSE por defecto sigue compatible. No se implementa otro cliente satelital.

`prepare` comprueba el commit fijado y aplica el parche a la instalación ACOLITE configurada (desde el 01-10-2026, `/home/antho/acolite`; antes, la copia `.work/acolite-audit`; ver [documento 34](34_acolite_installation.md)). Se registra commit, SHA del parche y hash del diff efectivo. La paginación USGS continúa siendo una limitación nativa; su completitud se marca desconocida.

## Pruebas y evidencia histórica

La suite actual contiene **27 pruebas**: consulta de estado, snapshots, duplicados, cambios de contenido, idempotencia, reutilización L1R, regeneración sin reproyección, fechas, productos, integridad, exclusión mutua, interrupción, retención, reintentos y QA técnico. No reproduce algoritmos científicos. Las 22 pruebas del cierre original precedían al cambio de conservación; no son el recuento vigente.

En los ensayos previos se consultaron cinco escenas CDSE, tres Landsat elegibles USGS y cero candidatos STAC. La implementación inicial probó derivación desde L2R; posteriormente se verificó la cadena desde L1R con Sentinel-2 y Landsat, con igualdad de variables bidimensionales L2W bajo las condiciones documentadas. El comando vigente es `derive --l1r`, no `--l2r`.

El inventario de 30,65 GB informado en el cierre original es histórico. El reinicio autorizado retiró las escenas y consolidó su trazabilidad en SQLite; no quedan esos NetCDF para reutilizarlos. Los ensayos antiguos no se convierten automáticamente en ciencia aprobada.

## Límites y continuación

- La validación científica, los datos in situ y la salida exclusivamente oceánica siguen pendientes. No se relajan máscaras. NDCI solo Sentinel-2; OC4 excluido.
- Zarr remoto se retiró del wrapper el 01-10-2026 por falta de cobertura EOPF; Sentinel-2 se adquiere solo como SAFE desde CDSE (documento 06). Los reintentos de consulta y adquisición se prueban con simulaciones.
- Se supervisa disco por muestreo; no hay cuota instantánea ni inventario exhaustivo de LUT/auxiliares consumidos por escena. Las esperas de reintento son fijas; no se interpreta `Retry-After`.
- **Fallo conocido sin corregir:** si se detecta una salida reutilizable después de descargar, el intento queda `SKIPPED` y conserva RAW. `cleanup` aplaza ese caso. Reproducido con adquisición simulada durante la revisión local.
- No descargar escenas, LUT, auxiliares ni dependencias sin autorización explícita. `run` y `derive` pueden descargar auxiliares aunque su entrada sea local; el CLI no incorpora un bloqueo de red ni confirmación automática.

Comandos: [README](../README.md). Docker/Airflow requieren una nueva orden.
