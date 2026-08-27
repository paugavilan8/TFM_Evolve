"""
Fase 2 (cierre) — Entrena el modelo de producción y lo GUARDA en disco
TFM Pau Gavilán

Hasta ahora los scripts de la fase 2 entrenaban, imprimían métricas y descartaban el
modelo. Aquí se entrena LightGBM con los hiperparámetros de producción y se serializa,
de modo que el modelo queda como artefacto reutilizable y citable en la memoria.

Se guarda en el formato NATIVO de LightGBM (.txt) y no con pickle. El motivo es la
portabilidad: un pickle depende de la versión exacta de Python y de scikit-learn con
que se creó, mientras que el fichero nativo lo lee cualquier versión de LightGBM, y
también sus enlaces para R o C++. Es texto plano, además, así que puede inspeccionarse.

Entrada:  data/gold/demanda_features_2023.parquet
Salida:   models/lgbm_demanda_nyc.txt    (el modelo)
          models/lgbm_demanda_nyc.json   (metadatos: variables, métricas, versiones)

    python pipeline/fase2_entrenar_final.py
"""

import json
import platform
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "gold" / "demanda_features_2023.parquet"
MODELS = ROOT / "models"
TARGET = "demanda"
FEATURES = [
    "hora", "hora_sin", "hora_cos", "dia_semana", "es_finde", "mes", "dia_mes",
    "es_festivo", "zona", "lag_1h", "lag_24h", "lag_168h", "roll_24h", "roll_168h",
]
PARAMS = dict(objective="poisson", n_estimators=500, learning_rate=0.05,
              num_leaves=63, min_child_samples=50, subsample=0.8,
              colsample_bytree=0.8, random_state=42, n_jobs=-1)


def metricas(y, yhat):
    y = np.asarray(y, dtype=float)
    yhat = np.asarray(yhat, dtype=float)
    return {
        "MAE": float(np.mean(np.abs(y - yhat))),
        "RMSE": float(np.sqrt(np.mean((y - yhat) ** 2))),
        "WAPE_%": float(np.sum(np.abs(y - yhat)) / np.sum(y) * 100),
    }


def main():
    import lightgbm as lgb
    from lightgbm import LGBMRegressor

    print("1) Cargando la tabla de variables...")
    df = pd.read_parquet(IN_PATH).dropna(subset=FEATURES)
    train = df[df["set"] == "train"]
    test = df[df["set"] == "test"]
    print("   train: %s filas | test: %s filas" % (f"{len(train):,}", f"{len(test):,}"))

    # Las categorías se fijan sobre TODAS las zonas del conjunto, no sobre las del
    # lote de entrenamiento, para que el mapeo guardado sea el mismo en inferencia.
    categorias = sorted(df["zona"].unique().tolist())

    print("2) Entrenando LightGBM (hiperparámetros de producción)...")
    X = train[FEATURES].copy()
    X["zona"] = pd.Categorical(X["zona"], categories=categorias)
    modelo = LGBMRegressor(**PARAMS, verbose=-1)
    modelo.fit(X, train[TARGET], categorical_feature=["zona"])

    print("3) Evaluando sobre el conjunto de prueba (nov-dic)...")
    Xt = test[FEATURES].copy()
    Xt["zona"] = pd.Categorical(Xt["zona"], categories=categorias)
    pred = np.clip(modelo.predict(Xt), 0, None)
    m_modelo = metricas(test[TARGET], pred)
    m_base = metricas(test[TARGET], test["lag_168h"])
    for nombre, m in [("Baseline", m_base), ("LightGBM", m_modelo)]:
        print("   %-9s MAE %6.3f | RMSE %7.3f | WAPE %5.1f %%"
              % (nombre, m["MAE"], m["RMSE"], m["WAPE_%"]))

    print("4) Guardando el modelo...")
    MODELS.mkdir(exist_ok=True)
    ruta_modelo = MODELS / "lgbm_demanda_nyc.txt"
    modelo.booster_.save_model(str(ruta_modelo))

    meta = {
        "nombre": "Modelo de demanda de taxi (NYC TLC 2023)",
        "entrenado": date.today().isoformat(),
        "datos": "data/gold/demanda_features_2023.parquet",
        "particion": {"train": "2023-01-01 a 2023-10-31", "test": "2023-11-01 a 2023-12-31",
                      "filas_train": int(len(train)), "filas_test": int(len(test))},
        "horizonte": "1 hora (predicción a un paso; usa lag_1h observado)",
        "features": FEATURES,
        "categorias_zona": [int(z) for z in categorias],
        "hiperparametros": {k: v for k, v in PARAMS.items()},
        "metricas_test": {"LightGBM": m_modelo, "Baseline": m_base},
        "entorno": {
            "python": platform.python_version(),
            "lightgbm": lgb.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    ruta_meta = MODELS / "lgbm_demanda_nyc.json"
    ruta_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    tam = ruta_modelo.stat().st_size / 1024**2
    print("   %s  (%.1f MB)" % (ruta_modelo.relative_to(ROOT), tam))
    print("   %s" % ruta_meta.relative_to(ROOT))

    # 5) Comprobación de ida y vuelta: el modelo recargado debe predecir lo mismo.
    print("5) Verificando el modelo guardado...")
    import sys
    sys.path.insert(0, str(ROOT))
    from pipeline.modelo import cargar, predecir

    booster, meta_leida = cargar()
    pred2 = predecir(booster, meta_leida, test.head(20000))
    dif = float(np.max(np.abs(pred2 - pred[:20000])))
    print("   diferencia máxima entre el modelo en memoria y el recargado: %.3e" % dif)
    if dif > 1e-9:
        raise SystemExit("El modelo recargado NO reproduce las predicciones.")
    print("   correcto: la serialización es fiel.")


if __name__ == "__main__":
    main()
