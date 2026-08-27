"""
Genera todas las figuras de la memoria del TFM -> docs/figuras/*.png
TFM Pau Gavilán

Reproduce, a resolución de impresión y con una paleta única, los gráficos de los
notebooks fase1b_eda.ipynb y fase3_comparacion.ipynb, más la importancia de variables
de LightGBM (que hasta ahora sólo se imprimía por consola).

    python pipeline/figuras_memoria.py            # todas menos la de LightGBM
    python pipeline/figuras_memoria.py --lgbm     # incluye LightGBM (tarda unos minutos)
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figuras"
OUT.mkdir(parents=True, exist_ok=True)

NYC = ROOT / "data" / "processed" / "demanda_nyc_2023.parquet"
GOLD = ROOT / "data" / "gold" / "demanda_features_2023.parquet"
TERRASSA = ROOT / "data" / "external" / "perfil_movilidad_terrassa.csv"

# Paleta de marca del producto, para que memoria y app se lean como un mismo proyecto.
ROJO, AMBAR, GRIS = "#C0392B", "#E0902E", "#7A828C"
MAPA_CALOR = "rocket_r"
DPI = 200

sns.set_theme(style="whitegrid", font_scale=0.95)
plt.rcParams.update({
    "figure.dpi": DPI, "savefig.dpi": DPI, "savefig.bbox": "tight",
    "axes.titleweight": "bold", "axes.titlesize": 12, "axes.edgecolor": "#CCCCCC",
    "grid.color": "#E8E8E8", "axes.labelcolor": "#333333", "text.color": "#222222",
    "xtick.color": "#555555", "ytick.color": "#555555",
})


def guardar(nombre):
    ruta = OUT / (nombre + ".png")
    plt.savefig(ruta)
    plt.close()
    print("  " + str(ruta.relative_to(ROOT)))


def norm(s):
    return s / s.sum()


print("Cargando datos de NYC...")
df = pd.read_parquet(NYC)
df["fecha"] = pd.to_datetime(df["fecha"])
dias = {0: "Dom", 1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb"}
orden = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
df["dia_nombre"] = pd.Categorical(df["dia_semana"].map(dias), categories=orden, ordered=True)

print("Figuras del análisis exploratorio (NYC)...")

# 1 — curva horaria
por_hora = df.groupby("hora")["demanda"].mean()
plt.figure(figsize=(7.5, 3.6))
plt.plot(por_hora.index, por_hora.values, marker="o", color=ROJO, lw=2.2, ms=5)
plt.title("Demanda media por hora del día")
plt.xlabel("Hora")
plt.ylabel("Recogidas medias por zona-hora")
plt.xticks(range(0, 24, 2))
guardar("fig01_demanda_por_hora")

# 2 — por día de la semana
por_dia = df.groupby("dia_nombre", observed=False)["demanda"].mean()
plt.figure(figsize=(7.5, 3.4))
plt.bar(por_dia.index.astype(str), por_dia.values, color=ROJO, width=0.65)
plt.title("Demanda media por día de la semana")
plt.ylabel("Recogidas medias por zona-hora")
guardar("fig02_demanda_por_dia")

# 3 — mapa de calor hora x día
piv = df.pivot_table(index="hora", columns="dia_nombre", values="demanda",
                     aggfunc="mean", observed=False)
plt.figure(figsize=(6.2, 7))
sns.heatmap(piv, cmap=MAPA_CALOR, cbar_kws={"label": "Recogidas medias"})
plt.title("Demanda media: hora × día de la semana")
plt.xlabel("")
plt.ylabel("Hora")
guardar("fig03_heatmap_hora_dia")

# 4 — top 15 zonas
top = df.groupby("nombre_zona")["demanda"].sum().sort_values(ascending=False).head(15)
plt.figure(figsize=(7.5, 4.6))
plt.barh(top.sort_values().index, top.sort_values().values / 1e6, color=ROJO)
plt.title("Quince zonas con más demanda (NYC, 2023)")
plt.xlabel("Recogidas totales (millones)")
guardar("fig04_top_zonas")

# 5 — mapa de calor zona x hora
sub = df[df["nombre_zona"].isin(top.index)]
pz = sub.pivot_table(index="nombre_zona", columns="hora", values="demanda",
                     aggfunc="mean").reindex(top.index)
plt.figure(figsize=(8.5, 5))
sns.heatmap(pz, cmap=MAPA_CALOR, cbar_kws={"label": "Recogidas medias"})
plt.title("Demanda media: zona (top 15) × hora")
plt.xlabel("Hora")
plt.ylabel("")
guardar("fig05_heatmap_zona_hora")

# 6 — laborable vs fin de semana
comp = df.groupby(["es_finde", "hora"])["demanda"].mean().unstack(0)
comp.columns = ["Laborable", "Fin de semana"]
plt.figure(figsize=(7.5, 3.6))
plt.plot(comp.index, comp["Laborable"], marker="o", color=ROJO, lw=2.2, ms=4.5,
         label="Laborable")
plt.plot(comp.index, comp["Fin de semana"], marker="s", color=GRIS, lw=2.2, ms=4.5,
         label="Fin de semana")
plt.title("Curva horaria: laborable frente a fin de semana")
plt.xlabel("Hora")
plt.ylabel("Recogidas medias por zona-hora")
plt.xticks(range(0, 24, 2))
plt.legend(frameon=False)
guardar("fig06_laborable_vs_finde")

# 7 — distribución (dispersión / ceros)
plt.figure(figsize=(7.5, 3.6))
plt.hist(df["demanda"].clip(upper=df["demanda"].quantile(0.99)), bins=60, color=ROJO)
pct0 = (df["demanda"] == 0).mean() * 100
plt.title("Distribución de la demanda por zona-hora "
          "(%.1f %% de celdas a cero)" % pct0)
plt.xlabel("Recogidas en la hora")
plt.ylabel("Frecuencia")
guardar("fig07_distribucion_demanda")

# 8 — serie anual
diaria = df.groupby("fecha")["demanda"].sum()
plt.figure(figsize=(8.5, 3.4))
plt.plot(diaria.index, diaria.values / 1000, color=ROJO, lw=1.1)
plt.title("Demanda diaria total — NYC 2023")
plt.ylabel("Recogidas (miles)")
plt.xlabel("")
guardar("fig08_serie_anual")

print("Figuras de la transferencia (NYC vs Terrassa)...")
ter = pd.read_csv(TERRASSA)
ter["id_str"] = ter["id_origin"].astype(str).str.zfill(7)
etiq = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

# 9 — Terrassa distrito x hora
pt = ter.pivot_table(index="id_str", columns="hour", values="viajes", aggfunc="mean")
plt.figure(figsize=(8.5, 2.9))
sns.heatmap(pt, cmap=MAPA_CALOR, cbar_kws={"label": "Viajes medios"})
plt.title("Terrassa — movilidad media por distrito × hora")
plt.xlabel("Hora")
plt.ylabel("Distrito")
guardar("fig09_terrassa_distrito_hora")

# 10 — Terrassa por hora y por día
th = ter.groupby("hour")["viajes"].mean()
tw = ter.groupby("dow")["viajes"].mean()
tw.index = etiq
fig, ax = plt.subplots(1, 2, figsize=(9, 3.3))
ax[0].plot(th.index, th.values, marker="o", color=ROJO, lw=2.2, ms=4.5)
ax[0].set_title("Terrassa — por hora")
ax[0].set_xlabel("Hora")
ax[0].set_xticks(range(0, 24, 4))
ax[1].bar(tw.index, tw.values, color=ROJO, width=0.65)
ax[1].set_title("Terrassa — por día de la semana")
plt.tight_layout()
guardar("fig10_terrassa_hora_dia")

# 11 — la figura clave: formas horarias normalizadas
nh = df.groupby("hora")["demanda"].mean()
r_hora = np.corrcoef(norm(nh).values, norm(th).values)[0, 1]
plt.figure(figsize=(8, 4))
plt.plot(range(24), norm(nh).values, marker="o", color=GRIS, lw=2.4, ms=5,
         label="NYC (taxi)")
plt.plot(range(24), norm(th).values, marker="s", color=ROJO, lw=2.4, ms=5,
         label="Terrassa (movilidad)")
plt.title("Forma horaria normalizada: NYC frente a Terrassa  (r = %.3f)" % r_hora)
plt.xlabel("Hora")
plt.ylabel("Proporción de la actividad diaria")
plt.xticks(range(0, 24, 2))
plt.legend(frameon=False)
guardar("fig11_forma_horaria_nyc_terrassa")

# 12 — formas semanales
orden_nyc = [1, 2, 3, 4, 5, 6, 0]
nw = df.groupby("dia_semana")["demanda"].mean().reindex(orden_nyc)
nw.index = etiq
r_dia = np.corrcoef(norm(nw).values, norm(tw).values)[0, 1]
x = np.arange(7)
w = 0.38
plt.figure(figsize=(8, 3.6))
plt.bar(x - w / 2, norm(nw).values, w, color=GRIS, label="NYC (taxi)")
plt.bar(x + w / 2, norm(tw).values, w, color=ROJO, label="Terrassa (movilidad)")
plt.xticks(x, etiq)
plt.title("Forma semanal normalizada: NYC frente a Terrassa  (r = %.3f)" % r_dia)
plt.ylabel("Proporción de la actividad semanal")
plt.legend(frameon=False)
guardar("fig12_forma_semanal_nyc_terrassa")

print("\nCorrelaciones: horaria r = %.3f | semanal r = %.3f" % (r_hora, r_dia))

# 13 — importancia de variables de LightGBM (opcional: tarda)
if "--lgbm" in sys.argv:
    print("\nEntrenando LightGBM para la importancia de variables...")
    from lightgbm import LGBMRegressor
    FEATURES = ["hora", "hora_sin", "hora_cos", "dia_semana", "es_finde", "mes", "dia_mes",
                "es_festivo", "zona", "lag_1h", "lag_24h", "lag_168h", "roll_24h", "roll_168h"]
    g = pd.read_parquet(GOLD).dropna(subset=FEATURES)
    tr = g[g["set"] == "train"]
    X = tr[FEATURES].copy()
    X["zona"] = X["zona"].astype("category")
    m = LGBMRegressor(objective="poisson", n_estimators=500, learning_rate=0.05,
                      num_leaves=63, min_child_samples=50, subsample=0.8,
                      colsample_bytree=0.8, random_state=42, n_jobs=-1, verbose=-1)
    m.fit(X, tr["demanda"], categorical_feature=["zona"])
    imp = pd.Series(m.feature_importances_, index=FEATURES).sort_values()
    plt.figure(figsize=(7.5, 4.4))
    colores = [ROJO if v >= imp.quantile(0.7) else AMBAR if v >= imp.quantile(0.35) else GRIS
               for v in imp.values]
    plt.barh(imp.index, imp.values, color=colores)
    plt.title("Importancia de variables — LightGBM")
    plt.xlabel("Número de divisiones en que interviene la variable")
    guardar("fig13_importancia_variables")
    (ROOT / "results").mkdir(exist_ok=True)
    imp.sort_values(ascending=False).to_csv(ROOT / "results" / "importancia_variables.csv",
                                            header=["importancia"])
    print("\n  Top 6:")
    for k, v in imp.sort_values(ascending=False).head(6).items():
        print("    %-12s %s" % (k, v))

print("\nListo.")
