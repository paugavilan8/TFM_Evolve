"""
Análisis de errores por segmento y contraste de la hipótesis de transferencia.
TFM Pau Gavilán

Cubre dos puntos que la entrega 4 declara pendientes:

  1. El WAPE global oculta dónde falla el modelo. Se desagrega por franja horaria,
     por tipo de día y por nivel de demanda de la zona.
  2. La correlación de 0,88 entre las formas horarias de Nueva York y Terrassa no
     estaba contrastada contra ningún modelo nulo. Como cualquier par de perfiles
     de movilidad urbana comparte valle nocturno y meseta diurna, una correlación
     alta puede ser en parte automática. Se establece el suelo con un test de
     permutación y con las correlaciones internas entre distritos de Terrassa.

    python pipeline/fase3_analisis_errores.py

Salida: results/errores_por_segmento.csv
        results/contraste_transferencia.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GOLD = ROOT / "data" / "gold" / "demanda_features_2023.parquet"
NYC = ROOT / "data" / "processed" / "demanda_nyc_2023.parquet"
TERRASSA = ROOT / "data" / "external" / "perfil_movilidad_terrassa.csv"
RESULTS = ROOT / "results"
FEATURES = [
    "hora", "hora_sin", "hora_cos", "dia_semana", "es_finde", "mes", "dia_mes",
    "es_festivo", "zona", "lag_1h", "lag_24h", "lag_168h", "roll_24h", "roll_168h",
]


def wape(y, yhat):
    y = np.asarray(y, float)
    yhat = np.asarray(yhat, float)
    total = np.sum(y)
    return float(np.sum(np.abs(y - yhat)) / total * 100) if total else np.nan


# ============================ 1. Errores por segmento ============================
def analisis_errores():
    from pipeline.modelo import cargar, predecir

    print("1) Análisis de errores por segmento")
    booster, meta = cargar()
    df = pd.read_parquet(GOLD).dropna(subset=FEATURES)
    test = df[df["set"] == "test"].copy()
    test["pred"] = predecir(booster, meta, test)
    test["base"] = test["lag_168h"]

    # Franja horaria: los nombres siguen el uso del taxi, no un corte arbitrario.
    franjas = pd.cut(test["hora"], [-1, 5, 11, 16, 20, 23],
                     labels=["Madrugada (0-5)", "Mañana (6-11)", "Tarde (12-16)",
                             "Punta (17-20)", "Noche (21-23)"])
    # Nivel de demanda de la zona: terciles de su demanda media anual.
    media_zona = df.groupby("zona")["demanda"].mean()
    nivel = pd.qcut(media_zona, 3, labels=["Zona baja", "Zona media", "Zona alta"])
    test["nivel_zona"] = test["zona"].map(nivel)
    tipo_dia = np.where(test["es_festivo"] == 1, "Festivo",
                        np.where(test["es_finde"] == 1, "Fin de semana", "Laborable"))

    filas = []
    for corte, serie in [("Franja horaria", franjas), ("Tipo de día", pd.Series(tipo_dia, index=test.index)),
                         ("Nivel de la zona", test["nivel_zona"])]:
        for valor, g in test.groupby(serie, observed=True):
            w_mod, w_base = wape(g["demanda"], g["pred"]), wape(g["demanda"], g["base"])
            filas.append({
                "Corte": corte, "Segmento": str(valor), "Filas": len(g),
                "Demanda media": round(float(g["demanda"].mean()), 2),
                "WAPE baseline %": round(w_base, 1), "WAPE LightGBM %": round(w_mod, 1),
                "Mejora relativa %": round((w_base - w_mod) / w_base * 100, 1),
            })

    tabla = pd.DataFrame(filas)
    RESULTS.mkdir(exist_ok=True)
    tabla.to_csv(RESULTS / "errores_por_segmento.csv", index=False)
    print(tabla.to_string(index=False))
    print("\n   -> results/errores_por_segmento.csv\n")
    return tabla


# ====================== 2. Contraste de la transferencia ======================
def contraste_transferencia(n_perm=20000, semilla=42):
    print("2) Contraste de la hipótesis de transferencia")
    nyc = pd.read_parquet(NYC)
    ter = pd.read_csv(TERRASSA)
    ter["id_str"] = ter["id_origin"].astype(str).str.zfill(7)

    def norm(s):
        return np.asarray(s / s.sum(), float)

    nyc_h = norm(nyc.groupby("hora")["demanda"].mean())
    ter_h = norm(ter.groupby("hour")["viajes"].mean())
    r_obs = float(np.corrcoef(nyc_h, ter_h)[0, 1])

    # (a) Test de permutación: reordenar al azar las 24 horas de Terrassa destruye
    #     la alineación horaria pero conserva la distribución de valores.
    rng = np.random.default_rng(semilla)
    nulos = np.array([np.corrcoef(nyc_h, rng.permutation(ter_h))[0, 1]
                      for _ in range(n_perm)])
    p_valor = float((np.sum(nulos >= r_obs) + 1) / (n_perm + 1))

    # (b) Suelo "urbano genérico": correlación entre pares de distritos de la propia
    #     Terrassa. Marca cuánto de la similitud es simplemente el ritmo de una ciudad.
    perfiles = {d: norm(g.groupby("hour")["viajes"].mean())
                for d, g in ter.groupby("id_str")}
    ids = sorted(perfiles)
    internas = [float(np.corrcoef(perfiles[a], perfiles[b])[0, 1])
                for i, a in enumerate(ids) for b in ids[i + 1:]]

    # (c) Cada distrito de Terrassa frente a Nueva York.
    contra_nyc = {d: float(np.corrcoef(nyc_h, p)[0, 1]) for d, p in perfiles.items()}

    filas = [
        {"Medida": "r observado (NYC vs Terrassa)", "Valor": round(r_obs, 3),
         "Lectura": "Correlación de las formas horarias normalizadas"},
        {"Medida": "Media del nulo por permutación", "Valor": round(float(nulos.mean()), 3),
         "Lectura": "Correlación esperada si la alineación horaria fuese casual"},
        {"Medida": "Percentil 95 del nulo", "Valor": round(float(np.percentile(nulos, 95)), 3),
         "Lectura": "Umbral que hay que superar para no ser azar"},
        {"Medida": "p-valor del test de permutación", "Valor": round(p_valor, 5),
         "Lectura": "Proporción de permutaciones que igualan o superan el r observado"},
        {"Medida": "r medio entre distritos de Terrassa", "Valor": round(float(np.mean(internas)), 3),
         "Lectura": "Suelo urbano genérico: dos perfiles de la MISMA ciudad"},
        {"Medida": "r mínimo entre distritos de Terrassa", "Valor": round(float(np.min(internas)), 3),
         "Lectura": "El par de distritos menos parecido entre sí"},
        {"Medida": "r NYC vs distrito más parecido", "Valor": round(max(contra_nyc.values()), 3),
         "Lectura": "Mejor distrito: " + max(contra_nyc, key=contra_nyc.get)},
        {"Medida": "r NYC vs distrito menos parecido", "Valor": round(min(contra_nyc.values()), 3),
         "Lectura": "Peor distrito: " + min(contra_nyc, key=contra_nyc.get)},
    ]
    tabla = pd.DataFrame(filas)
    RESULTS.mkdir(exist_ok=True)
    tabla.to_csv(RESULTS / "contraste_transferencia.csv", index=False)
    print(tabla.to_string(index=False))
    print("\n   -> results/contraste_transferencia.csv")

    print("\n   Lectura:")
    print("   El r observado de %.3f frente a una media nula de %.3f y un p-valor de %.5f"
          % (r_obs, nulos.mean(), p_valor))
    print("   descarta que la coincidencia sea casual. Pero el suelo urbano genérico es")
    print("   %.3f: dos distritos de la propia Terrassa se parecen MÁS entre sí que" % np.mean(internas))
    print("   Terrassa y Nueva York, de modo que 0,88 confirma un ritmo urbano común")
    print("   y no una afinidad particular entre ambas ciudades.")
    return tabla


if __name__ == "__main__":
    analisis_errores()
    contraste_transferencia()
