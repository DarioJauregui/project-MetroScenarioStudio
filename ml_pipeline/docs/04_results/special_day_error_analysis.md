# Analisis de dias especiales y desviaciones

## Alcance

- Unidad de evaluacion principal: observacion diaria `linea + estacion` en test.
- La comparacion principal es `baseline_naive_seasonal_weekly` frente a `tabular_hgbr + strict_available`.
- `forecastable_scenario` se mantiene como escenario de analisis: usa eventos, meteorologia y servicio planificado solo si existen como forecast, planificacion o hipotesis explicita.
- Las variables externas se usan aqui tambien para segmentar errores de `strict_available`; eso no implica que hayan sido usadas como inputs por ese modelo.

## Puntos de control

1. Los mayores errores agregados frente al baseline estacional se concentran en festivos y cambios fuertes de patron: 2025-12-25, 2026-04-05, 2026-04-06, 2026-03-29, 2026-01-06, 2026-01-08.
2. Esos errores son explicables sobre todo por calendario, festivos y Semana Santa; eventos y meteorologia aportan segmentos utiles, pero con menos cobertura positiva.
3. `strict_available` mejora el WAPE del baseline estacional en 48.2% para D+1 y 44.7% para D+7 a nivel serie-estacion-dia.
4. `forecastable_scenario` mejora adicionalmente a `strict_available` en -0.2% para D+1 y 5.6% para D+7, pero depende de variables que no deben asumirse disponibles en operativa sin feed o escenario.
5. No se recomienda entrenar todavia un residual/uplift como modelo principal: las desviaciones fuertes ya mejoran mucho con el tabular directo, y el fallo pendiente mas claro son dias donde el baseline acierta y el tabular sobrecorrige.
6. Recomendacion actual: mantener `strict_available` como variante operativa principal, mantener `forecastable_scenario` como analisis de escenarios y priorizar features/calidad externa antes que otro modelo.

## Metricas principales

### Nivel observacion serie-estacion-dia

| model_label | horizon | variant | mae | rmse | wape | smape | row_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Naive simple | D+1 | strict_available | 751.8064 | 1231.9797 | 0.2539 | 0.3266 | 3420 |
| Naive estacional | D+1 | strict_available | 508.6716 | 1174.6647 | 0.1718 | 0.1896 | 3420 |
| Tabular propuesto | D+1 | strict_available | 256.4940 | 552.0221 | 0.0890 | 0.1023 | 3420 |
| Tabular forecastable | D+1 | forecastable_scenario | 257.0609 | 506.5568 | 0.0892 | 0.1030 | 3420 |
| Naive simple | D+7 | strict_available | 508.6716 | 1174.6647 | 0.1718 | 0.1896 | 3420 |
| Naive estacional | D+7 | strict_available | 508.6716 | 1174.6647 | 0.1718 | 0.1896 | 3420 |
| Tabular propuesto | D+7 | strict_available | 273.6762 | 555.2667 | 0.0950 | 0.1092 | 3420 |
| Tabular forecastable | D+7 | forecastable_scenario | 258.4265 | 488.1931 | 0.0897 | 0.1045 | 3420 |

### Nivel agregado dia-red

| model_label | horizon | variant | mae | rmse | wape | smape | row_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Naive simple | D+1 | strict_available | 13071.0667 | 18227.8596 | 0.2324 | 0.2803 | 180 |
| Naive estacional | D+1 | strict_available | 7965.9278 | 13141.9581 | 0.1416 | 0.1574 | 180 |
| Tabular propuesto | D+1 | strict_available | 3544.1992 | 6282.2927 | 0.0647 | 0.0742 | 180 |
| Tabular forecastable | D+1 | forecastable_scenario | 3717.4771 | 5894.3255 | 0.0679 | 0.0775 | 180 |
| Naive simple | D+7 | strict_available | 7965.9278 | 13141.9581 | 0.1416 | 0.1574 | 180 |
| Naive estacional | D+7 | strict_available | 7965.9278 | 13141.9581 | 0.1416 | 0.1574 | 180 |
| Tabular propuesto | D+7 | strict_available | 3781.2117 | 5985.4487 | 0.0691 | 0.0784 | 180 |
| Tabular forecastable | D+7 | forecastable_scenario | 3362.8267 | 5134.4400 | 0.0614 | 0.0704 | 180 |

## Segmentos

| horizon_days | segment_name | row_count | baseline_seasonal_mae | baseline_seasonal_rmse | baseline_seasonal_wape | baseline_seasonal_smape | tabular_strict_mae | tabular_strict_rmse | tabular_strict_wape | tabular_strict_smape | tabular_strict_relative_wape_improvement_vs_seasonal | tabular_forecastable_wape | forecastable_relative_wape_improvement_vs_strict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | all_test_rows | 2755 | 511.3111 | 1230.9174 | 0.1762 | 0.1910 | 284.5195 | 596.0091 | 0.0980 | 0.1129 | 0.4435 | 0.0958 | 0.0228 |
| 1 | bad_weather_days | 304 | 543.4704 | 1060.6765 | 0.2072 | 0.2394 | 534.8241 | 1105.8029 | 0.2039 | 0.2376 | 0.0159 | 0.2016 | 0.0113 |
| 1 | event_days | 0 |  |  |  |  |  |  |  |  |  |  |  |
| 1 | heavy_rain_days | 114 | 826.9649 | 1511.1303 | 0.3608 | 0.3653 | 680.8667 | 1400.1412 | 0.2971 | 0.3210 | 0.1767 | 0.2578 | 0.1321 |
| 1 | high_impact_event_days | 0 |  |  |  |  |  |  |  |  |  |  |  |
| 1 | holidays | 133 | 1464.3759 | 2426.4685 | 0.6466 | 0.5346 | 425.2776 | 776.7655 | 0.1878 | 0.2082 | 0.7096 | 0.1512 | 0.1949 |
| 1 | normal_days | 2033 | 364.5229 | 884.4858 | 0.1234 | 0.1440 | 206.7824 | 365.5061 | 0.0700 | 0.0802 | 0.4327 | 0.0718 | -0.0268 |
| 1 | postholidays | 133 | 726.0075 | 1339.4789 | 0.2626 | 0.2755 | 498.4663 | 828.9924 | 0.1803 | 0.1778 | 0.3134 | 0.1399 | 0.2239 |
| 1 | preholidays | 114 | 746.8246 | 1836.0629 | 0.2101 | 0.1586 | 512.3777 | 991.8344 | 0.1442 | 0.1439 | 0.3139 | 0.1640 | -0.1379 |
| 1 | semana_santa | 171 | 1802.6667 | 3223.5836 | 0.4839 | 0.4351 | 643.4888 | 1170.4893 | 0.1727 | 0.1819 | 0.6430 | 0.1726 | 0.0008 |
| 1 | top_baseline_deviation_days | 380 | 1751.8447 | 2679.4513 | 0.6508 | 0.6721 | 605.7174 | 1177.4140 | 0.2250 | 0.2551 | 0.6542 | 0.2022 | 0.1013 |
| 1 | top_tabular_worse_than_baseline_days | 551 | 329.6388 | 764.7396 | 0.1150 | 0.1385 | 447.0750 | 885.8710 | 0.1560 | 0.1928 | -0.3563 | 0.1358 | 0.1300 |
| 7 | all_test_rows | 2755 | 511.3111 | 1230.9174 | 0.1762 | 0.1910 | 306.7504 | 600.4739 | 0.1057 | 0.1218 | 0.4001 | 0.0990 | 0.0639 |
| 7 | bad_weather_days | 304 | 543.4704 | 1060.6765 | 0.2072 | 0.2394 | 457.8558 | 892.4784 | 0.1745 | 0.2229 | 0.1575 | 0.1638 | 0.0618 |
| 7 | event_days | 0 |  |  |  |  |  |  |  |  |  |  |  |
| 7 | heavy_rain_days | 114 | 826.9649 | 1511.1303 | 0.3608 | 0.3653 | 648.7117 | 1210.5413 | 0.2830 | 0.3358 | 0.2156 | 0.2636 | 0.0687 |
| 7 | high_impact_event_days | 0 |  |  |  |  |  |  |  |  |  |  |  |
| 7 | holidays | 133 | 1464.3759 | 2426.4685 | 0.6466 | 0.5346 | 566.3098 | 939.1229 | 0.2501 | 0.2460 | 0.6133 | 0.2076 | 0.1696 |
| 7 | normal_days | 2033 | 364.5229 | 884.4858 | 0.1234 | 0.1440 | 237.0635 | 405.2385 | 0.0802 | 0.0918 | 0.3497 | 0.0770 | 0.0400 |
| 7 | postholidays | 133 | 726.0075 | 1339.4789 | 0.2626 | 0.2755 | 496.3436 | 846.9019 | 0.1795 | 0.1764 | 0.3163 | 0.1328 | 0.2603 |
| 7 | preholidays | 114 | 746.8246 | 1836.0629 | 0.2101 | 0.1586 | 484.1164 | 815.0893 | 0.1362 | 0.1243 | 0.3518 | 0.1371 | -0.0067 |
| 7 | semana_santa | 171 | 1802.6667 | 3223.5836 | 0.4839 | 0.4351 | 823.9648 | 1412.1339 | 0.2212 | 0.2298 | 0.5429 | 0.2071 | 0.0635 |
| 7 | top_baseline_deviation_days | 380 | 1751.8447 | 2679.4513 | 0.6508 | 0.6721 | 622.2359 | 1092.7138 | 0.2312 | 0.2713 | 0.6448 | 0.2091 | 0.0955 |
| 7 | top_tabular_worse_than_baseline_days | 551 | 329.6388 | 764.7396 | 0.1150 | 0.1385 | 423.9411 | 777.9838 | 0.1480 | 0.1816 | -0.2861 | 0.1209 | 0.1828 |

## Top desviaciones agregadas

| analysis_scope | rank_type | rank_position | horizon_days | target_date | series_label | station_abbrev | is_holiday | is_semana_santa | event_day | bad_weather_day | y_true | y_pred_seasonal | y_pred_tabular_strict | seasonal_abs_error | seasonal_relative_error | seasonal_wape_contribution | real_baseline_ratio | real_minus_baseline | tabular_strict_error_delta_vs_seasonal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| network_day | baseline_seasonal_deviation | 1 | 1 | 2025-12-25 |  |  | true | false | false | false | 21325.0000 | 74265.0000 | 21815.3824 | 52940.0000 | 2.4825 | 0.0066 | 0.2871 | -52940.0000 | -52449.6176 |
| network_day | baseline_seasonal_deviation | 2 | 1 | 2026-04-05 |  |  | false | true | false | false | 33903.0000 | 81594.0000 | 31303.7088 | 47691.0000 | 1.4067 | 0.0060 | 0.4155 | -47691.0000 | -45091.7088 |
| network_day | baseline_seasonal_deviation | 3 | 1 | 2026-04-06 |  |  | false | true | false | false | 49183.0000 | 96681.0000 | 57164.0284 | 47498.0000 | 0.9657 | 0.0059 | 0.5087 | -47498.0000 | -39516.9716 |
| network_day | baseline_seasonal_deviation | 4 | 1 | 2026-03-29 |  |  | false | true | false | false | 81594.0000 | 40291.0000 | 65487.9966 | 41303.0000 | 0.5062 | 0.0052 | 2.0251 | 41303.0000 | -25196.9966 |
| network_day | baseline_seasonal_deviation | 5 | 1 | 2026-01-06 |  |  | true | false | false | false | 21061.0000 | 59265.0000 | 18622.1385 | 38204.0000 | 1.8140 | 0.0048 | 0.3554 | -38204.0000 | -35765.1385 |
| network_day | baseline_seasonal_deviation | 6 | 1 | 2026-01-08 |  |  | false | false | false | false | 58548.0000 | 22156.0000 | 66585.4501 | 36392.0000 | 0.6216 | 0.0046 | 2.6425 | 36392.0000 | -28354.5499 |
| network_day | baseline_seasonal_deviation | 7 | 1 | 2026-02-11 |  |  | false | false | false | false | 58767.0000 | 22611.0000 | 55780.2374 | 36156.0000 | 0.6152 | 0.0045 | 2.5990 | 36156.0000 | -33169.2374 |
| network_day | baseline_seasonal_deviation | 8 | 1 | 2026-01-13 |  |  | false | false | false | false | 57040.0000 | 21061.0000 | 57661.9561 | 35979.0000 | 0.6308 | 0.0045 | 2.7083 | 35979.0000 | -35357.0439 |
| network_day | baseline_seasonal_deviation | 9 | 1 | 2026-05-08 |  |  | false | false | false | false | 69223.0000 | 36282.0000 | 68378.5775 | 32941.0000 | 0.4759 | 0.0041 | 1.9079 | 32941.0000 | -32096.5775 |
| network_day | baseline_seasonal_deviation | 10 | 1 | 2026-03-30 |  |  | false | true | false | false | 96681.0000 | 64313.0000 | 77240.3910 | 32368.0000 | 0.3348 | 0.0040 | 1.5033 | 32368.0000 | -12927.3910 |
| network_day | baseline_seasonal_deviation | 11 | 1 | 2026-05-01 |  |  | true | false | false | false | 36282.0000 | 66446.0000 | 34501.3070 | 30164.0000 | 0.8314 | 0.0038 | 0.5460 | -30164.0000 | -28383.3070 |
| network_day | baseline_seasonal_deviation | 12 | 1 | 2026-02-14 |  |  | false | false | false | false | 57342.0000 | 32751.0000 | 47954.1873 | 24591.0000 | 0.4288 | 0.0031 | 1.7508 | 24591.0000 | -15203.1873 |

## Variables externas

| variable_group | source | availability | model_usage | granularity | coverage_ratio_test_rows | positive_row_count | positive_day_count | leakage_risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| calendario_festivos_semana_santa | external_daily_features | disponible antes de predecir | strict_available y forecastable_scenario | dia-red, replicado a serie | 1.0000 | 437 | 23 | bajo si procede de calendario oficial |
| eventos_planificados | events_phase2a_series_daily | forecast/escenario | solo forecastable_scenario | dia-linea-estacion | 1.0000 | 0 | 0 | medio si el calendario se completa a posteriori |
| aforo_estimado | events_phase2a_series_daily | forecast/hipotesis explicita | solo forecastable_scenario | dia-linea-estacion | 1.0000 | 0 | 0 | medio-alto si el aforo usado no estaba previsto |
| eventos_por_estacion_serie | events_phase2a_series_daily | forecast/escenario | solo forecastable_scenario | dia-linea-estacion | 1.0000 | 0 | 0 | medio por dependencias de mapeo y carga previa |
| meteorologia | external_daily_features | forecast o escenario; observado es posteriori | solo forecastable_scenario | dia-red, replicado a serie | 1.0000 | 1368 | 72 | alto si se usa meteorologia observada como forecast |
| servicio_planificado | services_line_daily | planificacion previa | solo forecastable_scenario | dia-linea | 1.0000 | 2755 | 145 | bajo-medio si se mantiene planificado, no ejecutado |
| incidencias_y_servicio_ejecutado | incidents_daily / used_service_xml_name | solo a posteriori | excluido del modelo principal | operativa ejecutada |  | 0 | 0 | alto |

## Implicaciones

- El baseline estacional falla de forma clara cuando un dia rompe el patron semanal normal. El tabular ya corrige gran parte de ese salto con calendario y autoregresivos.
- Los eventos de alto impacto y la meteorologia adversa deben seguir como variables de escenario hasta confirmar que existen previsiones fiables antes de inferencia.
- `incidents_daily` y `used_service_xml_name` deben mantenerse fuera del modelo principal porque describen ejecucion observada, no informacion disponible antes de predecir.
- Si se incorporan reglas nuevas, deben entrar primero en el preprocesamiento/foundation y despues propagarse a entrenamiento, evaluacion e inferencia; no deben aparecer solo en notebooks.

## Artefactos generados

- `segment_metrics_csv`: `artifacts/daily_modeling/metrics/segment_metrics.csv`
- `top_deviation_days_csv`: `artifacts/daily_modeling/metrics/top_deviation_days.csv`
- `segment_metrics_summary_md`: `docs/05_memory_support/assets/tables/segment_metrics_summary.md`
- `top_deviation_days_md`: `docs/05_memory_support/assets/tables/top_deviation_days.md`
- `tfm_main_results_summary_md`: `docs/05_memory_support/assets/tables/tfm_main_results_summary.md`