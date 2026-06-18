# Analisis de dias especiales y desviaciones

## Alcance

- Unidad de evaluacion principal: observacion diaria `linea + estacion` en test.
- La comparacion principal es `baseline_naive_seasonal_weekly` frente a `tabular_hgbr + strict_available`.
- `forecastable_scenario` se mantiene como escenario de analisis: usa eventos, meteorologia y servicio planificado solo si existen como forecast, planificacion o hipotesis explicita.
- Las variables externas se usan aqui tambien para segmentar errores de `strict_available`; eso no implica que hayan sido usadas como inputs por ese modelo.

## Puntos de control

1. Los mayores errores agregados frente al baseline estacional se concentran en festivos y cambios fuertes de patron: 2025-12-25, 2026-04-05, 2026-04-06, 2025-12-24, 2026-03-29, 2026-01-06.
2. Esos errores son explicables sobre todo por calendario, festivos y Semana Santa; eventos y meteorologia aportan segmentos utiles, pero con menos cobertura positiva.
3. `strict_available` mejora el WAPE del baseline estacional en 48.9% para D+1 y 45.3% para D+7 a nivel serie-estacion-dia.
4. `forecastable_scenario` mejora adicionalmente a `strict_available` en -2.4% para D+1 y 0.8% para D+7, pero depende de variables que no deben asumirse disponibles en operativa sin feed o escenario.
5. No se recomienda entrenar todavia un residual/uplift como modelo principal: las desviaciones fuertes ya mejoran mucho con el tabular directo, y el fallo pendiente mas claro son dias donde el baseline acierta y el tabular sobrecorrige.
6. Recomendacion actual: mantener `strict_available` como variante operativa principal, mantener `forecastable_scenario` como analisis de escenarios y priorizar features/calidad externa antes que otro modelo.

## Metricas principales

### Nivel observacion serie-estacion-dia

| model_label | horizon | variant | mae | rmse | wape | smape | row_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Naive simple | D+1 | strict_available | 751.8064 | 1231.9797 | 0.2539 | 0.3266 | 3420 |
| Naive estacional | D+1 | strict_available | 508.6716 | 1174.6647 | 0.1718 | 0.1896 | 3420 |
| Tabular propuesto | D+1 | strict_available | 252.3108 | 526.2535 | 0.0877 | 0.1021 | 3420 |
| Tabular forecastable | D+1 | forecastable_scenario | 258.3521 | 515.3333 | 0.0898 | 0.1044 | 3420 |
| Naive simple | D+7 | strict_available | 508.6716 | 1174.6647 | 0.1718 | 0.1896 | 3420 |
| Naive estacional | D+7 | strict_available | 508.6716 | 1174.6647 | 0.1718 | 0.1896 | 3420 |
| Tabular propuesto | D+7 | strict_available | 270.1368 | 554.3326 | 0.0939 | 0.1094 | 3420 |
| Tabular forecastable | D+7 | forecastable_scenario | 267.8526 | 526.9193 | 0.0931 | 0.1090 | 3420 |

### Nivel agregado dia-red

| model_label | horizon | variant | mae | rmse | wape | smape | row_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Naive simple | D+1 | strict_available | 13071.0667 | 18227.8596 | 0.2324 | 0.2803 | 180 |
| Naive estacional | D+1 | strict_available | 7965.9278 | 13141.9581 | 0.1416 | 0.1574 | 180 |
| Tabular propuesto | D+1 | strict_available | 3341.7508 | 5969.1089 | 0.0612 | 0.0708 | 180 |
| Tabular forecastable | D+1 | forecastable_scenario | 3725.3911 | 5805.4181 | 0.0682 | 0.0787 | 180 |
| Naive simple | D+7 | strict_available | 7965.9278 | 13141.9581 | 0.1416 | 0.1574 | 180 |
| Naive estacional | D+7 | strict_available | 7965.9278 | 13141.9581 | 0.1416 | 0.1574 | 180 |
| Tabular propuesto | D+7 | strict_available | 3566.4576 | 5719.2904 | 0.0653 | 0.0754 | 180 |
| Tabular forecastable | D+7 | forecastable_scenario | 3456.6496 | 5384.3045 | 0.0633 | 0.0735 | 180 |

## Segmentos

| horizon_days | segment_name | row_count | baseline_seasonal_mae | baseline_seasonal_rmse | baseline_seasonal_wape | baseline_seasonal_smape | tabular_strict_mae | tabular_strict_rmse | tabular_strict_wape | tabular_strict_smape | tabular_strict_relative_wape_improvement_vs_seasonal | tabular_forecastable_wape | forecastable_relative_wape_improvement_vs_strict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | all_test_rows | 2850 | 523.7175 | 1238.2423 | 0.1812 | 0.1968 | 279.7448 | 571.3921 | 0.0968 | 0.1124 | 0.4658 | 0.0986 | -0.0182 |
| 1 | bad_weather_days | 323 | 544.8019 | 1066.3128 | 0.2117 | 0.2416 | 519.9954 | 1068.4225 | 0.2020 | 0.2367 | 0.0455 | 0.1916 | 0.0517 |
| 1 | event_days | 0 |  |  |  |  |  |  |  |  |  |  |  |
| 1 | heavy_rain_days | 114 | 826.9649 | 1511.1303 | 0.3608 | 0.3653 | 687.8479 | 1354.7881 | 0.3001 | 0.3297 | 0.1682 | 0.2550 | 0.1505 |
| 1 | high_impact_event_days | 0 |  |  |  |  |  |  |  |  |  |  |  |
| 1 | holidays | 133 | 1464.3759 | 2426.4685 | 0.6466 | 0.5346 | 392.5683 | 634.9891 | 0.1733 | 0.2134 | 0.7319 | 0.1700 | 0.0191 |
| 1 | normal_days | 2090 | 368.5005 | 882.9611 | 0.1245 | 0.1457 | 204.7777 | 362.7565 | 0.0692 | 0.0791 | 0.4443 | 0.0742 | -0.0720 |
| 1 | postholidays | 133 | 726.0075 | 1339.4789 | 0.2626 | 0.2755 | 485.6722 | 811.5149 | 0.1757 | 0.1702 | 0.3310 | 0.1401 | 0.2026 |
| 1 | preholidays | 133 | 971.6090 | 1968.9064 | 0.2972 | 0.2679 | 448.8730 | 887.2714 | 0.1373 | 0.1354 | 0.5380 | 0.1879 | -0.3687 |
| 1 | semana_santa | 171 | 1802.6667 | 3223.5836 | 0.4839 | 0.4351 | 586.2876 | 998.8217 | 0.1574 | 0.1710 | 0.6748 | 0.1700 | -0.0801 |
| 1 | top_baseline_deviation_days | 380 | 1815.4158 | 2721.6593 | 0.6641 | 0.6777 | 512.9449 | 925.7223 | 0.1876 | 0.2100 | 0.7175 | 0.1734 | 0.0759 |
| 1 | top_tabular_worse_than_baseline_days | 608 | 292.4260 | 698.8739 | 0.1082 | 0.1320 | 406.8196 | 825.3482 | 0.1506 | 0.1820 | -0.3912 | 0.1432 | 0.0493 |
| 7 | all_test_rows | 2850 | 523.7175 | 1238.2423 | 0.1812 | 0.1968 | 300.7370 | 602.4291 | 0.1041 | 0.1214 | 0.4258 | 0.1032 | 0.0083 |
| 7 | bad_weather_days | 323 | 544.8019 | 1066.3128 | 0.2117 | 0.2416 | 473.7379 | 947.2255 | 0.1841 | 0.2310 | 0.1304 | 0.1763 | 0.0422 |
| 7 | event_days | 0 |  |  |  |  |  |  |  |  |  |  |  |
| 7 | heavy_rain_days | 114 | 826.9649 | 1511.1303 | 0.3608 | 0.3653 | 654.9109 | 1273.0996 | 0.2858 | 0.3380 | 0.2081 | 0.3168 | -0.1086 |
| 7 | high_impact_event_days | 0 |  |  |  |  |  |  |  |  |  |  |  |
| 7 | holidays | 133 | 1464.3759 | 2426.4685 | 0.6466 | 0.5346 | 581.8836 | 1012.7068 | 0.2569 | 0.2521 | 0.6026 | 0.2196 | 0.1451 |
| 7 | normal_days | 2090 | 368.5005 | 882.9611 | 0.1245 | 0.1457 | 226.7862 | 389.3946 | 0.0766 | 0.0894 | 0.3846 | 0.0782 | -0.0210 |
| 7 | postholidays | 133 | 726.0075 | 1339.4789 | 0.2626 | 0.2755 | 481.5379 | 813.2462 | 0.1742 | 0.1681 | 0.3367 | 0.1358 | 0.2204 |
| 7 | preholidays | 133 | 971.6090 | 1968.9064 | 0.2972 | 0.2679 | 511.9305 | 913.4804 | 0.1566 | 0.1537 | 0.4731 | 0.1540 | 0.0166 |
| 7 | semana_santa | 171 | 1802.6667 | 3223.5836 | 0.4839 | 0.4351 | 820.1422 | 1428.3820 | 0.2201 | 0.2147 | 0.5450 | 0.2234 | -0.0146 |
| 7 | top_baseline_deviation_days | 380 | 1815.4158 | 2721.6593 | 0.6641 | 0.6777 | 554.7215 | 967.6955 | 0.2029 | 0.2307 | 0.6944 | 0.2046 | -0.0083 |
| 7 | top_tabular_worse_than_baseline_days | 608 | 292.4260 | 698.8739 | 0.1082 | 0.1320 | 380.9758 | 736.1804 | 0.1410 | 0.1749 | -0.3028 | 0.1196 | 0.1520 |

## Top desviaciones agregadas

| analysis_scope | rank_type | rank_position | horizon_days | target_date | series_label | station_abbrev | is_holiday | is_semana_santa | event_day | bad_weather_day | y_true | y_pred_seasonal | y_pred_tabular_strict | seasonal_abs_error | seasonal_relative_error | seasonal_wape_contribution | real_baseline_ratio | real_minus_baseline | tabular_strict_error_delta_vs_seasonal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| network_day | baseline_seasonal_deviation | 1 | 1 | 2025-12-25 |  |  | true | false | false | false | 21325.0000 | 74265.0000 | 22592.2835 | 52940.0000 | 2.4825 | 0.0064 | 0.2871 | -52940.0000 | -51672.7165 |
| network_day | baseline_seasonal_deviation | 2 | 1 | 2026-04-05 |  |  | false | true | false | false | 33903.0000 | 81594.0000 | 29528.9983 | 47691.0000 | 1.4067 | 0.0058 | 0.4155 | -47691.0000 | -43316.9983 |
| network_day | baseline_seasonal_deviation | 3 | 1 | 2026-04-06 |  |  | false | true | false | false | 49183.0000 | 96681.0000 | 56187.2440 | 47498.0000 | 0.9657 | 0.0058 | 0.5087 | -47498.0000 | -40493.7560 |
| network_day | baseline_seasonal_deviation | 4 | 1 | 2025-12-24 |  |  | false | false | false | false | 29621.0000 | 73707.0000 | 33634.7812 | 44086.0000 | 1.4883 | 0.0054 | 0.4019 | -44086.0000 | -40072.2188 |
| network_day | baseline_seasonal_deviation | 5 | 1 | 2026-03-29 |  |  | false | true | false | false | 81594.0000 | 40291.0000 | 72712.2532 | 41303.0000 | 0.5062 | 0.0050 | 2.0251 | 41303.0000 | -32421.2532 |
| network_day | baseline_seasonal_deviation | 6 | 1 | 2026-01-06 |  |  | true | false | false | false | 21061.0000 | 59265.0000 | 18187.4167 | 38204.0000 | 1.8140 | 0.0046 | 0.3554 | -38204.0000 | -35330.4167 |
| network_day | baseline_seasonal_deviation | 7 | 1 | 2026-01-08 |  |  | false | false | false | false | 58548.0000 | 22156.0000 | 64522.3570 | 36392.0000 | 0.6216 | 0.0044 | 2.6425 | 36392.0000 | -30417.6430 |
| network_day | baseline_seasonal_deviation | 8 | 1 | 2026-02-11 |  |  | false | false | false | false | 58767.0000 | 22611.0000 | 55964.0387 | 36156.0000 | 0.6152 | 0.0044 | 2.5990 | 36156.0000 | -33353.0387 |
| network_day | baseline_seasonal_deviation | 9 | 1 | 2026-01-13 |  |  | false | false | false | false | 57040.0000 | 21061.0000 | 57012.8602 | 35979.0000 | 0.6308 | 0.0044 | 2.7083 | 35979.0000 | -35951.8602 |
| network_day | baseline_seasonal_deviation | 10 | 1 | 2026-05-08 |  |  | false | false | false | false | 69223.0000 | 36282.0000 | 68039.2587 | 32941.0000 | 0.4759 | 0.0040 | 1.9079 | 32941.0000 | -31757.2587 |
| network_day | baseline_seasonal_deviation | 11 | 1 | 2026-03-30 |  |  | false | true | false | false | 96681.0000 | 64313.0000 | 77535.0758 | 32368.0000 | 0.3348 | 0.0039 | 1.5033 | 32368.0000 | -13222.0758 |
| network_day | baseline_seasonal_deviation | 12 | 1 | 2026-05-01 |  |  | true | false | false | false | 36282.0000 | 66446.0000 | 35778.2578 | 30164.0000 | 0.8314 | 0.0037 | 0.5460 | -30164.0000 | -29660.2578 |

## Variables externas

| variable_group | source | availability | model_usage | granularity | coverage_ratio_test_rows | positive_row_count | positive_day_count | leakage_risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| calendario_festivos_semana_santa | external_daily_features | disponible antes de predecir | strict_available y forecastable_scenario | dia-red, replicado a serie | 1.0000 | 456 | 24 | bajo si procede de calendario oficial |
| eventos_planificados | events_phase2a_series_daily | forecast/escenario | solo forecastable_scenario | dia-linea-estacion | 1.0000 | 0 | 0 | medio si el calendario se completa a posteriori |
| aforo_estimado | events_phase2a_series_daily | forecast/hipotesis explicita | solo forecastable_scenario | dia-linea-estacion | 1.0000 | 0 | 0 | medio-alto si el aforo usado no estaba previsto |
| eventos_por_estacion_serie | events_phase2a_series_daily | forecast/escenario | solo forecastable_scenario | dia-linea-estacion | 1.0000 | 0 | 0 | medio por dependencias de mapeo y carga previa |
| meteorologia | external_daily_features | forecast o escenario; observado es posteriori | solo forecastable_scenario | dia-red, replicado a serie | 1.0000 | 1444 | 76 | alto si se usa meteorologia observada como forecast |
| servicio_planificado | services_line_daily | planificacion previa | solo forecastable_scenario | dia-linea | 1.0000 | 2850 | 150 | bajo-medio si se mantiene planificado, no ejecutado |
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