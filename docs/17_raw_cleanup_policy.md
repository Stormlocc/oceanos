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

## Resultados de auditoría de fase 2

`delete_extracted_input=True` puede borrar la extracción al terminar L1R, **antes de L2R/L2W y antes de validación propia**. Mantener False. Fuente: [acolite/acolite/acolite_l1r.py:365](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l1r.py#L365-L380).

Los defaults de descarga `remove_zip=True` y `remove_tar=True` borran archivos después de extracción sin QA científica; son argumentos distintos de los settings delete. Los flags l1r/l2r/l2w_delete_netcdf se aplican al finalizar run sobre archivos existentes, sin nuestro contrato de validación. Mantenerlos False durante benchmark y manejar selección/limpieza después. Fuente: [acolite/acolite/acolite_run.py:334](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_run.py#L334-L351).

No se borró ninguna escena, fuente ni instalación durante la auditoría. La copia de código upstream en .work es referencia de investigación, no una escena temporal.


## Aplicación al ensayo inicial — fase 9

Se aplicó la política a la escena del 4 de agosto: estado `DEFERRED_VALIDATION`, cero archivos eliminados y fuentes conservadas. No hay validación acuática aceptada ni reintentos agotados. Los hashes de ZIP/L1R/L2R/L2W coinciden con fase 6. Ver [evaluación e inventario](30_phase9_cleanup.md).
