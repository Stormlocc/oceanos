# Productos científicos solicitados

| Solicitud del usuario | Prioridad | Estado |
|---|---|---|
| `Rrs_*` | Obligatorio | Verificar expansión de bandas y máscara |
| `tur_nechad2009` | Obligatorio | Verificar nombre, banda, unidades y variante |
| `chl_oc3` | Obligatorio | Verificar soporte Sentinel-2 y algoritmo |
| `chl_oc4` | Obligatorio | Verificar soporte Sentinel-2 y algoritmo |
| `ndci` | Obligatorio | Verificar bandas y validez |
| `fai` | Obligatorio | Verificar fuente de reflectancia y máscara |
| `ndvi` | Obligatorio | Verificar compatibilidad con máscara oceánica |

Estos textos expresan requisitos, no una lista ejecutable verificada de `l2w_parameters`. Si alguno no está disponible, documentar la limitación y presentar alternativas al usuario; no sustituirlo automáticamente.

Auditar también flags, geometría y metadata necesaria para interpretar los resultados. SPM y AFAI no forman parte de la lista obligatoria actual; mantenerlos como posibilidades posteriores.

Comparar variantes implementadas de turbidez Nechad y Dogliotti, y algoritmos de clorofila. Documentar referencia, bandas seleccionadas, unidades, supuestos y limitaciones para aguas tropicales costeras, someras y con adyacencia terrestre. La solicitud de Nechad no demuestra superioridad universal.

Separar productos nativos de eventuales productos propios. No desarrollar índices propios durante el MVP.
