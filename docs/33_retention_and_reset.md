# Política vigente: L1R/L2W, trazabilidad mínima y reinicio

Esta decisión reemplaza las recomendaciones anteriores de conservar L2R, esperar validación científica para eliminar intermediarios y acumular logs/JSON. Se aplica a todas las fases del plan. No inicia otra fase.

## L1R sí permite regenerar L2W, con condiciones

ACOLITE acepta un L1R completo y ejecuta **L1R → corrección atmosférica → L2R temporal → L2W**. Se conserva L1R en la grilla ya validada, además de L2W. Regenerar ahorra descarga y conversión desde RAW, pero vuelve a calcular AC. L1R no es una entrada directa de `acolite_l2w`.

Antes de la limpieza se comprobó con datos existentes, sin descargar escenas:

| Entrada conservable | Adquisición | Variables bidimensionales L2W comparadas | Resultado |
|---|---|---:|---|
| Sentinel-2C L1R | 19-08-2026 | 19 | Valores idénticos, incluidos flags y patrón de NaN |
| Landsat 9 L1R ya proyectado | 17-08-2026 | 16 | Valores idénticos, incluidos flags y patrón de NaN |

La grilla también pasó QA. No se compara el archivo NetCDF byte a byte: timestamps y otras metadata de generación cambian. La igualdad comprobada corresponde a las bandas y condiciones de aquel ensayo. Hacen falta bandas TOA, geometría, settings, revisión ACOLITE y auxiliares compatibles; si cambia cualquiera, no se garantiza igualdad. Un L1R recortado no amplía el AOI ni recupera bandas ausentes. Para Landsat no se repite la reproyección del L1R retenido.

## Qué queda en una ejecución futura

- **L1R y L2W** como únicos archivos científicos persistentes. Un L1R padre se referencia sin duplicarlo.
- **SQLite** con identidad/checksum de fuente, configuración, versión del procesador, artefactos/hashes, metadata atmosférica seleccionada, QA y métricas/error breves.
- Código, perfil y AOI bajo control de versiones.

L2R, RAW, extracción, logs y settings redundantes se eliminan después de verificar y registrar L1R/L2W. No se espera aceptación científica para quitar intermediarios reproducibles; la aceptación científica sigue pendiente y separada. Los JSON de transporte del proceso se crean en un temporal y desaparecen al cerrar la etapa. No hay manifiestos, JSON de provenance/validación ni backups por comando. Tampoco se vuelve a calcular y guardar el inventario completo de auxiliares en cada ejecución.

## Historial

La trazabilidad útil de los ensayos anteriores se consolidó en `storage/catalog/catalog.sqlite`, esquema v2. Incluye resultados de las ocho adquisiciones manuales, diagnósticos de radiometría/flags/glint, ejecuciones del wrapper, regeneración desde L1R y referencias de hashes de la caché retirada. El inventario de caché es contexto disponible, no una afirmación de qué archivos usó cada escena.

Todos los artefactos de prueba eliminados están marcados **DELETED** y las ejecuciones como `DELETED_BY_USER_RESET` en su estado de limpieza. No se omitirán futuros procesos por estos archivos ausentes. Los informes de fases previas conservan sus cifras históricas; sus archivos de evidencia detallada ya no están disponibles como JSON independientes. Se mantienen únicamente las dos figuras científicas útiles (cobertura del AOI y diagnóstico de enmascarado).

El catálogo no reconstruye todos los cuerpos HTTP ni logs antiguos: se descartó información redundante o regenerable. Las credenciales permanecen fuera del catálogo.

## Limpieza realizada por orden del usuario

Se retiraron **31 541 779 581 bytes (31,54 GB decimales)** de datos/registros de ensayo:

- `.work/phase6_20260804` y `.work/phase10`, con RAW y todos sus NetCDF de prueba.
- `storage/runs`, `storage/temporary` y `storage/queries`, incluidos los NetCDF usados en esta verificación.
- Cachés descargadas `.work/acolite-audit/data/LUT` y `data/MET`.
- 131 archivos sueltos de evidencia duplicada, scripts manuales de ensayo y respaldo automático anterior.

Se comprobaron las rutas absolutas dentro del proyecto antes de eliminar. Se preservaron AOI original, perfiles, código, parche, tests, instalación/copias de código ACOLITE y credenciales. La copia auditada puede necesitar reconstruir o descargar cachés para una nueva ejecución. Cualquier descarga de escenas, LUT, auxiliares o dependencias requiere autorización explícita; no ejecutar procesamiento local suponiendo que no usa red. No se promete que Windows recupere inmediatamente el tamaño físico del VHDX de WSL: los archivos sí se eliminaron del filesystem Linux.

## Continuación paso a paso

La revisión local del 30-09-2026 confirma SQLite v2, 14 ejecuciones con limpieza `DELETED_BY_USER_RESET` y 33 artefactos `DELETED` (11 L1R, 10 L2R y 12 L2W). No hay archivos en los directorios de escenas revisados. El catálogo conserva historia, pero ya no hay escenas de prueba disponibles. El siguiente uso puede comenzar con `search` y después `run --version ID` para una sola escena, cuando el usuario lo indique. Para regenerar se usa `derive --l1r RUTA --scene NOMBRE`, no `--l2r`; puede necesitar descargar auxiliares y requiere autorización para ello. El CLI no incorpora un bloqueo de red.

El perfil Sentinel-2 actual usa [2026-08-01,2026-08-15) UTC; Landsat conserva [2026-08-01,2026-08-21). Las fechas de las regeneraciones de la tabla anterior son históricas y no se modifican por el nuevo intervalo.

Limitación conocida: el intento `SKIPPED` después de descargar deja RAW retenido y `cleanup` lo aplaza; la corrección sigue pendiente. La política de conservación describe la intención y la ruta de éxito, no resuelve ese fallo.

La suite actual contiene **27 pruebas** de catálogo, reintentos, regeneración, retención y QA. Docker/Airflow siguen pendientes de orden explícita. Recordar incorporar datos in situ antes de declarar aceptación científica de productos acuáticos.
