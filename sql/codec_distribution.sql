-- Question: What share of stations uses each codec?
-- Grain: one row per codec, with blank codecs grouped as Unknown, ordered by station count descending.
SELECT 
	COALESCE(NULLIF(TRIM(codec), ''), 'Unknown'),
	COUNT(*) AS station_count,
	ROUND((COUNT(*) * 100.0) / SUM(COUNT(*)) OVER (), 2) AS share_pct
FROM stations
GROUP BY COALESCE(NULLIF(TRIM(codec), ''), 'Unknown')
ORDER BY station_count DESC;