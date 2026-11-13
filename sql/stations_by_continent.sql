-- Question: How many stations are there per continent, including an Unknown bucket
--           for stations with missing or unmatched country metadata?
-- Grain: one row per continent (including Unknown), ordered by station count descending.
SELECT 
	COALESCE(NULLIF(TRIM(c.continent), ''), 'Unknown') AS continent,
	COUNT(*) AS station_count
FROM stations AS s
LEFT JOIN country AS c
	ON s.countrycode = c.country_code
GROUP BY 
	COALESCE(NULLIF(TRIM(c.continent), ''), 'Unknown')
ORDER BY station_count DESC;