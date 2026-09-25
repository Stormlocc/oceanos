# Recorte y máscaras del AOI

Se requiere un rectángulo que cubra el AOI y una salida orientada al océano. Incluir bahías, lagunas costeras y aguas someras. Conservar tierra durante las etapas donde la necesite el procesador; evaluar máscara terrestre en productos finales.

No añadir buffer por defecto. La eliminación de tierra no debe confundirse con modificar el extent ni con eliminar todas las aguas costeras.

Auditar los candidatos `limit`, `region_name`, `polygon`, `polygon_limit`, `polygon_clip`, `limit_buffer`, `limit_buffer_units`, `extend_region` y `l1r_crop`. Determinar cuáles existen, defaults, orden de ejecución, nivel afectado y si reducen lectura, cambian extent o solo enmascaran valores.

No seleccionar una máscara antes de conocer su comportamiento en agua somera, vegetación flotante y costa. El filtro de nubosidad del catálogo está desactivado; las máscaras de calidad de píxel son una decisión científica independiente.
