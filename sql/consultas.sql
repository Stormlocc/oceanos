-- Consultas de solo lectura sobre storage/catalog/catalog.sqlite (esquema v5).
-- Abrir con:  python -m sqlite3 storage/catalog/catalog.sqlite   (o DB Browser for SQLite)
-- Tablas: escenas (catálogo + cola), procesos (descarga y procesamiento, legado=1 es lapargera_v1),
--         busquedas, eventos, productos_escena (superimagen por escena y zona, con linaje),
--         mascaras, compuestos (sargazo diario y compuestos) y compuesto_escenas.
-- Vistas: v_resumen, v_cola, v_descargas, v_fallidas, v_superimagen, v_compuestos, v_legado, v_disco.

-- 1. Resumen general (cantidades por estado) y espacio en disco.
SELECT * FROM v_resumen;
SELECT * FROM v_superimagen;

-- 2. Imágenes descargadas y procesadas: fecha, tiempos, intentos y tamaños.
SELECT * FROM v_descargas;

-- 3. Imágenes que no se pudieron descargar/procesar (sin éxito posterior).
SELECT * FROM v_fallidas;

-- 4. Reintentos: procesos con más de un intento de descarga y el motivo de cada intento fallido.
SELECT p.id, p.escena, p.estado, p.intentos,
       (SELECT group_concat(mensaje, ' | ') FROM eventos e WHERE e.proceso = p.id AND e.tipo = 'INTENTO_FALLIDO') AS fallos
FROM procesos p WHERE p.intentos > 1 ORDER BY p.id;

-- 5. Escenas procesadas más de una vez y su historial de estados.
SELECT escena, count(*) AS procesos, group_concat(estado, ' → ') AS historial
FROM (SELECT * FROM procesos ORDER BY id) GROUP BY escena HAVING count(*) > 1;

-- 6. Cola de descargas.
SELECT * FROM v_cola;

-- 7. Catálogo completo de escenas conocidas, con su estado.
SELECT fecha_utc, satelite, tile, tamano_mb, nubosidad, estado, escena FROM escenas ORDER BY fecha_utc;

-- 8. Legado (lapargera_v1 e importados con sync): L1R/L2W conservados fuera de la superimagen.
SELECT * FROM v_legado;
SELECT * FROM v_disco;

-- 9. Velocidad de descarga: totales y promedio por imagen.
SELECT count(*) AS descargas, round(sum(descarga_min), 1) AS minutos, round(avg(descarga_min), 1) AS minutos_promedio,
       round(sum(descarga_mb) / 1000, 2) AS gb, round(sum(descarga_mb) / sum(descarga_min * 60), 2) AS mb_por_segundo
FROM procesos WHERE descarga_min IS NOT NULL;

-- 10. Duración de cada etapa (descarga, extracción, ACOLITE) de los procesos OK.
SELECT p.id, json_extract(m.value, '$.stage') AS etapa, round(json_extract(m.value, '$.seconds') / 60, 2) AS minutos
FROM procesos p, json_each(json_extract(p.detalle, '$.metrics')) m WHERE p.estado = 'OK' ORDER BY p.id, m.key;

-- 11. Procesos con archivos faltantes o limpieza pendiente.
SELECT id, estado, archivos, limpieza, carpeta FROM procesos WHERE archivos = 'FALTAN' OR limpieza IN ('APLAZADA', 'FALLIDA');

-- 12. Búsquedas: completitud y escenas descartadas por el perfil con su motivo.
SELECT id, fecha, proveedor, sensor, desde, hasta, estado, devueltas, cumplen, total_proveedor, completitud, tamanos FROM busquedas ORDER BY id;
SELECT b.id, json_extract(d.value, '$.escena') AS escena, json_extract(d.value, '$.motivo') AS motivo
FROM busquedas b, json_each(b.descartadas) d ORDER BY b.id;

-- 13. Últimos eventos.
SELECT fecha, proceso, tipo, mensaje FROM eventos ORDER BY id DESC LIMIT 30;

-- 14. Superimagen: resultado de cada escena en cada zona, con nubes, cobertura y glint.
SELECT fecha, zona, sensor, satelite, estado, round(nubes_pct, 1) AS nubes, round(cobertura_pct, 1) AS cobertura,
       round(angulo_glint_deg, 1) AS glint_deg, round(bytes / 1e6, 1) AS mb, via_descarga, carpeta
FROM productos_escena ORDER BY fecha, zona;

-- 15. Linaje de un producto: fuente, checksums, ACOLITE, auxiliares y máscara.
SELECT escena, zona, proveedor_id, sha256, checksum_proveedor, baseline, via_descarga, acolite, auxiliares, mascara, fecha_proceso
FROM productos_escena WHERE estado = 'OK' ORDER BY fecha DESC LIMIT 10;

-- 16. Tamaño medio por producto de zona y por mes, frente al presupuesto de 100 GB.
SELECT sensor, zona, count(*) AS productos, round(avg(bytes) / 1e6, 1) AS mb_medio, round(sum(bytes) / 1e9, 2) AS gb
FROM productos_escena WHERE estado = 'OK' GROUP BY sensor, zona;
SELECT substr(fecha, 1, 7) AS mes, round(sum(bytes) / 1e9, 2) AS gb FROM productos_escena GROUP BY mes ORDER BY mes;

-- 17. Compuestos y escenas que entraron a cada uno.
SELECT * FROM v_compuestos;
SELECT c.tipo, c.metodo, c.zona, c.sensor, c.periodo, p.fecha, p.escena
FROM compuestos c JOIN compuesto_escenas ce ON ce.compuesto = c.id JOIN productos_escena p ON p.id = ce.producto
ORDER BY c.tipo, c.zona, c.periodo, p.fecha;

-- 18. Máscaras de tierra.
SELECT * FROM mascaras ORDER BY zona, resolucion_m;
