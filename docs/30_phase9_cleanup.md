# Fase 9 — evaluación de limpieza y conservación

Fecha: 29 de septiembre de 2026. **Política de limpieza aplicada: conservar la ejecución y aplazar el borrado.** Estado `DEFERRED_VALIDATION`. Se liberaron **0 bytes** y no se eliminó ningún archivo. No se inició la fase 10.

## Motivo

La [política acordada](17_raw_cleanup_policy.md) habilita limpieza por éxito solo después de validación aprobada y registro persistente. También contempla limpieza por fallo recuperable tras agotar reintentos, conservando diagnóstico y procedencia.

Esta ejecución terminó y produjo NetCDF, pero Rrs, turbidez, OC3 y NDCI contienen cero píxeles válidos. La fase 7 descartó errores concretos de escala y geolocalización y formuló la hipótesis de glint; todavía no hay una solución científica validada. No se agotaron reintentos de adquisición o procesamiento. Repetir el mismo cálculo no convierte este estado de calidad en un fallo transitorio ni habilita su borrado.

El catálogo operativo SQLite tampoco está implementado. Los JSON de evidencia conservan el historial del ensayo manual, pero no se presentan como el registro transaccional del wrapper futuro. No se implementó un limpiador genérico antes de su fase.

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

La carpeta de ensayo contiene **76 archivos y 2.789.939.291 bytes (2,79 GB)**. La medición de fase 8 que también incluye data/LUT fue 3,42 GB; los alcances son diferentes y no deben sumarse. No hay presión de presupuesto demostrada que justifique cambiar la decisión: ambos valores están por debajo del techo de 50 GB.

## Comprobaciones realizadas

- La ruta absoluta de `.work/phase6_20260804` está dentro del proyecto.
- Se enumeraron los archivos del ensayo y se comprobó que sus rutas resueltas permanecen dentro de esa carpeta, sin enlaces simbólicos en el árbol inspeccionado.
- Se recalcularon los SHA-256 del ZIP, L1R, L2R y L2W: los cuatro coinciden con fase 6.
- Se comprobó que no se cumplen las condiciones de limpieza por éxito ni de reintentos agotados.
- El registro final contiene lista de borrados vacía y cero bytes liberados.

No se ejecutó un borrado para probar la política. No se creó una suite de tests de un limpiador todavía inexistente. Las pruebas futuras del wrapper deberán cubrir validación fallida, exclusión de rutas externas/enlaces, recuperación tras interrupción y borrado repetible, conforme al plan ya documentado.

Evidencia: [inventario, hashes y decisión](evidence/phase9/retention_audit.json). Los archivos científicos conservan sus rutas originales para mantener válidos los enlaces del ensayo; no se movieron ni sobrescribieron.

## Revisión posterior

La evaluación de fase 9 queda entregada; **la eliminación física permanece aplazada**, no marcada como completada. Revisar esta decisión cuando exista una validación aceptable o una decisión explícita de cerrar el caso científico como no recuperable para el objetivo, conservando su diagnóstico y referencias. No establecer caducidad automática mientras esos criterios estén pendientes.

La retención local no equivale a una copia de seguridad externa. Tampoco convierte los NetCDF no aceptados en productos finales. La siguiente fase requiere orden del usuario; no se descargaron ni procesaron otras fechas.
