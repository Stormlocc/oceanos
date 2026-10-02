# Alcance y requisitos acordados

## Objetivo

Construir un sistema reproducible y económico en disco alrededor de ACOLITE para calidad del agua costera. Antes de implementar una función, verificar si ACOLITE ya la resuelve. Delegar en ACOLITE catálogo, adquisición y procesamiento siempre que su implementación cubra la necesidad.

## Acuerdos

- AOI inicial: `lapargera_v1`, geometría suministrada y considerada definitiva para este estudio.
- MVP con Sentinel-2 y Landsat 8/9 ya incorporados; Docker sigue pendiente.
- Intervalo histórico: 1–20 de agosto de 2026. Perfil actual Sentinel-2: [2026-08-01,2026-08-15); Landsat: [2026-08-01,2026-08-21), en UTC y con final exclusivo.
- Todas las adquisiciones válidas, sin filtro de nubosidad del catálogo. Mantener ese filtro configurable por AOI.
- Salida rectangular a 10 m para Sentinel-2. Remuestrear no agrega información espacial original.
- Prioridad al océano, incluyendo bahías, lagunas costeras y aguas someras; evaluar máscara terrestre nativa.
- Una escena a la vez. Máximo 50 GB temporales.
- Entrada Sentinel-2: SAFE desde CDSE, con reintentos. Zarr remoto retirado el 01-10-2026 por falta de cobertura EOPF.
- Conservar únicamente L1R/L2W y trazabilidad útil en SQLite; RAW, L2R y registros duplicados son temporales.
- Reutilizar L1R para regenerar productos mediante L2R temporal; se evita descarga, pero se repite AC.
- Código futuro pequeño, legible y directo. Validaciones simples y tests de comportamiento relevantes.
- Documentación en español. Cada nueva fase requiere orden explícita.
- No descargar escenas, LUT, auxiliares ni dependencias sin autorización explícita. Una entrada local también puede provocar descargas auxiliares; el CLI no bloquea la red por sí mismo.

## Secuencia

0. Discovery: completado.
1. Analizar AOI: completado; 19QGV cubre todo el AOI.
2. Auditar ACOLITE: auditoría estática completada; ver documento 23.
3. Catálogo y provenance diseñados; implementados y probados con respuestas reales en fase 11, SQLite esquema v2.
4. Perfil científico candidato preparado y ensayado técnicamente en fases 6 y 10; OC4 excluido. Aceptación científica pendiente.
5. Adquisición y fallback definidos; disponibilidad consultada: cinco SAFE, cero Zarr. Ver documento 26. Zarr retirado el 01-10-2026 (documento 06).
6. Escena procesada; productos acuáticos totalmente enmascarados. Ver documento 27.
7. Revisión técnica completada: escala y grilla correctas en las pruebas; productos acuáticos no aceptados. Validación científica pendiente. Ver documento 28.
8. Benchmark de una escena analizado; concurrencia uno mantenida. Ver documento 29.
9. Limpieza inicialmente aplazada. Decisión reemplazada por conservación L1R/L2W tras QA técnico y reinicio explícito de ensayos ya ejecutado. Ver documentos 30 y 33.
10. Repetición e incorporación Landsat completadas técnicamente: cinco Sentinel-2 y tres Landsat; validación científica pendiente. Ver documento 31.
11. Wrapper mínimo implementado: SQLite, procesamiento nativo, reintentos, reutilización L1R y 27 pruebas. Pendiente corregir temporales retenidos en `SKIPPED` después de descargar. Ver documento 32.
12. Docker y Airflow: no iniciados, requieren orden explícita.
13. Cubo Zarr: no iniciado.
14. Productos científicos propios solo donde ACOLITE no cubra la necesidad: no iniciados.

La entrega documental no autoriza por sí misma la ejecución de estas fases.
