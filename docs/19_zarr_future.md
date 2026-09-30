# Cubo Zarr futuro

No implementar durante el MVP. Distinguir Zarr remoto como entrada de ACOLITE del cubo temporal propio de productos derivados.

Entrada futura: NetCDF validado por adquisición, con variables, unidades, máscaras y grilla documentadas. Partición lógica por AOI y versión de grilla. Cada variable puede representarse con dimensiones tiempo, y, x; no imponer una dimensión única de variable si unidades o tipos difieren.

Diseñar después política de ingestión, duplicados temporales, sustitución por revisiones, chunks, compresión y escrituras recuperables. Conservar vínculo a ejecución, configuración y fuente. No mezclar silenciosamente productos con algoritmos o grillas incompatibles.

No eliminar NetCDF por crear un cubo hasta decidir y verificar explícitamente una política de conservación.

## Política vigente de conservación

El cubo futuro se alimentará de L2W retenidos. L2R no será un archivo persistente ni una copia adicional dentro del cubo. La decisión de mantener otra representación de L2W deberá justificarse en esa fase para evitar duplicación. Ver [decisión transversal](33_retention_and_reset.md).
