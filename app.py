"""
Asistente del Taxi de Terrassa — App profesional (Fase 4, rediseño)
TFM Pau Gavilán

Modo Conductor: recomienda la PARADA a la que ir + mapa, con demanda por niveles
                (alta / media / baja), pensada para un vistazo rápido.
Modo Análisis : patrones, transferencia NYC<->Terrassa, rentabilidad y origen de datos.

Coloca junto a este archivo:
  - perfil_movilidad_terrassa.csv             (OBLIGATORIO, Fase 3)
  - terrassa_distritos.geojson                (mapa; en WGS84)
  - paradas_terrassa.csv                      (genera con obtener_paradas.py o edita a mano)
  - Registro_carreras_TFM.xlsx                (rentabilidad; opcional)
  - data/processed/demanda_nyc_2023.parquet   (comparación; opcional)
  - .streamlit/config.toml                    (tema)

Ejecutar:
    python -m pip install streamlit folium streamlit-folium plotly branca openpyxl pandas
    python -m streamlit run app.py
"""

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Asistente del Taxi — Terrassa",
                   layout="wide", initial_sidebar_state="collapsed")

PERFIL_CSV = "perfil_movilidad_terrassa.csv"
GEOJSON = "terrassa_distritos.geojson"
PARADAS_CSV = "paradas_terrassa.csv"
REGISTRO_XLSX = "Registro_carreras_TFM.xlsx"
NYC_PARQUET = "data/processed/demanda_nyc_2023.parquet"
CENTRO = [41.5631, 2.0089]
DIAS = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes", 6: "Sábado", 7: "Domingo"}
COLOR = {"Alta": "#0E6E55", "Media": "#E6A700", "Baja": "#9AA5B1"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 1.5rem; max-width: 1100px;}
.brand {font-weight: 800; font-size: 1.5rem; letter-spacing: -.02em; margin-bottom: .2rem;}
.brand b {color: #0E6E55;}
.sub {color: #5e6b78; margin-bottom: 1rem;}
.hero {color: #fff; border-radius: 20px; padding: 26px 30px; margin: 6px 0 18px;}
.hero-label {opacity: .9; font-size: .8rem; text-transform: uppercase; letter-spacing: .1em;}
.hero-stand {font-size: 2.3rem; font-weight: 800; line-height: 1.1; margin: .15em 0;}
.hero-why {opacity: .92; margin-top: .5em; font-size: .98rem;}
.badge {display: inline-block; padding: 5px 14px; border-radius: 999px;
        font-weight: 600; font-size: .85rem; background: rgba(255,255,255,.22);}
</style>
"""
CSS_NIGHT = "<style>.stApp{background:#0e1117;} h1,h2,h3,h4,p,span,div,label{color:#e6edf3 !important;}" \
            ".sub{color:#9aa5b1 !important;}</style>"


# ----------------------------- Carga -----------------------------
@st.cache_data
def cargar_perfil():
    df = pd.read_csv(PERFIL_CSV)
    df["id_str"] = df["id_origin"].astype(str).str.zfill(7)
    return df


@st.cache_data
def cargar_geo():
    p = Path(GEOJSON)
    if not p.exists():
        return None, {}
    geo = json.loads(p.read_text(encoding="utf-8"))
    nombres = {}
    for f in geo["features"]:
        pr = f.get("properties", {})
        fid = str(pr.get("id", pr.get("ID", ""))).zfill(7)
        nombres[fid] = pr.get("name", pr.get("nombre", f"Distrito {fid}"))
    return geo, nombres


@st.cache_data
def cargar_paradas():
    p = Path(PARADAS_CSV)
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if not {"nombre", "lat", "lon"}.issubset(df.columns):
        return None
    df = df.dropna(subset=["lat", "lon"])
    return df if len(df) else None


@st.cache_data
def cargar_registro():
    p = Path(REGISTRO_XLSX)
    if not p.exists():
        return None
    try:
        df = pd.read_excel(p, sheet_name="Registro", skiprows=2)
    except Exception:
        return None
    df = df[df["Fecha"].notna()]
    if "Nº" in df.columns:
        df = df[df["Nº"].astype(str).str.upper() != "EJEMPLO"]
    df = df[pd.to_numeric(df["Importe (€)"], errors="coerce").notna()]
    if len(df):
        df["Importe (€)"] = pd.to_numeric(df["Importe (€)"], errors="coerce")
        df["Distancia (km)"] = pd.to_numeric(df.get("Distancia (km)"), errors="coerce")
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    return df


# ----------------------------- Geometría / demanda -----------------------------
def _en_anillo(x, y, anillo):
    dentro = False
    n = len(anillo)
    j = n - 1
    for i in range(n):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            dentro = not dentro
        j = i
    return dentro


def distrito_de(lon, lat, geo):
    for f in geo["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            if poly and _en_anillo(lon, lat, poly[0]):
                return str(f["properties"].get("id", "")).zfill(7)
    return None


def demanda_distritos(perfil, dia, hora):
    s = perfil[(perfil["dow"] == dia) & (perfil["hour"] == hora)]
    return s.groupby("id_str")["viajes"].mean()


def nivel(v, vmax):
    if vmax <= 0:
        return "Baja"
    if v >= 0.66 * vmax:
        return "Alta"
    if v >= 0.33 * vmax:
        return "Media"
    return "Baja"


# ----------------------------- Render -----------------------------
def dibujar_mapa_paradas(items, noche):
    try:
        import folium
        from streamlit_folium import st_folium
    except Exception:
        st.warning("Instala el mapa: python -m pip install folium streamlit-folium")
        return
    tiles = "cartodbdark_matter" if noche else "cartodbpositron"
    m = folium.Map(location=CENTRO, zoom_start=14, tiles=tiles)
    for i, it in enumerate(items):
        if pd.isna(it["lat"]) or pd.isna(it["lon"]):
            continue
        es_top = (i == 0)
        folium.CircleMarker(
            location=[it["lat"], it["lon"]],
            radius=12 if es_top else 7,
            color="#ffffff", weight=2 if es_top else 1,
            fill=True, fill_color=COLOR[it["nivel"]], fill_opacity=0.95,
            tooltip=f'{it["nombre"]} — demanda {it["nivel"].lower()}',
        ).add_to(m)
    st_folium(m, height=460, use_container_width=True)


def recomendar_por_distrito(perfil, dem, nombres, geo, noche):
    try:
        import folium
        import branca.colormap as cm
        from streamlit_folium import st_folium
    except Exception:
        return
    vmax = float(dem.max()) if len(dem) else 1.0
    escala = cm.linear.YlOrRd_09.scale(0, vmax)
    for f in geo["features"]:
        fid = str(f["properties"].get("id", "")).zfill(7)
        f["properties"]["zona"] = nombres.get(fid, fid)

    def estilo(feat):
        fid = str(feat["properties"].get("id", "")).zfill(7)
        return {"fillColor": escala(float(dem.get(fid, 0))), "color": "black",
                "weight": 1, "fillOpacity": 0.7}

    tiles = "cartodbdark_matter" if noche else "cartodbpositron"
    m = folium.Map(location=CENTRO, zoom_start=13, tiles=tiles)
    folium.GeoJson(geo, style_function=estilo,
                   tooltip=folium.GeoJsonTooltip(fields=["zona"], aliases=["Zona:"])).add_to(m)
    st_folium(m, height=440, use_container_width=True)


def modo_analisis(perfil, geo, nombres):
    try:
        import plotly.express as px
        tiene_px = True
    except Exception:
        tiene_px = False

    st.subheader("Patrón de demanda de Terrassa")
    piv = perfil.pivot_table(index="id_str", columns="hour", values="viajes", aggfunc="mean")
    piv.index = [nombres.get(i, i) for i in piv.index]
    if tiene_px:
        st.plotly_chart(px.imshow(piv, aspect="auto", color_continuous_scale="YlOrRd",
                                  labels={"x": "Hora", "y": "Zona", "color": "Demanda"}),
                        use_container_width=True)
    else:
        st.dataframe(piv)

    a, b = st.columns(2)
    a.markdown("**Demanda por hora**")
    a.line_chart(perfil.groupby("hour")["viajes"].mean())
    sem = perfil.groupby("dow")["viajes"].mean()
    sem.index = [DIAS[d] for d in sem.index]
    b.markdown("**Demanda por día**")
    b.bar_chart(sem)

    if Path(NYC_PARQUET).exists():
        st.divider()
        st.subheader("Transferencia: NYC vs Terrassa")
        nyc = pd.read_parquet(NYC_PARQUET)
        nh = nyc.groupby("hora")["demanda"].mean()
        th = perfil.groupby("hour")["viajes"].mean()
        comp = pd.DataFrame({"NYC (taxi)": nh / nh.sum(), "Terrassa": th / th.sum()})
        st.line_chart(comp)
        r = np.corrcoef(comp["NYC (taxi)"], comp["Terrassa"])[0, 1]
        st.metric("Correlación de la forma horaria", f"r = {r:.3f}")

    st.divider()
    st.subheader("Rentabilidad")
    reg = cargar_registro()
    if reg is None:
        st.warning(f"No encuentro '{REGISTRO_XLSX}'.")
    elif len(reg) == 0:
        st.info("Aún no hay carreras registradas. Aparecerán aquí en cuanto se apunten.")
    else:
        ingresos, km = reg["Importe (€)"].sum(), reg["Distancia (km)"].sum()
        m1, m2, m3 = st.columns(3)
        m1.metric("Carreras", len(reg))
        m2.metric("Ingresos", f"{ingresos:,.2f} €")
        m3.metric("€/km medio", f"{ingresos / km:.2f}" if km and not np.isnan(km) else "—")
        st.bar_chart(reg.groupby(reg["Fecha"].dt.date)["Importe (€)"].sum())

    st.divider()
    with st.expander("De dónde vienen los datos"):
        st.markdown(
            "- **Patrones de demanda:** NYC TLC Trip Record Data (taxi real).\n"
            "- **Escala local:** Estudio de movilidad con Big Data del MITMA (proxy por distrito).\n"
            "- **Paradas:** OpenStreetMap + conocimiento local.\n"
            "- **Validación:** registro real de carreras del taxista.")


# =============================== Página ===============================
def main():
    perfil = cargar_perfil()
    geo, nombres = cargar_geo()
    paradas = cargar_paradas()

    st.markdown(CSS, unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1])
    c1.markdown('<div class="brand">Taxi<b>Terrassa</b></div>'
                '<div class="sub">Tu asistente para saber dónde hay trabajo</div>',
                unsafe_allow_html=True)
    modo = c2.radio("Vista", ["Conductor", "Análisis"], horizontal=True, label_visibility="collapsed")
    noche = c2.toggle("Modo noche")
    if noche:
        st.markdown(CSS_NIGHT, unsafe_allow_html=True)

    if modo == "Conductor":
        ahora = dt.datetime.now()
        cc1, cc2 = st.columns([1, 2])
        if cc1.toggle("Ahora mismo", value=True):
            dia, hora = ahora.isoweekday(), ahora.hour
        else:
            dia = cc1.selectbox("Día", list(DIAS), format_func=lambda d: DIAS[d],
                                index=ahora.isoweekday() - 1)
            hora = cc2.slider("Hora", 0, 23, ahora.hour)

        dem = demanda_distritos(perfil, dia, hora)
        vmax = float(dem.max()) if len(dem) else 0.0

        items = []
        if paradas is not None and geo is not None:
            for _, p in paradas.iterrows():
                if pd.isna(p["lat"]) or pd.isna(p["lon"]):
                    continue
                did = distrito_de(p["lon"], p["lat"], geo)
                v = float(dem.get(did, 0)) if did else 0.0
                items.append({"nombre": p["nombre"], "lat": float(p["lat"]), "lon": float(p["lon"]),
                              "valor": v, "nivel": nivel(v, vmax)})
            items.sort(key=lambda d: d["valor"], reverse=True)

        if items:
            top = items[0]
            st.markdown(
                f'<div class="hero" style="background:{COLOR[top["nivel"]]}">'
                f'<div class="hero-label">Ahora ({DIAS[dia]}, {hora:02d}:00), ve a</div>'
                f'<div class="hero-stand">{top["nombre"]}</div>'
                f'<span class="badge">Demanda {top["nivel"].lower()}</span>'
                f'<div class="hero-why">Es la parada con más movimiento previsto a esta hora.</div>'
                f'</div>', unsafe_allow_html=True)
            dibujar_mapa_paradas(items, noche)
        elif geo is not None:
            st.info("Aún no tengo las paradas. Ejecuta `python obtener_paradas.py` para "
                    "descargarlas de OpenStreetMap (o crea `paradas_terrassa.csv` con tu madre).")
            recomendar_por_distrito(perfil, dem, nombres, geo, noche)
        else:
            st.warning("Falta `terrassa_distritos.geojson` para el mapa.")
    else:
        modo_analisis(perfil, geo, nombres)


if __name__ == "__main__":
    main()
