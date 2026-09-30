# Alcance y requisitos acordados

## Objetivo

Construir un sistema reproducible y económico en disco alrededor de ACOLITE para calidad del agua costera. Antes de implementar una función, verificar si ACOLITE ya la resuelve. Delegar en ACOLITE catálogo, adquisición y procesamiento siempre que su implementación cubra la necesidad.

## Acuerdos

- AOI inicial: `lapargera_v1`, geometría suministrada y considerada definitiva para este estudio.
- MVP Sentinel-2. Incorporar Landsat 8/9 antes de Docker.
- Intervalo inicial: 1–20 de agosto de 2026, ambos incluidos. La auditoría debe establecer cómo expresar correctamente el límite final en la API.
- Todas las adquisiciones válidas, sin filtro de nubosidad del catálogo. Mantener ese filtro configurable por AOI.
- Salida rectangular a 10 m para Sentinel-2. Remuestrear no agrega información espacial original.
- Prioridad al océano, incluyendo bahías, lagunas costeras y aguas someras; evaluar máscara terrestre nativa.
- Una escena a la vez. Máximo 50 GB temporales.
- Preferencia condicional por Zarr remoto; reintentos y fallback automático informado.
- Catálogo, configuraciones, logs y resultados útiles persistentes; fuentes grandes temporales.
- Reutilizar productos persistidos para generar nuevos productos cuando sea suficiente.
- Código futuro pequeño, legible y directo. Validaciones simples y tests de comportamiento relevantes.
- Documentación en español. Cada nueva fase requiere orden explícita.

## Secuencia

0. Discovery: completado.
1. Analizar AOI: completado; 19QGV cubre todo el AOI.
2. Auditar ACOLITE: auditoría estática completada; ver documento 23.
3. Diseñar catálogo y provenance: completado según retornos auditados; mapeo con respuestas reales pendiente de ejecución.
4. Perfil científico candidato preparado; OC4 excluido por el usuario. Ensayo real pendiente.
5. Adquisición y fallback definidos; disponibilidad consultada: cinco SAFE, cero Zarr. Ver documento 26.
6. Escena procesada; productos acuáticos totalmente enmascarados. Ver documento 27.
7. Revisión técnica completada: escala y grilla correctas en las pruebas; productos acuáticos no aceptados. Validación científica pendiente. Ver documento 28.
8. Benchmark de una escena analizado; concurrencia uno mantenida. Ver documento 29.
9. Limpieza evaluada: borrado aplazado por validación no aceptada; fuentes conservadas. Ver documento 30.
10. Repetición e incorporación Landsat completadas técnicamente: cinco Sentinel-2 y tres Landsat; validación científica pendiente. Ver documento 31.
11. Implementar wrapper mínimo.
12. Docker y Airflow.
13. Cubo Zarr.
14. Productos científicos propios solo donde ACOLITE no cubra la necesidad.

La entrega documental no autoriza por sí misma la ejecución de estas fases.
