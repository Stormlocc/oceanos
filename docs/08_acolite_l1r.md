# L1R y alineación interna

Sentinel-2 tendrá una salida final a 10 m. Las bandas de resolución más gruesa se remuestrearán con los mecanismos de ACOLITE cuya implementación se verifique.

La auditoría debe seguir `s2_target_res`, las grillas originales, la función de proyección, `warp_to`, el método de resampling y la geometría de observación. Confirmar si SAFE y Zarr recorren rutas equivalentes.

Documentar CRS, origen, extent, dimensiones y tamaño de píxel antes y después de la conversión. Distinguir alineación de bandas dentro de una adquisición de alineación temporal entre adquisiciones.

L1R será inicialmente retenido durante el benchmark. Su conservación permanente no está decidida; depende de qué reprocesamientos futuros requieran información que no se conserva en L2R.
