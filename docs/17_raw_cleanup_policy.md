# Temporales, estados y conservación

## Organización propuesta

- `storage/catalog/`: consultas e historial persistente.
- `storage/runs/<run_id>/`: configuración, logs, estado, validación y benchmark.
- `storage/temporary/<run_id>/`: descargas, extracción y archivos de trabajo propios.
- `storage/acolite/<aoi_id>/<product_id>/<run_id>/`: resultados seleccionados.

La estructura evita sobrescribir distintas versiones. No crear caché global compartida de SAFE.

## Estados conceptuales

Descubierto → adquiriendo → entrada disponible → procesando → procesado → validado → limpieza completada. Zarr puede pasar a entrada disponible sin descarga completa; no registrar descarga exitosa inexistente.

Registrar por separado fallos de adquisición, procesamiento, validación y limpieza. Una limpieza fallida no invalida un resultado científico ya válido, pero requiere atención al espacio ocupado.

## Limpieza por éxito

Solo tras validación aprobada y persistencia del registro de resultados. Eliminar únicamente fuentes y temporales de la ejecución. Conservar catálogo, settings, logs, reportes, métricas y productos seleccionados. Auditar y desactivar la eliminación prematura nativa cuando corresponda.

## Limpieza por fallo

El usuario prefiere liberar fuentes recuperables al agotar reintentos. Esto es una política distinta de limpieza por éxito: nunca marcar como validada una ejecución fallida. Antes de borrar, conservar diagnóstico, referencia recuperable, intentos y motivo, e informar la limpieza. Si la fuente no es recuperable o no existe diagnóstico suficiente, conservarla y registrar la excepción.

## Límite de borrado

Resolver la ruta absoluta y comprobar que pertenece al directorio temporal de esa ejecución; rechazar enlaces o rutas que escapen de él. No eliminar entradas externas, credenciales, instalaciones, AOI ni resultados persistentes. El borrado repetido debe ser seguro y quedar registrado.

Retención persistente sin caducidad automática por ahora. Respaldo y capacidad a largo plazo quedan pendientes; permanencia no equivale a disponer de una copia de seguridad.
