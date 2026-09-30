# L2R temporal y regeneración desde L1R

La política vigente conserva **L1R y L2W**. L2R se genera como intermedio y se elimina después de verificar y registrar las salidas. Se prioriza ahorrar disco sobre ahorrar cálculo.

ACOLITE acepta un NetCDF L1R completo: `acolite_l1r` reconoce el formato ACOLITE y reutiliza el archivo; `acolite_run` identifica `acolite_file_type=L1R`, llama a `acolite_l2r` y después a `acolite_l2w`. Por tanto, L1R es suficiente como entrada radiométrica para los productos compatibles del perfil, pero **no produce L2W directamente**: hay que repetir la corrección atmosférica.

Se necesitan las bandas TOA, geometría y metadata originales del L1R, además de la revisión ACOLITE, settings, tablas/RSR y auxiliares atmosféricos compatibles. L1R no contiene por sí solo todos los recursos externos ni garantiza igualdad bit a bit si estos cambian. Tampoco permite recuperar bandas descartadas, ampliar el AOI recortado o generar NDCI Landsat sin las bandas necesarias.

Se conserva el L1R en la grilla final de este AOI. Para Landsat es el L1R ya proyectado antes de AC; al reutilizarlo no se repite la proyección. El wrapper verifica ejes/EPSG antes de regenerar, ejecuta la cadena nativa y comprueba L2W y flags antes de borrar L2R. L1R se referencia como padre y no se duplica cuando ya está registrado.

El L2R temporal conserva rhos y rhot para que ACOLITE calcule productos y flags. Su metadata científica seleccionada se guarda una vez en SQLite antes de eliminarlo. El catálogo retiene versión del procesador, ajustes, fuente, hashes, grilla y resultados de QA; no un inventario completo de todos los auxiliares disponibles por cada ejecución.

Fuentes verificadas localmente: `acolite/acolite/acolite_l1r.py` (rama ACOLITE), `acolite_run.py` (cadena L1R → L2R → L2W) y `acolite_l2w.py` (requiere entrada L2R). Revisión fijada: `80da0c0c681d9597fd4b7737837d6a3e61907b33`.

[Política transversal y comprobación de regeneración](33_retention_and_reset.md).
