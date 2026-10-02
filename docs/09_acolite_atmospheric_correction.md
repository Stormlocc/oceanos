# Corrección atmosférica y defaults científicos

> Estado vigente (30-09-2026): corrección atmosférica ejecutada en fases 6/10 y repetida desde L1R en la verificación de conservación. La validez científica sigue pendiente. Landsat usa L1R a 10 m antes de AC y tiles DSF 600×600; los defaults nativos descritos abajo son la referencia auditada. No obtener LUT/auxiliares sin autorización.

Auditoría estática de fase 2, 25-09-2026. Revisión upstream `80da0c0c681d9597fd4b7737837d6a3e61907b33`. Las capacidades de código no equivalen a validación científica ni prueba con una escena real.

## DSF

Default general: atmospheric_correction=True, atmospheric_correction_method=dark_spectrum. S2A/B/C: estimación AOT tiled, espectro intercept, dos bandas, rango de ajuste 400–900 nm, intercepto 200 píxeles y tiles 600×600 píxeles. General usa rango 400–2500, intercepto 1000 y tiles 100×100; copiar esos valores generales como overrides destruiría los defaults del sensor.

A 10 m un tile DSF nominal es 6×6 km, distinto del tile MGRS. El método puede cambiar tiled a fixed si la imagen es demasiado pequeña; guardar los settings L2R efectivos. Selección de modelo min_drmsd, con límites de AOT/validez y tratamiento de NaN nativos. No activar filtros adicionales arbitrariamente.

L8/L9: tiled, 400–2500 nm, intercepto 200 y tiles 200×200; con 30 m son también nominalmente 6×6 km. El perfil Landsat posterior utiliza la proyección nativa de L1R antes de AC y tiles 600×600 a 10 m para mantener unos 6 km; véase fase 10.

Fuentes: [config/defaults.txt:418](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/config/defaults.txt#L418-L471), [config/defaults/S2A_MSI.txt:20](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/config/defaults/S2A_MSI.txt#L20-L37), [config/defaults/L8_OLI.txt:11](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/config/defaults/L8_OLI.txt#L11-L19), [acolite/acolite/acolite_l2r.py:433](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2r.py#L433-L496).

## Auxiliares, gases y presión

Gas transmittance=True; ancillary_data=True y ancillary_type=GMAO_MERRA2_MET. El parser convierte pressure=None a pressure_default=1013,25 hPa; L2R permite sustituir ese valor por auxiliares. Wind=None permite auxiliares; si falta, wind_default=2 m/s. Un override de presión distinto del default o viento explícito cambia esa precedencia. Registrar valores usados, origen y disponibilidad real.

Auxiliares se consultan para fecha y posición representativa del AOI; `ancillary.get` puede descargar e interpolar GMAO o recurrir a alternativas. No asumir que son archivos pequeños o que `.netrc` existente demuestra acceso. LUT y auxiliares deben contabilizarse en disco y provenance aunque no sean SAFE.

Fuentes: [acolite/acolite/acolite_l2r.py:177](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2r.py#L177-L195), [acolite/acolite/acolite_l2r.py:309](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2r.py#L309-L313), [acolite/ac/ancillary/get.py:40](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/ac/ancillary/get.py#L40-L116).

## Clasificación

| Grupo | Clasificación inicial | Criterio |
|---|---|---|
| DSF y defaults específicos S2 | Conservar default | Primera referencia reproducible |
| gas_transmittance, ancillary_data | Conservar default | Registrar disponibilidad y valores |
| pressure/wind | Conservar default | No imponer constantes sin evidencia |
| DEM pressure/altitude/shadow | No requerido inicialmente | Están desactivados; revisar si surge necesidad |
| dsf_interface_reflectance | Experimental si se propone cambio | Default False |
| dsf_residual_glint_correction | Experimental | Default False; no activarlo solo por ser costa |
| Adyacencia GLAD/RAdCor | Experimental | Cambia procesamiento; run distingue radcor de GLAD posterior |
| ROI y productos | Override AOI | Requisitos del estudio, no modificación de ciencia arbitraria |

RAdCor existe como método atmosférico, mientras GLAD se aplica después de DSF con flags específicos. No equivalen a un único interruptor universal. Antes de selección científica final se necesitan inspección de resultados y validación in situ; mantener este requisito abierto después de la revisión técnica de fase 7.
