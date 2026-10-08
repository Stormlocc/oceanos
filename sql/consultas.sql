-- Consultas de solo lectura sobre storage/catalog/catalog.sqlite (esquema v4).
-- Abrir con:  python -m sqlite3 storage/catalog/catalog.sqlite   (o DB Browser for SQLite)
-- Tablas: escenas (catálogo + cola), procesos (descarga/procesamiento + L1R/L2W),
--         busquedas (cada search) y eventos (historial legible).
-- Vistas listas: v_resumen, v_cola, v_descargas, v_fallidas, v_disco  →  SELECT * FROM v_resumen;

-- 1. Resumen general (cantidades por estado) y espacio en disco.
SELECT * FROM v_resumen;
SELECT * FROM v_disco;

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

-- 8. Archivos importados con sync.
SELECT id, carpeta, l1r_mb, l2w_mb, archivos, validacion, escena FROM procesos WHERE tipo = 'IMPORTADO' ORDER BY id;

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
