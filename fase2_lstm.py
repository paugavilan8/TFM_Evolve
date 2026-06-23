"""
Fase 2 (cierre) — LSTM, para completar la comparativa de modelos
TFM Pau Gavilán — Predicción de demanda para taxistas autónomos

Compara, sobre LAS MISMAS filas de test, tres modelos:
    Baseline ('misma hora, semana anterior')  ·  LightGBM  ·  LSTM

El LSTM aprende de SECUENCIAS: para predecir la demanda de la próxima hora en una
zona, mira las últimas WINDOW horas de esa zona. Por coste de cómputo se entrena
sobre una MUESTRA de zonas (las de más demanda), igual que hicimos con Prophet, y
LightGBM se reentrena sobre esas mismas zonas para que la comparación sea justa.

Entrada:  data/processed/demanda_features_2023.parquet
Salida:   resultados_lstm.csv

Ejecuta en TU máquina, con el venv activado:
    python -m pip install tensorflow lightgbm pandas pyarrow numpy
    python fase2_lstm.py

⚠️ Es el script más pesado. Si te quedas sin memoria, baja SAMPLE_ZONES o WINDOW.
"""

import os
import numpy as np
import pandas as pd

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

IN_PATH = "data/processed/demanda_features_2023.parquet"
TARGET = "demanda"
WINDOW = 168          # nº de horas de historia que mira el LSTM (168 = 1 semana; capta el lag semanal)
SAMPLE_ZONES = 20     # zonas de más demanda para entrenar (sube/baja según tu RAM)
SEQ_FEATS = ["demanda_log", "hora_sin", "hora_cos", "es_finde"]   # variables por paso temporal
LGBM_FEATS = [
    "hora", "hora_sin", "hora_cos", "dia_semana", "es_finde", "mes", "dia_mes",
    "es_festivo", "zona", "lag_1h", "lag_24h", "lag_168h", "roll_24h", "roll_168h",
]


def metricas(y, yhat):
    y = np.asarray(y, float); yhat = np.asarray(yhat, float)
    mae = np.mean(np.abs(y - yhat))
    rmse = np.sqrt(np.mean((y - yhat) ** 2))
    wape = np.sum(np.abs(y - yhat)) / np.sum(y) if np.sum(y) > 0 else np.nan
    return {"MAE": mae, "RMSE": rmse, "WAPE_%": wape * 100}


# ----------------------------- Cargar -----------------------------
print("1) Cargando datos...")
df = pd.read_parquet(IN_PATH)
df["demanda_log"] = np.log1p(df[TARGET])

zonas_top = df.groupby("zona")[TARGET].sum().sort_values(ascending=False).index.tolist()
zonas = zonas_top[:SAMPLE_ZONES]
sub = df[df["zona"].isin(zonas)].sort_values(["zona", "datetime"]).reset_index(drop=True)

# ----------------------- Construir secuencias -----------------------
print(f"2) Construyendo secuencias (WINDOW={WINDOW}h, {SAMPLE_ZONES} zonas)...")
Xtr, ytr, Xte, yte_true, base_te = [], [], [], [], []
for z in zonas:
    s = sub[sub["zona"] == z]
    feat = s[SEQ_FEATS].values.astype("float32")          # (T, F)
    y_log = s["demanda_log"].values.astype("float32")
    y_cnt = s[TARGET].values.astype("float32")            # conteos reales (para métricas)
    lag168 = s["lag_168h"].values.astype("float32")       # baseline en las mismas filas
    is_test = (s["set"] == "test").values

    # ventanas deslizantes: ventana k = feat[k:k+WINDOW] -> predice y en k+WINDOW
    win = np.lib.stride_tricks.sliding_window_view(feat, WINDOW, axis=0)  # (n, F, WINDOW)
    win = win.transpose(0, 2, 1)[:-1]                                      # (n, WINDOW, F)
    tgt_log = y_log[WINDOW:]
    tgt_cnt = y_cnt[WINDOW:]
    tgt_base = lag168[WINDOW:]
    tgt_mask = is_test[WINDOW:]

    Xtr.append(win[~tgt_mask]);  ytr.append(tgt_log[~tgt_mask])
    Xte.append(win[tgt_mask]);   yte_true.append(tgt_cnt[tgt_mask]); base_te.append(tgt_base[tgt_mask])

Xtr = np.concatenate(Xtr); ytr = np.concatenate(ytr)
Xte = np.concatenate(Xte); yte_true = np.concatenate(yte_true); base_te = np.concatenate(base_te)
print(f"   train: {Xtr.shape} | test: {Xte.shape}")

# ----------------------------- LSTM -----------------------------
print("3) Entrenando el LSTM (la parte lenta)...")
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Input
from tensorflow.keras.callbacks import EarlyStopping

tf.random.set_seed(42)
model = Sequential([
    Input((WINDOW, len(SEQ_FEATS))),
    LSTM(64),
    Dense(32, activation="relu"),
    Dense(1),
])
model.compile(optimizer="adam", loss="mse")
model.fit(Xtr, ytr, validation_split=0.1, epochs=15, batch_size=256, verbose=2,
          callbacks=[EarlyStopping(patience=3, restore_best_weights=True)])

pred_lstm = np.clip(np.expm1(model.predict(Xte, verbose=0).ravel()), 0, None)   # vuelve a conteos

# ----------------------- LightGBM en las mismas zonas -----------------------
print("4) Reentrenando LightGBM en las mismas zonas (comparación justa)...")
from lightgbm import LGBMRegressor

tr = sub[(sub["set"] == "train")].dropna(subset=LGBM_FEATS)
te = sub[(sub["set"] == "test")].dropna(subset=LGBM_FEATS)
Xa, Xb = tr[LGBM_FEATS].copy(), te[LGBM_FEATS].copy()
Xa["zona"] = Xa["zona"].astype("category"); Xb["zona"] = Xb["zona"].astype("category")
lgbm = LGBMRegressor(objective="poisson", n_estimators=500, learning_rate=0.05,
                     num_leaves=63, min_child_samples=50, subsample=0.8,
                     colsample_bytree=0.8, random_state=42, n_jobs=-1)
lgbm.fit(Xa, tr[TARGET], categorical_feature=["zona"])
pred_lgbm = np.clip(lgbm.predict(Xb), 0, None)

# ----------------------------- Resultados -----------------------------
res = {
    "Baseline": metricas(yte_true, base_te),
    "LightGBM": metricas(te[TARGET], pred_lgbm),
    "LSTM": metricas(yte_true, pred_lstm),
}
tabla = pd.DataFrame(res).T.round(3)
print("\n" + "=" * 56)
print(f"COMPARATIVA — muestra de {SAMPLE_ZONES} zonas (test nov-dic)")
print("=" * 56)
print(tabla.to_string())
tabla.to_csv("resultados_lstm.csv")
print("\n→ Guardado: resultados_lstm.csv")

mejor = tabla["WAPE_%"].idxmin()
print(f"\nMejor WAPE: {mejor} ({tabla.loc[mejor, 'WAPE_%']:.1f}%).")
print("Recuerda: aunque el LSTM no gane, documentar la comparativa completa da rigor a la memoria.")
