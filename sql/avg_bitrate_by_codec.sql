-- Question: What is the average bitrate for each codec, using only stations with a positive bitrate?
-- Grain: one row per codec with at least one positive bitrate, ordered by average bitrate descending.
SELECT 
	codec,
	COUNT(*) AS station_count,
	AVG(bitrate)::NUMERIC(10,2) AS avg_bitrate_kbps
FROM stations
WHERE bitrate > 0
GROUP BY codec
ORDER BY avg_bitrate_kbps DESC;