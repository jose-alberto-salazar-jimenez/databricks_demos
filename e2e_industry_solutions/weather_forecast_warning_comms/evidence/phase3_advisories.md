# Evidence - Phase 3: Risk flags and advisories (GenAI)

Dev catalog, run_date 2026-11-27. Pipeline update `bda90996` (advisories refresh): COMPLETED, 4.6 min.

## Risk flags (`gold.location_weather_summary`, next 3 days)

Thresholds: rain >= 50 mm/day, apparent max >= 41 C, gusts >= 60 km/h. A 35 C heat threshold
flagged most tropical lowland cells (2,212 of 2,861 in Colombia), so it was raised to 41 C.

| Country | Cells | Heavy rain | Extreme heat | Strong wind | Any flag |
| --- | --- | --- | --- | --- | --- |
| COL | 2,861 | 76 | 183 | 9 | 266 |
| CRI | 520 | 96 | 5 | 66 | 160 |
| ECU | 632 | 103 | 15 | 0 | 109 |
| PAN | 747 | 8 | 29 | 20 | 57 |
| PER | 3,281 | 62 | 79 | 12 | 151 |

743 of 8,041 cells have at least one flag.

## Towns (`silver.dim_town`)

109 towns (GeoNames, population >= 100,000 or top 5 per country): COL 56, PER 26, ECU 17,
CRI 5, PAN 5. All mapped to a land cell; farthest 19.8 km.

## Advisories (`gold.advisories`)

654 rows = 109 towns x 2 languages x 3 user types; 19 towns (114 rows) have an active warning.
`system.ai.qwen3-next-80b-a3b-instruct`: 654 generated, 0 errors, fallback unused; 32-64 words.

Guardrail: every number in the text must be an injected value (rain, heat, gusts, ONI, "3"
days; "24 hours/horas" allowed as daily rain).

| Step | Advisories with other numbers |
| --- | --- |
| First prompt | 79 of 654 (times of day, e.g. "11 a.m.") |
| Prompt forbids times, durations, dates, phone numbers | 5 (4x "in 24 hours", 1x "40 C") |
| `numbers_ok` column + expectation `numbers_from_forecast` | 653 pass, 1 fail ("10 a.m. y 4 p.m.") |

`numbers_ok` (SQL) agrees with an independent Python check on all 654 rows. The app shows only
`numbers_ok` rows. Text changes on every run, so the failing row changes too.

## Reviewed sample: Piura (Peru), heavy rain, 116 mm, apparent 39 C, gusts 33 km/h

* es/citizen: Se esperan lluvias intensas con hasta 116 mm, temperatura aparente de 39 °C y ráfagas de viento de hasta 33 km/h. Eviten caminar por zonas bajas o cerca de ríos, y aseguren techos y ventanas para evitar filtraciones. No dejen objetos al aire libre que puedan volverse proyectiles con el viento.
* es/farmer: Riesgo por lluvia intensa hasta 116 mm y temperatura aparente de 39 °C. Proteja cultivos con coberturas y despeje canales de drenaje para evitar acumulaciones. Evite movilizar maquinaria en terrenos empapados por vientos hasta 33 km/h.
* es/municipality: Riesgo principal por lluvia intensa, con máximos de 116 mm y temperatura aparente de 39 °C. Verifique el drenaje urbano y asegure estructuras temporales contra vientos hasta 33 km/h. Mantenga equipos de respuesta listos para evacuaciones por inundaciones repentinas.
* en/citizen: Heavy rain is expected, with up to 116 mm in 24 hours and apparent temperatures reaching 39 C. Avoid walking or driving through flooded areas, and secure loose outdoor items that could become hazards in wind gusts up to 33 km/h. Stay informed through official channels.
* en/farmer: Heavy rain is expected, with up to 116 mm and apparent temperatures reaching 39 C. Secure stored crops and livestock feed in elevated, waterproof areas. Reinforce drainage around fields and animal shelters to prevent flooding and mudslides from wind gusts up to 33 km/h.
* en/municipality: Heavy rain poses the main risk, with up to 116 mm forecasted and apparent temperatures reaching 39 C. Ensure drainage systems are cleared of debris and verify emergency shelters are ready for potential flooding. Monitor wind gusts up to 33 km/h for loose debris and unstable structures.

Review: numbers match the inputs in 6/6, actions fit each audience, no ENSO causal claim.
Issues: 2/6 (both farmer texts) wrongly link wind to soaked ground or mudslides, and all 6
mention 33 km/h gusts with no wind warning. Next: mention only values tied to an active
warning, and score a sample with an LLM judge.
