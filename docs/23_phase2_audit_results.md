# Resultado de fase 2 — auditoría técnica ACOLITE

> Informe histórico. Estado vigente al 30-09-2026: auditoría completada; revisión fijada, OC4 excluido y parche de catálogo implementado. Ensayos y wrapper completados técnicamente en fases posteriores; ciencia pendiente. Rige la [política L1R/L2W y reinicio](33_retention_and_reset.md); las cifras y decisiones originales no describen la disponibilidad actual de archivos.

Fecha: 25-09-2026. Estado: **auditoría estática completada para el alcance solicitado**; no se procesaron escenas ni se validó científicamente el perfil.

## Conclusión

ACOLITE cubre el núcleo: consulta, descarga, extracción, lectura S2/Landsat, ROI, alineación, corrección, L2R/L2W y NetCDF. Nuestro código puede mantenerse pequeño: perfil AOI, registro de catálogo/ejecución, comprobación de outputs y política de limpieza. Hay límites concretos que requieren decisiones o adaptaciones mínimas; no justifican otro procesador.

## Hallazgos determinantes

1. Instalación local `f73cbe73887c2b114d9d3c70865effee73871525` distinta del upstream auditado `80da0c0c681d9597fd4b7737837d6a3e61907b33`. No se actualizó. Cambian defaults científicos y de almacenamiento: fijar versión antes del benchmark. *Resuelto el 01-10-2026: instalación actualizada a `80da0c0` ([documento 34](34_acolite_installation.md)).*
2. `chl_oc4` no está configurado para S2A/B/C; el procesador puede omitirlo sin abortar. Se registró inicialmente como requisito pendiente; el usuario lo excluyó el 29 de septiembre, sin sustitución.
3. FAI y NDVI no reciben la máscara acuática estándar. Existe máscara tierra/agua nativa separada que puede evitar lógica geográfica propia, con prueba previa.
4. El proyector general apila datasets, modifica rangos ya alineados si align=True y omite l2_flags al escribir. Grilla nativa single-tile merece evaluarse primero; no activar reproyección indiscriminada.
5. CDSE retorna metadata parcial incluso con attributes=True. STAC conserva features completos si no se pide selección reducida. El diseño del catálogo debe contemplarlo.
6. Zarr remoto está implementado para estructura EOPF y descubrimiento EODC; no es soporte universal ni evidencia de disponibilidad/ahorro para agosto de 2026.
7. Descargas nativas no usan streaming explícito y pueden borrar ZIP/TAR antes de QA. El token CDSE se imprime si verbosity>1. Registrar el riesgo y usar verbosidad segura; no se expusieron credenciales.
8. Hay diferencias temporales entre APIs, URL STAC defectuosa sin bbox y ausencia de paginación explícita EarthExplorer. Se documentaron límites y mitigaciones pequeñas, sin escribir un cliente nuevo.

## Entregables

- [Arquitectura y matriz](02_acolite_architecture.md).
- [Catálogo](03_acolite_catalog.md), [descarga](04_acolite_download.md), [formatos](05_acolite_input_formats.md), [Zarr remoto](06_acolite_zarr_input.md).
- [ROI](07_acolite_roi.md), [L1R/S2/Landsat](08_acolite_l1r.md), [corrección](09_acolite_atmospheric_correction.md), [L2R](10_acolite_l2r.md), [L2W](11_acolite_l2w.md).
- [Proyección](12_acolite_projection.md) y [81 settings con defaults/decisión/fuente](14_selected_aoi_configuration.md).
- [Evidencias de comprobación — evidencia consolidada](33_retention_and_reset.md#historial), [alineación reproducida — evidencia consolidada](33_retention_and_reset.md#historial) y [manifiesto — evidencia consolidada](33_retention_and_reset.md#historial).

Las referencias de código enlazan al commit exacto, no a main mutable. La auditoría revisó código y realizó ocho aserciones aisladas relevantes, sin benchmark, consultas de adquisiciones ni descargas de escenas. No se crearon tests del pipeline inexistente ni wrappers de procesamiento.

## Continuación posterior

La fase 3 completó el diseño de catálogo/provenance; la fase 11 lo implementó. La configuración permanece candidata científicamente. La siguiente fase no iniciada es Docker/Airflow (12), que requiere nueva orden.
