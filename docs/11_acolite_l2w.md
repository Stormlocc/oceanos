# Productos L2W: compatibilidad, algoritmos y máscaras

> Estado vigente (30-09-2026): productos y flags comprobados técnicamente en ocho adquisiciones; cinco sin píxeles acuáticos finitos y tres con fracciones pequeñas. La presencia de variables no aprueba ciencia. OC4 excluido y NDCI solo Sentinel-2. Véase [fase 10](31_phase10_multidate.md).

Auditoría estática de fase 2, 25-09-2026. Revisión `80da0c0c681d9597fd4b7737837d6a3e61907b33`. Ensayos técnicos posteriores completados en fases 6/10; aceptación científica pendiente.

## Productos obligatorios

| Solicitud | Resultado de auditoría para S2A/B/C | Entrada y salida | Máscara acuática nativa |
|---|---|---|---|
| `Rrs_*` | Soportado; expansión según rhos disponibles | rhos/pi; sr-1 | Sí |
| `tur_nechad2009` | Soportado; selecciona banda cercana a 665 nm | Sale como TUR_Nechad2009_<longitud>; FNU | Sí |
| `chl_oc3` | Configurado para S2A/B/C | Máximo de azul 443/483 frente a verde 561; mg m-3 | Sí |
| `chl_oc4` | **No configurado para S2A/B/C** | La rama omite producto si no hay coeficientes | No se genera |
| `ndci` | Habilitado para MSI, no OLI | Cercanas a 670 y 705 nm, tolerancia 10 nm; adimensional | Sí |
| `fai` | Implementado; bandas típicas MSI B4/B8A/B11 | rhos, objetivos 660/865/1610 ±30/30/80 nm | No |
| `ndvi` | Implementado | Default S2 665/835, típicamente B4/B8; adimensional | No |

Las bandas reales y longitudes en nombres de datasets se obtienen de RSR de cada plataforma; registrar las seleccionadas en el output, no fijar un sufijo 665 universal. S2C usa `rsr_version=V4` por default, mientras S2A/B no tienen ese override activo.

**OC4 excluido por decisión del usuario el 29 de septiembre de 2026.** OC3 se mantiene como clorofila del MVP. La fila OC4 anterior conserva el resultado de auditoría; no es un requisito activo.

Fuentes: [acolite/acolite/acolite_l2w.py:203](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2w.py#L203-L281), [acolite/acolite/acolite_l2w.py:303](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2w.py#L303-L393), [acolite/acolite/acolite_l2w.py:760](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2w.py#L760-L817), [data/Shared/algorithms/chl_oc/defaults.txt:24](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/data/Shared/algorithms/chl_oc/defaults.txt#L24-L43), [acolite/acolite/acolite_l2w.py:1258](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2w.py#L1258-L1346), [acolite/acolite/acolite_l2w.py:1485](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2w.py#L1485-L1554), [acolite/acolite/acolite_l2w.py:1629](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2w.py#L1629-L1666).

## Clorofila

OC3 MSI usa coeficientes 0.3308, -2.6684, 1.5990, 0.5525, -1.4876 con referencia en tabla Pahlevan et al. 2020; el bloque de cálculo incluye un texto genérico Franz 2015 que no describe con precisión todas las calibraciones. Conservar tabla y revisión junto con atributos del producto. El código acepta bandas próximas dentro de 20 nm.

`chlor_a` no es simplemente chl_oc3: selecciona chl_ocx por sensor, calcula chl_ci y combina según configuración. Para S2/L8/L9 la tabla asigna chl_oc3, pero sus coeficientes no son idénticos entre MSI y OLI. Fuente: [acolite/acolite/acolite_l2w.py:150](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2w.py#L150-L170), [acolite/acolite/acolite_l2w.py:821](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2w.py#L821-L953), [data/Shared/algorithms/chl_ci/chl_ocx.txt:1](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/data/Shared/algorithms/chl_ci/chl_ocx.txt#L1-L14).

Estos algoritmos son productos de clorofila definidos, no mediciones directas; la contribución de sedimentos, materia orgánica disuelta y fondo somero exige validación local. No declarar un algoritmo óptimo universal.

## Turbidez y SPM

| Familia | Implementación | Bandas/unidades | Limitación para selección |
|---|---|---|---|
| Nechad 2009 TUR / 2010 SPM | A*rhos/(1-rhos/C), coeficiente central | Banda elegida, FNU / g m-3 | Dependencia de banda/calibración; enmascara rhos >= 0,5 C por default |
| Nechad Ave | Coeficientes remuestreados con RSR | Sensor/banda, mismas unidades | No equivalente exacto al coeficiente central |
| Nechad 2016 | Tabla sensor/banda/parámetro | Solo combinaciones con A/C disponibles | Verificar cobertura de tabla |
| Dogliotti 2015 | Rojo/NIR con mezcla entre umbrales | FNU | Pensado para rango de turbidez; no demuestra ventaja en agua clara |
| Dogliotti 2022 | Recalibración por banda/RSR | FNU | Metadata de referencia dice in prep/Nechad; verificar bibliografía al seleccionar |
| Novoa 2017 | Mezcla roja/NIR TUR o SPM | Según configuración nativa | Alternativa, no sustitución autorizada |

Fuentes: [acolite/acolite/acolite_l2w.py:303](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2w.py#L303-L643), [config/parameter_cf_attributes.json:1](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/config/parameter_cf_attributes.json#L1), [config/defaults.txt:260](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/config/defaults.txt#L260-L261). Otros algoritmos visibles incluyen Jiang TSS, QAA, índices red-edge y CRAT; no agregarlos al MVP por disponibilidad.

## FAI/AFAI y calidad

FAI resta una línea base espectral del NIR. AFAI usa 660/750/865 nm con tolerancias 30/30/80 nm, típicamente B4/B6/B8A MSI; OLI no dispone de banda próxima a 750 dentro de ese margen. Versiones `_rhot` usan TOA, las otras rhos. Ninguna equivale directamente a biomasa de sargazo.

L2W siempre escribe `l2_flags` cuando llega a creación de salida. Bits por default: 0 SWIR/no agua, 1 cirrus, 2 TOA alta, 3 reflectancia negativa, 4 fuera de escena, 5 mixto, 6 sombra DEM. La máscara aplicada usa selección de bits; mixtos tiene cálculo específico VIIRS y no debe interpretarse como detector universal MSI. No confundir filtro de nube del catálogo desactivado con flags desactivados.

El procesador puede avisar “Parameter not computed” y continuar, por lo que el test de éxito debe revisar variables finales y no solo existencia del NetCDF.
