# Fase 9 — evaluación de limpieza y conservación

> Informe histórico. Estado vigente al 30-09-2026: la decisión de aplazar limpieza fue reemplazada por la política de QA técnico y el reinicio autorizado ya ejecutado. El catálogo está implementado y los archivos de este ensayo figuran eliminados. Rige la [política L1R/L2W y reinicio](33_retention_and_reset.md); las cifras y decisiones originales no describen la disponibilidad actual de archivos.

Fecha: 29 de septiembre de 2026. **Decisión histórica: conservar la ejecución y aplazar el borrado.** Estado `DEFERRED_VALIDATION`. Se liberaron **0 bytes** y no se eliminó ningún archivo. La fase 10 se ejecutó posteriormente.

## Motivo

La política aplicada entonces condicionaba la limpieza a la validación aceptada y al registro persistente. Fue reemplazada por la [política vigente](17_raw_cleanup_policy.md), que permite retirar intermediarios tras QA técnico de L1R/L2W y registro, sin esperar aprobación científica. También contempla limpieza por fallo recuperable tras agotar reintentos, conservando diagnóstico y procedencia.

Esta ejecución terminó y produjo NetCDF, pero Rrs, turbidez, OC3 y NDCI contienen cero píxeles válidos. La fase 7 descartó errores concretos de escala y geolocalización y formuló la hipótesis de glint; todavía no hay una solución científica validada. No se agotaron reintentos de adquisición o procesamiento. Repetir el mismo cálculo no convierte este estado de calidad en un fallo transitorio ni habilita su borrado.

Al cerrar fase 9 aún no existía SQLite. La fase 11 lo implementó y el reinicio consolidó la trazabilidad útil, retirando los JSON independientes. No se implementó un limpiador genérico antes de su fase.

## Inventario y decisión

| Grupo | Decisión | Motivo |
|---|---|---|
| ZIP original | Conservar | Fuente íntegra, con SHA-256 comprobado; permite recuperar SAFE sin red |
| SAFE extraído | Conservar | Diagnóstico y posible reprocesamiento científico pendientes |
| L1R | Conservar | Permite revisar TOA y repetir corrección sin reconvertir la entrada |
| L2R | Conservar | Reflectancias, geometría y TOA necesarias para análisis y derivaciones |
| L2W | Conservar como resultado no aceptado | Evidencia reproducible del enmascarado; no publicar como producto válido |
| Settings, logs y reportes | Conservar | Trazabilidad e historial de ambos intentos |
| LUT y copia auditada de ACOLITE | Fuera del borrado de RAW | Recursos reutilizables y referencia del procesador |
| AOI, credenciales e instalación original | Fuera del alcance | No pertenecen al temporal de la escena |

La carpeta de ensayo contenía **76 archivos y 2.789.939.291 bytes (2,79 GB)**. La medición de fase 8 que también incluye data/LUT fue 3,42 GB; los alcances son diferentes y no deben sumarse. No hay presión de presupuesto demostrada que justifique cambiar la decisión: ambos valores están por debajo del techo de 50 GB.

## Comprobaciones realizadas

- La ruta absoluta de `.work/phase6_20260804` está dentro del proyecto.
- Se enumeraron los archivos del ensayo y se comprobó que sus rutas resueltas permanecen dentro de esa carpeta, sin enlaces simbólicos en el árbol inspeccionado.
- Se recalcularon los SHA-256 del ZIP, L1R, L2R y L2W: los cuatro coinciden con fase 6.
- Se comprobó que no se cumplen las condiciones de limpieza por éxito ni de reintentos agotados.
- El registro final contiene lista de borrados vacía y cero bytes liberados.

No se ejecutó un borrado para probar la política. No se creó una suite de tests de un limpiador todavía inexistente. El wrapper posterior incorpora pruebas de limpieza, exclusión de rutas externas, recuperación y fallo de borrado; la limpieza de `SKIPPED` permanece pendiente.

Evidencia: [inventario, hashes y decisión — evidencia consolidada](33_retention_and_reset.md#historial). Los archivos conservaron sus rutas hasta el reinicio posterior; actualmente están retirados y registrados como eliminados.

## Revisión posterior

La evaluación de fase 9 quedó entregada con eliminación aplazada. **Esa decisión ya fue reemplazada:** el usuario autorizó reiniciar los ensayos y la eliminación física se ejecutó según el documento 33. La falta de aceptación científica no impide actualmente limpiar intermediarios tras QA técnico.

La retención local no equivale a una copia de seguridad externa. Tampoco convierte los NetCDF no aceptados en productos finales. Durante fase 9 no se descargaron ni procesaron otras fechas; eso se realizó después en fase 10. La próxima fase no iniciada es la 12 y requiere orden explícita.
