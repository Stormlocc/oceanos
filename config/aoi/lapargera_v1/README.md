# Perfil científico lapargera_v1

`project.yaml` expresa el contrato OCEANOS; **ACOLITE no interpreta este YAML**. No existe todavía un wrapper que lo ejecute. `acolite_s2.txt` sí usa settings nativos y contiene solo cinco overrides respecto de la revisión auditada.

El KMZ es la geometría original; no se alteró. El límite enviado a ACOLITE está en orden sur, oeste, norte, este y produce un recorte rectangular. No se pasa `polygon`, porque la ruta auditada de polygon_limit activa clipping.

## Decisiones para el primer ensayo

- Sentinel-2 L1C, tile 19QGV, 1–20 agosto 2026 inclusive en UTC; nubosidad del catálogo desactivada.
- Revisión candidata ACOLITE `80da0c0c681d9597fd4b7737837d6a3e61907b33`. No ejecutar silenciosamente con otra revisión: los defaults locales difieren.
- DSF, auxiliares, gases, geometría y compresión: conservar defaults por plataforma de esa revisión.
- Resolución 10 m, merge_tiles=False, sin buffer y sin reproyección final. Estos valores ya son defaults, por eso no se copian al TXT.
- Conservar L2R y L2W nativos; L1R y temporales se conservan durante el ensayo hasta validar y decidir limpieza.
- No activar borrado nativo. La descarga usará remove_zip=False y remove_tar=False; son argumentos de adquisición, no settings del TXT.
- OC4 excluido por decisión del usuario del 29 de septiembre de 2026; OC3 permanece activo.
- FAI/NDVI permanecen sin máscara acuática nativa; una salida exclusivamente oceánica para todas las variables sigue pendiente. El usuario permite conservar tierra y aplicar filtro posteriormente.

## Grilla candidata

La función nativa projection_sub aplicada al extent nominal de 19QGV predice EPSG:32619, 2440 filas × 7335 columnas, xrange 701980–775330 m y yrange 1997360–1972960 m. Es distinta del envolvente del polígono calculado en fase 1: ahora se recorta su bounding box geográfico y se usa la alineación nativa de ACOLITE.

No es una grilla validada de escena. SAFE y Zarr deben producir coordenadas/extent coherentes; cualquier diferencia requiere revisión antes de publicar o acumular fechas. No tolerar silenciosamente un desplazamiento de medio píxel.

No crear aún `acolite_l89.txt`: Landsat será configurado y validado antes de Docker, no por copiar settings Sentinel-2.

Detalles y límites: [informe de fase 4](../../../docs/25_phase4_aoi_configuration.md).

## Ensayo real de fase 6

La grilla candidata fue confirmada con la escena del 4 de agosto. L1R, L2R y L2W se generaron, pero Rrs, turbidez, OC3 y NDCI quedaron totalmente enmascarados. El perfil conserva estado candidato; no modificar umbrales ni declarar aceptación científica. Ver [informe de fase 6](../../../docs/27_phase6_first_scene.md).
