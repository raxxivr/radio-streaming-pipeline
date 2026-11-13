-- Question: How much metadata is missing for each key station field
--           (countrycode, tags, homepage, codec, bitrate)?
-- Grain: one row per metadata field, ordered by missing percentage descending.
-- Note: null or blank text counts as missing; bitrate null or 0 also counts as missing.
SELECT 
    f.field_name,
    COUNT(*) AS total_stations,
    COUNT(*) FILTER (
        WHERE f.field_value IS NULL 
           OR TRIM(f.field_value) = ''
           OR (f.field_name = 'bitrate' AND f.field_value = '0')
    ) AS missing_count,
    CAST(
        COUNT(*) FILTER (
            WHERE f.field_value IS NULL 
               OR TRIM(f.field_value) = ''
               OR (f.field_name = 'bitrate' AND f.field_value = '0')
        ) * 100.0 / COUNT(*) 
        AS DECIMAL(10, 2)
    ) AS missing_pct
FROM stations AS s
CROSS JOIN LATERAL (
    VALUES 
        ('countrycode', s.countrycode::TEXT),
        ('tags',        s.tags::TEXT),
        ('homepage',    s.homepage::TEXT),
        ('codec',       s.codec::TEXT),
        ('bitrate',     s.bitrate::TEXT)
) AS f(field_name, field_value)
GROUP BY f.field_name
ORDER BY missing_pct DESC;