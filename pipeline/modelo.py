"""
Carga del modelo de demanda entrenado y predicción.
TFM Pau Gavilán

Separa la inferencia del entrenamiento: cualquier proceso puede cargar el modelo
guardado y predecir sin volver a entrenar ni depender del script que lo generó.

    from pipeline.modelo import cargar, predecir
    booster, meta = cargar()
    y = predecir(booster, meta, df)
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODELO = ROOT / "models" / "lgbm_demanda_nyc.txt"
META = ROOT / "models" / "lgbm_demanda_nyc.json"


def cargar(ruta_modelo=MODELO, ruta_meta=META):
    """Devuelve (booster, metadatos). Lanza FileNotFoundError si falta el modelo."""
    import lightgbm as lgb

    if not ruta_modelo.exists():
        raise FileNotFoundError(
            "No encuentro el modelo en %s. Entrénalo con:\n"
            "    python pipeline/fase2_entrenar_final.py" % ruta_modelo)
    booster = lgb.Booster(model_file=str(ruta_modelo))
    meta = json.loads(ruta_meta.read_text(encoding="utf-8"))
    return booster, meta


def predecir(booster, meta, df):
    """Predice demanda para un DataFrame con las variables del modelo.

    Reconstruye explícitamente las categorías de 'zona' a partir de los metadatos:
    si se dejara que pandas las dedujera del propio lote, un subconjunto de zonas
    produciría códigos distintos a los del entrenamiento y predicciones erróneas.
    """
    X = df[meta["features"]].copy()
    X["zona"] = pd.Categorical(X["zona"], categories=meta["categorias_zona"])
    if X["zona"].isna().any():
        desconocidas = sorted(set(df.loc[X["zona"].isna(), "zona"]))
        raise ValueError("Zonas no vistas en el entrenamiento: %s" % desconocidas[:10])
    # La demanda es un conteo: nunca negativa.
    return np.clip(booster.predict(X), 0, None)
