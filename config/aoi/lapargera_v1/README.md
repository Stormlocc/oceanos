# Perfil lapargera_v1

- `project.yaml`: perfil común y Sentinel-2 (tile 19QGV, S2A/S2B/S2C).
- `landsat.yaml`: Landsat 8/9 (path/row 005/048), con `--sensor landsat`.
- `W2C_South_AOI.kmz`: geometría original; su SHA-256 está en `project.yaml` y se comprueba en cada carga.

ACOLITE no lee estos YAML: `oceanos/config.py` los traduce a settings nativos. Qué se envía, qué defaults se conservan y la grilla verificada (EPSG:32619, 2440 × 7335, 10 m): [docs/03_configuracion.md](../../../docs/03_configuracion.md). El AOI y su cobertura: [docs/01_proyecto.md](../../../docs/01_proyecto.md).

El perfil sigue siendo **candidato**: no modificar umbrales ni máscaras para forzar resultados, y no declarar aceptación científica sin datos in situ.
