"""
Fase 2 (paso 3) — Entrenamiento y comparativa de modelos
TFM Pau Gavilán — Predicción de demanda para taxistas autónomos

Compara, sobre la MISMA división temporal (entrena ene-oct, valida nov-dic):
    Baseline ('misma hora, semana anterior')  →  LightGBM  →  Prophet

Cada modelo predice lo mismo: la demanda por (zona, hora) en el test, y se evalúa
con MAE / RMSE / WAPE. El objetivo es BATIR el baseline.

Entrada:  data/gold/demanda_features_2023.parquet   (de fase2_features_baseline.py)
Salida:   results/resultados_comparativa.csv          (tu tabla para la memoria)

Ejecuta en TU máquina, con el venv activado:
    python -m pip install lightgbm prophet pandas pyarrow numpy
    python fase2_modelos.py

Nota: LightGBM y Baseline se evalúan sobre TODAS las zonas del test.
Prophet se ajusta una serie por zona (es su forma natural), pero como eso es lento,
por defecto corre sobre una MUESTRA de zonas; para que la comparación sea justa,
en esa muestra se recalculan también Baseline y LightGBM (Tabla B).
"""

import logging
import warnings

from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

# Raíz del proyecto (este script vive en pipeline/), para que las rutas de datos
# no dependan del directorio desde el que lo lances.
ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "gold" / "demanda_features_2023.parquet"
RESULTS_DIR = ROOT / "results"
TARGET = "demanda"
FEATURES = [
    "hora", "hora_sin", "hora_cos", "dia_semana", "es_finde", "mes", "dia_mes",
    "es_festivo", "zona", "lag_1h", "lag_24h", "lag_168h", "roll_24h", "roll_168h",
]
SAMPLE_ZONES_PROPHET = 30   # nº de zonas (las de más demanda) para Prophet. Pon None para todas (muy lento).


def metricas(y, yhat):
    y = np.asarray(y, dtype=float)
    yhat = np.asarray(yhat, dtype=float)
    mae = np.mean(np.abs(y - yhat))
    rmse = np.sqrt(np.mean((y - yhat) ** 2))
    wape = np.sum(np.abs(y - yhat)) / np.sum(y) if np.sum(y) > 0 else np.nan
    return {"MAE": mae, "RMSE": rmse, "WAPE_%": wape * 100}


# ----------------------------- Cargar y dividir -----------------------------
print("1) Cargando tabla de features...")
df = pd.read_parquet(IN_PATH)
df = df.dropna(subset=FEATURES).reset_index(drop=True)

train = df[df["set"] == "train"]
test = df[df["set"] == "test"]
print(f"   train: {len(train):,} filas | test: {len(test):,} filas")

resultados = {}

# ----------------------------- Baseline -----------------------------
print("2) Baseline (misma hora, semana anterior)...")
resultados["Baseline"] = metricas(test[TARGET], test["lag_168h"])

# ----------------------------- LightGBM -----------------------------
print("3) Entrenando LightGBM (esto tarda un par de minutos)...")
from lightgbm import LGBMRegressor

X_train = train[FEATURES].copy()
X_test = test[FEATURES].copy()
X_train["zona"] = X_train["zona"].astype("category")
X_test["zona"] = X_test["zona"].astype("category")

lgbm = LGBMRegressor(
    objective="poisson",          # apropiado para conteos (demanda >= 0, muchos ceros)
    n_estimators=500,
    learning_rate=0.05,
    num_leaves=63,
    min_child_samples=50,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    n_jobs=-1,
)
lgbm.fit(X_train, train[TARGET], categorical_feature=["zona"])
pred_lgbm = np.clip(lgbm.predict(X_test), 0, None)   # nunca demanda negativa
resultados["LightGBM"] = metricas(test[TARGET], pred_lgbm)

# Importancia de variables (útil para la memoria)
imp = (pd.Series(lgbm.feature_importances_, index=FEATURES)
       .sort_values(ascending=False))
print("\n   Importancia de variables (top 6):")
for f, v in imp.head(6).items():
    print(f"     {f:12s} {v}")

# ----------------------------- Prophet (muestra de zonas) -----------------------------
print(f"\n4) Prophet — una serie por zona (muestra de {SAMPLE_ZONES_PROPHET} zonas)...")
from prophet import Prophet

zonas_top = (df.groupby("zona")[TARGET].sum().sort_values(ascending=False).index.tolist())
zonas_muestra = zonas_top if SAMPLE_ZONES_PROPHET is None else zonas_top[:SAMPLE_ZONES_PROPHET]

preds_prophet, y_true_p, idx_p = [], [], []
for i, z in enumerate(zonas_muestra, 1):
    tr = train[train["zona"] == z][["datetime", TARGET]].rename(columns={"datetime": "ds", TARGET: "y"})
    te = test[test["zona"] == z]
    if len(tr) < 168 or len(te) == 0:
        continue
    try:
        m = Prophet(weekly_seasonality=True, daily_seasonality=True,
                    yearly_seasonality=False, seasonality_mode="multiplicative")
        m.fit(tr)
        fc = m.predict(te[["datetime"]].rename(columns={"datetime": "ds"}))
        preds_prophet.extend(np.clip(fc["yhat"].values, 0, None))
        y_true_p.extend(te[TARGET].values)
        idx_p.extend(te.index.tolist())
    except Exception as e:
        print(f"     (zona {z} omitida: {e})")
    if i % 10 == 0:
        print(f"     ...{i}/{len(zonas_muestra)} zonas")

# Comparación JUSTA en la misma muestra de filas
test_m = test.loc[idx_p]
res_muestra = {
    "Baseline (muestra)": metricas(test_m[TARGET], test_m["lag_168h"]),
    "LightGBM (muestra)": metricas(test_m[TARGET], np.clip(lgbm.predict(
        test_m[FEATURES].assign(zona=test_m["zona"].astype("category"))), 0, None)),
    "Prophet (muestra)": metricas(y_true_p, preds_prophet),
}

# ----------------------------- Resultados -----------------------------
print("\n" + "=" * 60)
print("TABLA A — todas las zonas del test (nov-dic)")
print("=" * 60)
tabla_a = pd.DataFrame(resultados).T.round(3)
print(tabla_a.to_string())

print("\n" + "=" * 60)
print(f"TABLA B — muestra de {len(set(test_m['zona']))} zonas (comparación justa con Prophet)")
print("=" * 60)
tabla_b = pd.DataFrame(res_muestra).T.round(3)
print(tabla_b.to_string())

# Guardar para la memoria
out = pd.concat([tabla_a, tabla_b])
out.to_csv(RESULTS_DIR / "resultados_comparativa.csv")
print("\n→ Guardado: resultados_comparativa.csv")

# Veredicto rápido
mejora = (1 - tabla_a.loc["LightGBM", "WAPE_%"] / tabla_a.loc["Baseline", "WAPE_%"]) * 100
print(f"\nLightGBM mejora el WAPE del baseline en {mejora:.1f}%.")
print("Falta el LSTM (script aparte) para cerrar la comparativa de la Fase 2.")
