# Catálogo y trazabilidad científica

Política vigente: [conservación L1R/L2W y reinicio de pruebas](33_retention_and_reset.md). SQLite es el único registro operativo; no se duplican resultados en JSON por etapa, manifiestos por ejecución ni backups después de cada comando.

## Modelo pequeño: seis tablas

| Tabla | Información conservada |
|---|---|
| consultas | Proveedor, AOI/intervalo/filtro, estado y completitud |
| versiones_producto | Identidad, revisión, representación, metadata seleccionada y SHA/checksum disponible |
| observaciones | Relación consulta/versión y contador de duplicados |
| ejecuciones | Configuración, clave de trabajo, padre L1R, estados, resumen científico y métricas breves |
| artefactos | Nuevos archivos persistentes L1R/L2W: ruta, bytes, SHA, variables y grilla; también conserva registros históricos L2R eliminados |
| eventos | Fallos, reintentos, fallback, cambios de estado y eliminación de fuentes |

Se mantienen snapshots de fuente inmutables. No se deduplica por fecha ni se confunden hashes de ZIP, TAR y Zarr. El SHA se compara dentro de representaciones equivalentes; cambios administrativos no implican por sí mismos nueva ciencia. Si no hay checksum remoto confiable, comprobar contenido antes de omitir trabajo.

Cada ejecución conserva configuración, revisión/hash del parche ACOLITE, entorno, metadata atmosférica seleccionada expuesta por L2R, fracciones finitas de productos y métricas de etapa. Los NetCDF conservan su metadata nativa. No se almacena un segundo volcado completo de fuente/configuración ni hashes de todo el directorio de LUT por ejecución.

## Reprocesamiento e idempotencia

Una salida L2W íntegra, con la misma entrada y configuración, permite omitir cálculo. Para otros productos compatibles, buscar L1R registrado y comprobar archivo, hash y grilla. Regenerar L2R temporal y L2W mediante ACOLITE, conservando referencia al padre. Esto evita descarga y lectura del RAW, pero repite AC. Cambios de AOI, bandas disponibles o corrección requieren revisar compatibilidad; no prometer reutilización universal.

La validación técnica y la aceptación científica son estados distintos. Tras registrar L1R y L2W técnicamente íntegros se pueden borrar RAW/L2R; la ciencia puede seguir pendiente. Un fallo de limpieza no repite AC ni cambia una ejecución exitosa a fallida. Una salida borrada o corrupta impide omitir trabajo por un registro antiguo.

## Archivos y recuperación

`storage/catalog/catalog.sqlite` contiene el historial. `storage/runs/<run_id>/` conserva únicamente L1R/L2W al terminar correctamente; `storage/temporary/` contiene transporte IPC, descarga y extracción de vida corta. No hay archivos JSON permanentes de validación/provenance ni logs de éxito. Los errores quedan como etapa/tipo/evento sin tokens ni cuerpos de autenticación.

Un bloqueo de escritor permite una operación a la vez. Las migraciones de esquema son locales y transaccionales; el esquema actual es v2. `recover` marca intentos abandonados como interrumpidos y no aprueba archivos huérfanos. Los backups se harán en hitos o por solicitud, no tras cada consulta/comando. Las credenciales nunca pertenecen al catálogo.

Los archivos de ensayos eliminados se marcan `DELETED`, manteniendo resultados y hashes útiles en el catálogo. Los ensayos antiguos no se convierten en ciencia aprobada. Las limitaciones reales siguen explícitas: paginación USGS desconocida, ausencia de ensayo Zarr remoto compatible e igualdad numérica condicionada a recursos auxiliares compatibles.

Limitación vigente: si la coincidencia de contenido se detecta después de descargar, el intento `SKIPPED` deja RAW retenido y `cleanup` lo aplaza. La omisión de cálculo funciona, pero esa limpieza sigue pendiente de corrección; véase [fase 11](32_phase11_wrapper.md).
