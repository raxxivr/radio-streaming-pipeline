-- Question: Which countries have the most stations?
-- Grain: one row per country with at least one station, ordered by station count descending.
SELECT 
	c.country_code,
	c.country_name,
	COUNT(*) AS station_count
FROM stations AS s
JOIN country AS c
	ON s.countrycode = c.country_code
GROUP BY c.country_code, c.country_name
ORDER BY station_count DESC;