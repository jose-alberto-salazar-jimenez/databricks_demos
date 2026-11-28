-- Preventive advisories per main town, language and user type, written by an LLM (ai_query) from
-- gold values only. Rebuilt on each pipeline update (daily): 109 towns x 2 languages x 3 user
-- types. The fallback model is called only for rows where the primary call failed.
-- Guardrail: numbers_ok is true when every number in the text is one of the injected values
-- ("24 hours/horas" allowed as a rewording of daily rain); the app shows only numbers_ok rows.
CREATE OR REFRESH MATERIALIZED VIEW ${gold_schema}.advisories (
  CONSTRAINT advisory_generated EXPECT (advisory_text IS NOT NULL),
  CONSTRAINT numbers_from_forecast EXPECT (numbers_ok)
)
COMMENT 'LLM advisories per town, language and user type; numbers injected from gold'
AS
WITH base AS (
  SELECT t.town_id, t.town, t.country, t.country_name, t.cell_id, s.run_date, s.warnings,
         s.rain_3d_max_mm, s.heat_3d_max_c, s.gust_3d_max_kmh, s.enso_phase, s.enso_anomaly,
         l.language, u.user_type, u.audience
  FROM ${silver_schema}.dim_town t
  JOIN ${gold_schema}.location_weather_summary s ON s.cell_id = t.cell_id
  CROSS JOIN (VALUES ('es'), ('en')) AS l(language)
  CROSS JOIN (VALUES ('citizen', 'residents (general public)'),
                     ('farmer', 'farmers and rural producers'),
                     ('municipality', 'municipal emergency officials')) AS u(user_type, audience)
),
prompts AS (
  SELECT *, concat(
    'You write short preventive weather advisories for a civil protection agency.\n',
    'Audience: ', audience, '. Language: ', CASE language WHEN 'es' THEN 'Spanish' ELSE 'English' END, '.\n',
    'Location: ', town, ', ', country_name,
    '. Forecast for the next 3 days (use only these numbers, add no others):\n',
    '- max daily rain: ', cast(round(rain_3d_max_mm) AS INT), ' mm; max apparent temperature: ',
    cast(round(heat_3d_max_c) AS INT), ' C; max wind gusts: ', cast(round(gust_3d_max_kmh) AS INT), ' km/h\n',
    '- active warnings: ', warnings, '\n',
    '- ENSO: ', enso_phase, ', ONI ', format_string('%+.2f', enso_anomaly),
    ' (seasonal context only; do not say it causes this forecast)\n',
    'Write 2-4 sentences, max 70 words: the main risk, or that no warning is active, then 2 concrete ',
    'preventive actions for this audience. The only numbers you may write are the forecast values ',
    'above: no times of day, durations, dates or phone numbers. No greeting, no heading.') AS prompt,
    array('3', string(cast(round(rain_3d_max_mm) AS INT)), string(cast(round(heat_3d_max_c) AS INT)),
          string(cast(round(gust_3d_max_kmh) AS INT)), format_string('%.2f', abs(enso_anomaly))) AS allowed_numbers
  FROM base
),
first_try AS (
  SELECT *, ai_query('${llm_endpoint}', prompt,
    modelParameters => named_struct('temperature', 0.2, 'max_tokens', 220), failOnError => false) AS r
  FROM prompts
),
with_fallback AS (
  SELECT *, CASE WHEN r.result IS NULL THEN ai_query('${llm_fallback_endpoint}', prompt,
    modelParameters => named_struct('temperature', 0.2, 'max_tokens', 220), failOnError => false) END AS f
  FROM first_try
),
checked AS (
  SELECT *, coalesce(r.result, f.result) AS advisory_text,
    array_except(regexp_extract_all(
      regexp_replace(replace(coalesce(r.result, f.result), ',', '.'), '(?i)24 ?(hours|horas|h)', ''),
      '[0-9]+([.][0-9]+)?', 0), allowed_numbers) AS unexpected_numbers
  FROM with_fallback
)
SELECT town_id, town, country, cell_id, run_date, language, user_type, warnings,
       rain_3d_max_mm, heat_3d_max_c, gust_3d_max_kmh, enso_phase, enso_anomaly,
       advisory_text, coalesce(size(unexpected_numbers) = 0, false) AS numbers_ok, unexpected_numbers,
       CASE WHEN r.result IS NOT NULL THEN '${llm_endpoint}'
            WHEN f.result IS NOT NULL THEN '${llm_fallback_endpoint}' END AS model,
       r.errorMessage AS primary_error, prompt
FROM checked;
