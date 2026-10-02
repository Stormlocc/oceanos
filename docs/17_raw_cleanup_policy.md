# Conservación y limpieza

Se conservan **L1R y L2W** y un único catálogo SQLite. L2R, RAW, archivos IPC, logs y settings duplicados son temporales. La política se aplica a todo el plan, incluidos futuros contenedores, Airflow y cubos Zarr.

## Ejecución correcta

1. Verificar L1R, L2W, grilla, productos y flags; usar L2R temporal para verificar bandas Rrs y extraer metadata atmosférica relevante.
2. Registrar artefactos, SHA y resumen científico en SQLite.
3. Eliminar L2R y archivos auxiliares propios de la ejecución; retirar descarga/extracción cuando L1R/L2W registrados sigan disponibles e íntegros.

No es necesario esperar validación in situ para retirar intermediarios reproducibles: L1R permite volver a corregir y obtener L2W. Esto no cambia la aceptación científica, que sigue pendiente. No borrar ni sobrescribir un L1R padre de otra ejecución.

## Fallos

Tras reintentos agotados se puede eliminar el temporal de una fuente remota recuperable, conservando referencia y diagnóstico en SQLite. Ante interrupción o ausencia de L1R/L2W íntegros sin reintentos agotados se conserva lo necesario para recuperar el intento. Un fallo de limpieza queda separado del cálculo científico.

Toda ruta de borrado se resuelve y se comprueba dentro del temporal de esa ejecución. Nunca borrar fuentes locales externas, AOI, credenciales, código o productos de otra ejecución. Los flags nativos de borrado NetCDF permanecen desactivados: el wrapper limpia después del registro y QA técnico.

## Reinicio solicitado de las pruebas

Por orden del usuario se eliminaron los datos de todos los ensayos previos, incluidos sus L1R/L2R/L2W, RAW y cachés descargadas para las pruebas. Es un reinicio puntual, distinto de la política futura que conserva L1R/L2W. Se preservan el catálogo con disponibilidad actualizada, el resumen científico histórico, el AOI original, los perfiles y el código. [Detalle y cantidades](33_retention_and_reset.md).

## Limitación actual del wrapper

Si después de descargar se reconoce un L2W reutilizable, el intento termina `SKIPPED` y el RAW queda retenido. `cleanup` no trata ese estado como éxito limpiable y lo aplaza. Este fallo está documentado y pendiente de corrección; no se considera resuelto por la política anterior.
