# Documentación del proyecto NASA OCEANOS

Fecha: 25 de septiembre de 2026. AOI: `lapargera_v1`.

## Estado de la entrega

Fase 0 cerrada; fase 1 completada; fase 2 completada como auditoría estática; fase 3 completada como diseño de catálogo/provenance. Ver [resultado de fase 2](23_phase2_audit_results.md) y [diseño de fase 3](24_phase3_catalog_design.md). Todavía no hay pipeline, benchmark ni configuración científica validada.

Cada nueva fase requiere orden del usuario. El catálogo de fase 3 tiene diseño definido; las decisiones científicas y de adquisición de fases 4–5 siguen pendientes.

## Índice

| Documento | Contenido |
|---|---|
| [00_project_scope.md](00_project_scope.md) | Requisitos, alcance y orden de fases |
| [01_aoi_analysis.md](01_aoi_analysis.md) | AOI, tiles y análisis pendiente |
| [02_acolite_architecture.md](02_acolite_architecture.md) | Auditoría y matriz de responsabilidades |
| [03_acolite_catalog.md](03_acolite_catalog.md) | Selección e identidad de adquisiciones |
| [04_acolite_download.md](04_acolite_download.md) | Adquisición y fallback |
| [05_acolite_input_formats.md](05_acolite_input_formats.md) | Formatos de entrada |
| [06_acolite_zarr_input.md](06_acolite_zarr_input.md) | Comparación Zarr remoto y SAFE |
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

## Fuentes y trazabilidad

Los requisitos provienen del documento de proyecto y las respuestas del usuario en esta conversación. El archivo geométrico fue movido a `config/aoi/lapargera_v1/W2C_South_AOI.kmz`, con igualdad de SHA-256 comprobada antes y después del movimiento.

Se verificó la existencia de `/home/antho/acolite`, `/home/antho/acolite.main-d61c8de` y `/home/antho/.netrc`. El contenido de las credenciales no se leyó. El SHA `0a963cd` observado pertenece a otra copia, `/home/antho/projects/EMC/tools/acolite`: no debe atribuirse a la instalación elegida.

Autoridad técnica de la auditoría: código de [ACOLITE](https://github.com/acolite/acolite), fijado a una revisión identificable y comparado con la instalación local. Los documentos de fase 2 distinguen capacidades verificadas en código de resultados todavía pendientes de ejecución.
