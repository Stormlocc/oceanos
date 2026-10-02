# Documentación del proyecto NASA OCEANOS

Actualizado: 1 de octubre de 2026. AOI: `lapargera_v1`.

**Política vigente para todo el plan:** conservar L1R/L2W y SQLite; L2R/RAW y registros duplicados son temporales. Regenerar desde L1R repite AC. Se solicitó reiniciar los ensayos para avanzar paso a paso; ver [conservación y limpieza](33_retention_and_reset.md).

## Estado de la entrega

Fases 0–5 completadas en su alcance de análisis, auditoría, diseño y configuración. Fases 6–10 ejecutadas técnicamente: cinco Sentinel-2 y tres Landsat sobre la grilla común, con productos acuáticos mayormente enmascarados. La validación científica permanece abierta.

Fase 11 implementada: wrapper local secuencial, SQLite v2, regeneración desde L1R, retención L1R/L2W y suite de 27 pruebas. El reinicio autorizado retiró las escenas de ensayo y preservó el historial; no quedan NetCDF de esos ensayos para reutilizar. La limpieza inicialmente aplazada en fase 9 fue reemplazada por la decisión del [documento 33](33_retention_and_reset.md).

Perfil actual Sentinel-2: [2026-08-01,2026-08-15) UTC; Landsat: [2026-08-01,2026-08-21). Los informes históricos de cinco Sentinel-2 corresponden al intervalo 1–20, no a una consulta nueva con el perfil reducido.

ACOLITE: instalación `/home/antho/acolite` en `80da0c0` con parche de catálogo aplicado por `prepare`; la copia `.work/acolite-audit` se eliminó. Ver [documento 34](34_acolite_installation.md).

Zarr remoto retirado del wrapper el 01-10-2026 (sin cobertura EOPF para el AOI; ver documento 06). Pendientes: validación in situ, máscara exclusivamente oceánica y corrección de RAW retenido cuando se omite cálculo después de descargar (`SKIPPED`). Ver [riesgos actuales](21_risks_and_decisions.md). Docker/Airflow (fase 12), cubo Zarr (fase 13) y productos propios (fase 14) no iniciados.

**No descargar escenas, LUT, auxiliares ni dependencias sin autorización explícita del usuario.** `run` y `derive` pueden solicitar auxiliares aun con entrada local; el CLI no aplica un bloqueo de red. Cada nueva fase requiere orden explícita. Esta sincronización documental no inicia procesamiento ni consultas remotas.

Los informes de fases conservan cifras y conclusiones de sus ensayos, con notas de estado vigente. Las evidencias JSON, manifiestos y scripts retirados se citan como históricos; los enlaces al documento 33 explican su consolidación y no ofrecen copias de esos archivos.

## Índice

| Documento | Contenido |
|---|---|
| [00_project_scope.md](00_project_scope.md) | Requisitos, alcance y orden de fases |
| [01_aoi_analysis.md](01_aoi_analysis.md) | AOI, tiles y análisis pendiente |
| [02_acolite_architecture.md](02_acolite_architecture.md) | Auditoría y matriz de responsabilidades |
| [03_acolite_catalog.md](03_acolite_catalog.md) | Selección e identidad de adquisiciones |
| [04_acolite_download.md](04_acolite_download.md) | Adquisición y reintentos |
| [05_acolite_input_formats.md](05_acolite_input_formats.md) | Formatos de entrada |
| [06_acolite_zarr_input.md](06_acolite_zarr_input.md) | Comparación Zarr remoto y SAFE; retirada de Zarr |
| [07_acolite_roi.md](07_acolite_roi.md) | Recorte y máscara |
| [08_acolite_l1r.md](08_acolite_l1r.md) | Conversión y alineación |
| [09_acolite_atmospheric_correction.md](09_acolite_atmospheric_correction.md) | Corrección atmosférica y defaults |
| [10_acolite_l2r.md](10_acolite_l2r.md) | Reflectancias y reutilización |
| [11_acolite_l2w.md](11_acolite_l2w.md) | Productos solicitados |
| [12_acolite_projection.md](12_acolite_projection.md) | Grilla y reproyección |
| [13_acolite_storage_cost.md](13_acolite_storage_cost.md) | Recursos y benchmark |
| [14_selected_aoi_configuration.md](14_selected_aoi_configuration.md) | Perfil candidato y tabla de decisiones |
| [15_validation_plan.md](15_validation_plan.md) | Validación simple y tests |
| [16_catalog_provenance.md](16_catalog_provenance.md) | Persistencia, hashes y cambios |
| [17_raw_cleanup_policy.md](17_raw_cleanup_policy.md) | Estados y eliminación de temporales |
| [18_airflow_design.md](18_airflow_design.md) | Orquestación futura |
| [19_zarr_future.md](19_zarr_future.md) | Cubo temporal futuro |
| [20_multitile_future.md](20_multitile_future.md) | Cambios de AOI y mult tile |
| [21_risks_and_decisions.md](21_risks_and_decisions.md) | Riesgos y pendientes |
| [22_step54_delivery.md](22_step54_delivery.md) | Correspondencia con los 23 entregables |
| [23_phase2_audit_results.md](23_phase2_audit_results.md) | Resultados y límites verificados de fase 2 |
| [24_phase3_catalog_design.md](24_phase3_catalog_design.md) | Decisiones del catálogo y provenance |
| [25_phase4_aoi_configuration.md](25_phase4_aoi_configuration.md) | Perfil científico candidato y comprobaciones |
| [26_phase5_input_strategy.md](26_phase5_input_strategy.md) | Disponibilidad comprobada y adquisición seleccionada |
| [27_phase6_first_scene.md](27_phase6_first_scene.md) | Ensayo real, métricas e incidencia de enmascarado |
| [28_phase7_validation.md](28_phase7_validation.md) | Validación técnica y dictamen de productos acuáticos no aceptados |
| [29_phase8_benchmark.md](29_phase8_benchmark.md) | Análisis de tiempos, RAM, disco y límites del ensayo |
| [30_phase9_cleanup.md](30_phase9_cleanup.md) | Decisión de conservación, inventario y limpieza aplazada |
| [31_phase10_multidate.md](31_phase10_multidate.md) | Ocho adquisiciones, integración Landsat y cierre técnico |
| [32_phase11_wrapper.md](32_phase11_wrapper.md) | Wrapper operativo local, catálogo, reintentos y pruebas |
| [33_retention_and_reset.md](33_retention_and_reset.md) | Política transversal, prueba de regeneración y reinicio limpio |
| [34_acolite_installation.md](34_acolite_installation.md) | Instalación ACOLITE usada, comando `prepare` y parche |

## Fuentes y trazabilidad

Los requisitos provienen del documento de proyecto y las respuestas del usuario en esta conversación. El archivo geométrico fue movido a `config/aoi/lapargera_v1/W2C_South_AOI.kmz`, con igualdad de SHA-256 comprobada antes y después del movimiento.

Se verificó la existencia de `/home/antho/acolite` (actualizada a `80da0c0` el 01-10-2026), `/home/antho/acolite.main-d61c8de` y `/home/antho/.netrc`. El contenido de las credenciales no se leyó. El SHA `0a963cd` observado pertenece a otra copia, `/home/antho/projects/EMC/tools/acolite`: no debe atribuirse a la instalación elegida.

Autoridad técnica de la auditoría: código de [ACOLITE](https://github.com/acolite/acolite), fijado a una revisión identificable y comparado con la instalación local. Los documentos de fase 2 distinguen capacidades verificadas en código de resultados todavía pendientes de ejecución.
