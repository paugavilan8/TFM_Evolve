"""
Fase 2 (pasos 1 y 2) — Feature engineering + BASELINE
TFM Pau Gavilán — Predicción de demanda para taxistas autónomos

Qué hace:
  1. Construye la tabla con la que aprenderán los modelos: features de calendario,
     codificación cíclica de la hora, festivos y — lo más importante — LAGS
     (demanda de la misma zona hace 1h, 24h y 168h) + medias móviles.
  2. Hace la DIVISIÓN TEMPORAL (entrena con ene-oct, valida con nov-dic).
  3. Calcula el BASELINE ingenuo ("misma hora, semana anterior") con MAE / RMSE / WAPE.
     → Ese es el número que Prophet / LightGBM / LSTM tendrán que batir en la Fase 2.

Entrada:  data/processed/demanda_nyc_2023.parquet   (de la Fase 1)
Salida:   data/gold/demanda_features_2023.parquet    (lista para modelar)

Ejecuta en TU máquina, con el venv activado:
    python -m pip install pandas pyarrow numpy holidays
    python fase2_features_baseline.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

# Raíz del proyecto (este script vive en pipeline/), para que las rutas de datos
# no dependan del directorio desde el que lo lances.
ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "processed" / "demanda_nyc_2023.parquet"
OUT_PATH = ROOT / "data" / "gold" / "demanda_features_2023.parquet"
TEST_START = "2023-11-01"   # división TEMPORAL: nunca al azar (el modelo no debe "ver el futuro")

# ----------------------------- Cargar -----------------------------
print("1) Cargando tabla de demanda...")
df = pd.read_parquet(IN_PATH)
df["fecha"] = pd.to_datetime(df["fecha"])
df["datetime"] = df["fecha"] + pd.to_timedelta(df["hora"], unit="h")
df = df.sort_values(["zona", "datetime"]).reset_index(drop=True)

# ----------------------- Features de calendario -----------------------
print("2) Construyendo features de calendario...")
df["mes"] = df["fecha"].dt.month
df["dia_mes"] = df["fecha"].dt.day
df["es_finde"] = df["es_finde"].astype(int)
# Codificación cíclica de la hora: así las 23h y las 0h quedan "cerca"
df["hora_sin"] = np.sin(2 * np.pi * df["hora"] / 24)
df["hora_cos"] = np.cos(2 * np.pi * df["hora"] / 24)

# Festivos de EE. UU. (con fallback por si la librería 'holidays' no está instalada)
try:
    import holidays
    us = holidays.UnitedStates(years=2023)
    df["es_festivo"] = df["fecha"].dt.date.isin(us).astype(int)
except Exception:
    festivos_2023 = {
        "2023-01-01", "2023-01-02", "2023-01-16", "2023-02-20", "2023-05-29",
        "2023-06-19", "2023-07-04", "2023-09-04", "2023-10-09", "2023-11-10",
        "2023-11-11", "2023-11-23", "2023-12-25",
    }
    df["es_festivo"] = df["fecha"].dt.strftime("%Y-%m-%d").isin(festivos_2023).astype(int)

# ----------------------- Lags y medias móviles -----------------------
# La rejilla es regular y completa (zona × horas consecutivas), así que shift(n) = n horas.
# transform(...) mantiene el cálculo DENTRO de cada zona (no cruza fronteras de zona).
print("3) Construyendo lags y medias móviles (esto es lo que da la predicción)...")
gd = df.groupby("zona")["demanda"]
df["lag_1h"] = gd.shift(1)
df["lag_24h"] = gd.shift(24)
df["lag_168h"] = gd.shift(168)   # misma hora, semana anterior
df["roll_24h"] = gd.transform(lambda s: s.shift(1).rolling(24).mean())
df["roll_168h"] = gd.transform(lambda s: s.shift(1).rolling(168).mean())

# ----------------------- División temporal + baseline -----------------------
print("4) División temporal y baseline...")
df["set"] = np.where(df["datetime"] >= TEST_START, "test", "train")


def metricas(y, yhat):
    y = np.asarray(y, dtype=float)
    yhat = np.asarray(yhat, dtype=float)
    mae = np.mean(np.abs(y - yhat))
    rmse = np.sqrt(np.mean((y - yhat) ** 2))
    wape = np.sum(np.abs(y - yhat)) / np.sum(y) if np.sum(y) > 0 else np.nan
    return mae, rmse, wape


test = df[df["set"] == "test"].dropna(subset=["lag_168h"])
mae, rmse, wape = metricas(test["demanda"], test["lag_168h"])

print("\n" + "=" * 52)
print("BASELINE  ·  'misma hora, semana anterior'  ·  test nov-dic")
print("=" * 52)
print(f"  MAE  = {mae:.3f}   (error medio en nº de carreras)")
print(f"  RMSE = {rmse:.3f}   (penaliza los picos mal predichos)")
print(f"  WAPE = {wape * 100:.1f}%   (error porcentual robusto a ceros)")
print("=" * 52)
print("→ ESTE es el número que LightGBM / Prophet / LSTM deben batir.\n")

# ----------------------- Guardar -----------------------
FEATURES = [
    "hora", "hora_sin", "hora_cos", "dia_semana", "es_finde", "mes", "dia_mes",
    "es_festivo", "zona", "lag_1h", "lag_24h", "lag_168h", "roll_24h", "roll_168h",
]
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(OUT_PATH, index=False)

n_train = (df["set"] == "train").sum()
n_test = (df["set"] == "test").sum()
print(f"Tabla de features guardada: {OUT_PATH}")
print(f"  Filas: {len(df):,}  (train: {n_train:,} | test: {n_test:,})")
print(f"  Target: 'demanda'")
print(f"  {len(FEATURES)} features: {FEATURES}")
print("\nNota: las primeras 168 h de cada zona tienen lags vacíos (NaN);")
print("el script de modelado hará dropna() sobre esas columnas antes de entrenar.")
