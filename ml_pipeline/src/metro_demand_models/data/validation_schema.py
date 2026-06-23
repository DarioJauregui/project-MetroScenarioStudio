from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series


class ValidationSchema(pa.DataFrameModel):
    fecha_validacion: Series[pd.DatetimeTZDtype] = pa.Field(
        dtype_kwargs={"tz": "Europe/Madrid"},
        nullable=True,
    )
    linea: Series[str] = pa.Field(coerce=True)
    estacion: Series[str] = pa.Field(coerce=True)
    cod_eq: Series[str] = pa.Field(coerce=True)
    tipo_validacion: Series[str] = pa.Field(coerce=True)
    tipo_titulo: Series[str] = pa.Field(coerce=True)
    id_tarjeta: Series[str] = pa.Field(coerce=True)
    num_tarjeta: Series[str] = pa.Field(coerce=True, nullable=True)
    dinero_deducido: Series[float] = pa.Field(ge=0.0, coerce=True)
    saldo_restante: Series[float] = pa.Field(coerce=True)
    viajes_deducidos: Series[int] = pa.Field(ge=0, coerce=True)
    fecha_validacion_hora_estimada: Series[bool] = pa.Field(coerce=True)
    fecha_generacion: Series[pd.DatetimeTZDtype] = pa.Field(
        dtype_kwargs={"tz": "Europe/Madrid"},
        nullable=True,
    )
    rango_desde: Series[pd.DatetimeTZDtype] = pa.Field(
        dtype_kwargs={"tz": "Europe/Madrid"},
        nullable=True,
    )
    rango_hasta: Series[pd.DatetimeTZDtype] = pa.Field(
        dtype_kwargs={"tz": "Europe/Madrid"},
        nullable=True,
    )
    rango_fechas_raw: Series[str] = pa.Field(coerce=True, nullable=True)
    dia: Series[str] = pa.Field(nullable=False)
    archivo_origen: Series[str] = pa.Field(coerce=True)
    fecha_validacion_iso: Series[str] = pa.Field(coerce=True, nullable=True)
    fecha_generacion_iso: Series[str] = pa.Field(coerce=True, nullable=True)
    rango_desde_iso: Series[str] = pa.Field(coerce=True, nullable=True)
    rango_hasta_iso: Series[str] = pa.Field(coerce=True, nullable=True)
    _orden_manifest: Series[int] = pa.Field(coerce=True)
    idtarjeta: Series[object] = pa.Field(nullable=True)

    class Config:
        strict = False
        coerce = True
