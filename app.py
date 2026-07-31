"""
TaxiTerrassa — App unificada (Fase 4)
TFM Pau Gavilán

Tres modos:
  Conductor  — recomienda la parada a la que ir (mapa, demanda por niveles).
  Registrar  — foto del ticket -> Gemini extrae -> guarda en Google Sheets (o Excel local).
  Análisis   — patrones, transferencia NYC<->Terrassa y rentabilidad REAL leída del registro.

Coloca junto a este archivo: perfil_movilidad_terrassa.csv, terrassa_distritos.geojson,
paradas_terrassa.csv, (opcional) data/processed/demanda_nyc_2023.parquet, .streamlit/config.toml
y, para el escáner/rentabilidad en la nube, los secretos (GEMINI_API_KEY, SHEET_ID, cuenta de servicio).

    python -m pip install streamlit folium streamlit-folium branca plotly pandas openpyxl \
                          google-generativeai gspread google-auth pillow
    python -m streamlit run app.py
"""

import datetime as dt
import io
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="TaxiTerrassa", page_icon="🚕",
                   layout="centered", initial_sidebar_state="collapsed")

PERFIL_CSV = "perfil_movilidad_terrassa.csv"
GEOJSON = "terrassa_distritos.geojson"
PARADAS_CSV = "paradas_terrassa.csv"
REGISTRO_XLSX = "Registro_carreras_TFM.xlsx"
NYC_PARQUET = "data/processed/demanda_nyc_2023.parquet"
CENTRO = [41.5631, 2.0089]
DIAS = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes", 6: "Sábado", 7: "Domingo"}
COLOR = {"Alta": "#0E6E55", "Media": "#E6A700", "Baja": "#9AA5B1"}

MODELO = "gemini-2.5-flash"
COLUMNAS = ["fecha", "hora_recogida", "hora_fin", "zona_recogida", "zona_destino",
            "distancia_km", "importe_eur", "origen_servicio", "tarifa"]
PROMPT = """Eres un asistente que lee tickets de taxi (pueden estar en catalán o español).
Extrae los datos y responde SOLO con un objeto JSON (sin texto alrededor), usando null
cuando un dato no aparezca. Claves:
{"fecha": "YYYY-MM-DD",
 "hora_recogida": "HH:MM",
 "hora_fin": "HH:MM",
 "zona_recogida": "calle o lugar de ORIGEN, sin la ciudad",
 "zona_destino": "calle o lugar del DESTINO, sin la ciudad",
 "distancia_km": number,
 "importe_eur": number,
 "tarifa": "valor de TAR. APLICAD / tarifa, si aparece",
 "origen_servicio": "Emisora si el ticket viene de central o despacho; si no, null"}
Pistas: fecha=DATA INICI, hora_recogida=HORA INICI, hora_fin=HORA FINAL,
distancia=RECORREGUT (km), importe=IMP. TOTAL (total cobrado).
Convierte las comas decimales a punto."""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif; }
.stApp { background: #F4F5F7; }
#MainMenu, footer, header, [data-testid="stToolbar"] { visibility: hidden; height: 0; }
.block-container { padding-top: 1rem; padding-bottom: 3rem; max-width: 760px; }

/* Cabecera de marca */
.brandbar { display: flex; align-items: center; gap: 12px; margin: 2px 0 16px; }
.brandbar .avatar { width: 42px; height: 42px; border-radius: 50%; background: #C0392B; color: #fff;
  display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 20px; flex: none; }
.brandbar .title { font-weight: 800; font-size: 1.25rem; color: #1A1A1A; line-height: 1.15; }
.brandbar .title b { color: #C0392B; }
.brandbar .sub { color: #7A828C; font-size: .85rem; }

/* Tarjeta de recomendación */
.hero { background: linear-gradient(135deg, #C0392B, #8E2018); color: #fff; border-radius: 20px;
  padding: 22px 24px; margin: 6px 0 16px; box-shadow: 0 12px 26px rgba(192,57,43,.28); }
.hero-label { opacity: .9; font-size: .74rem; text-transform: uppercase; letter-spacing: .09em; }
.hero-stand { font-size: 2rem; font-weight: 800; line-height: 1.1; margin: .15em 0; }
.hero-why { opacity: .92; margin-top: .5em; font-size: .95rem; }
.badge { display: inline-block; padding: 5px 13px; border-radius: 999px;
  font-weight: 600; font-size: .82rem; background: rgba(255,255,255,.22); }

/* Métricas y contenedores como tarjetas blancas */
[data-testid="stMetric"], [data-testid="stVerticalBlockBorderWrapper"] {
  background: #fff; border: 1px solid #EDEFF2; border-radius: 16px; padding: 14px 16px;
  box-shadow: 0 4px 16px rgba(20,32,43,.05); }
[data-testid="stMetricValue"] { color: #C0392B; font-weight: 800; }

/* Botones rojos redondeados */
.stButton > button, .stDownloadButton > button, [data-testid="stCameraInput"] button {
  background: #C0392B; color: #fff; border: none; border-radius: 12px; font-weight: 600; padding: .55rem 1rem; }
.stButton > button:hover { background: #A93226; color: #fff; }

@media (max-width: 640px) {
  .block-container { padding: .8rem .7rem 3rem !important; }
  .hero-stand { font-size: 1.7rem; }
}
</style>
"""
CSS_NIGHT = "<style>.stApp{background:#0e1117;} .brandbar .title,.brandbar .title b{color:#e6edf3;}" \
            "[data-testid='stMetric'],[data-testid='stVerticalBlockBorderWrapper']{background:#161b22;border-color:#2b333d;}" \
            "h1,h2,h3,h4,p,span,div,label{color:#e6edf3 !important;} .brandbar .sub{color:#9aa5b1 !important;}</style>"


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


# ----------------------------- Gemini / Sheets -----------------------------
def obtener_api_key():
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY")


def _preparar_imagen(uploaded):
    raw = uploaded.getvalue()
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img.thumbnail((1600, 1600))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return raw, uploaded.type or "image/jpeg"


def extraer(uploaded, api_key):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODELO)
    data, mime = _preparar_imagen(uploaded)
    resp = model.generate_content([PROMPT, {"mime_type": mime, "data": data}])
    txt = resp.text.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        txt = txt[4:] if txt.lower().startswith("json") else txt
    return json.loads(txt.strip())


def parse_fecha(s):
    if not s:
        return s
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(str(s), fmt).date()
        except ValueError:
            pass
    return s


def _service_account_info():
    try:
        if "gcp_service_account_json" in st.secrets:
            return json.loads(st.secrets["gcp_service_account_json"])
        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
    except Exception:
        pass
    return None


def _usar_sheets():
    try:
        return _service_account_info() is not None and bool(st.secrets.get("SHEET_ID"))
    except Exception:
        return False


def _hoja():
    import gspread
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_info(
        _service_account_info(), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(st.secrets["SHEET_ID"]).sheet1


def guardar(df):
    if _usar_sheets():
        ws = _hoja()
        for _, r in df.iterrows():
            fila = ["" if pd.isna(r.get(c)) else r.get(c) for c in COLUMNAS]
            fila[0] = str(parse_fecha(r.get("fecha")))
            ws.append_row(fila, value_input_option="USER_ENTERED")
        return "Google Sheets"
    return _guardar_excel(df)


def _guardar_excel(df):
    from openpyxl import load_workbook
    if not Path(REGISTRO_XLSX).exists():
        raise FileNotFoundError(f"No encuentro '{REGISTRO_XLSX}'.")
    wb = load_workbook(REGISTRO_XLSX)
    ws = wb["Registro"]
    cols = {c.value: c.column for c in ws[3] if c.value}
    fila = 4
    while ws.cell(fila, cols["Fecha"]).value not in (None, ""):
        fila += 1

    def put(f, col, val):
        if col in cols and pd.notna(val):
            ws.cell(f, cols[col], val)

    for _, r in df.iterrows():
        ws.cell(fila, cols["Fecha"], parse_fecha(r.get("fecha")))
        put(fila, "Hora recogida", r.get("hora_recogida"))
        put(fila, "Zona recogida", r.get("zona_recogida"))
        put(fila, "Distancia (km)", r.get("distancia_km"))
        put(fila, "Importe (€)", r.get("importe_eur"))
        fila += 1
    wb.save(REGISTRO_XLSX)
    return "Excel local"


def leer_registro():
    """Carreras registradas, desde Google Sheets si está configurado."""
    if _usar_sheets():
        try:
            df = pd.DataFrame(_hoja().get_all_records())
            return df if len(df) else None
        except Exception:
            return None
    p = Path(REGISTRO_XLSX)
    if not p.exists():
        return None
    try:
        df = pd.read_excel(p, sheet_name="Registro", skiprows=2)
        df = df[df["Fecha"].notna()]
        if "Nº" in df.columns:
            df = df[df["Nº"].astype(str).str.upper() != "EJEMPLO"]
        df = df.rename(columns={"Importe (€)": "importe_eur", "Distancia (km)": "distancia_km",
                                "Fecha": "fecha", "Hora recogida": "hora_recogida"})
        return df if len(df) else None
    except Exception:
        return None


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


# ----------------------------- Contexto: festivos y clima -----------------------------
@st.cache_data
def es_festivo(fecha):
    try:
        import holidays
        return fecha in holidays.Spain(subdiv="CT", years=fecha.year)
    except Exception:
        return False


@st.cache_data(ttl=1800)
def clima_actual():
    import urllib.request
    url = ("https://api.open-meteo.com/v1/forecast?latitude=41.56&longitude=2.01"
           "&current=temperature_2m,precipitation")
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            c = json.loads(r.read())["current"]
        return {"temp": c.get("temperature_2m"), "lluvia": c.get("precipitation") or 0}
    except Exception:
        return None


# ----------------------------- Modos -----------------------------
def modo_conductor(perfil, geo, nombres, paradas, noche):
    ahora = dt.datetime.now()
    cc1, cc2 = st.columns([1, 2])
    if cc1.toggle("Ahora mismo", value=True):
        dia, hora, fecha = ahora.isoweekday(), ahora.hour, ahora.date()
    else:
        dia = cc1.selectbox("Día", list(DIAS), format_func=lambda d: DIAS[d], index=ahora.isoweekday() - 1)
        hora = cc2.slider("Hora", 0, 23, ahora.hour)
        fecha = ahora.date()

    festivo = es_festivo(fecha)
    dia_efectivo = 7 if festivo else dia   # un festivo se comporta como un domingo

    dem = demanda_distritos(perfil, dia_efectivo, hora)
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

    if items:
        with st.expander("¿Hay algún evento hoy? (opcional)"):
            ev = st.selectbox("Parada cercana al evento", ["(ninguno)"] + [it["nombre"] for it in items])
            if ev != "(ninguno)":
                for it in items:
                    if it["nombre"] == ev:
                        it["valor"] = vmax * 2 + 1
                        it["nivel"] = "Alta"

    items.sort(key=lambda d: d["valor"], reverse=True)

    if festivo:
        st.info("Hoy es festivo: uso el patrón de demanda de un domingo.")
    clima = clima_actual()
    if clima and clima.get("lluvia", 0) > 0:
        st.info("Está lloviendo ahora mismo: suele haber más carreras.")

    if items:
        top = items[0]
        st.markdown(
            f'<div class="hero">'
            f'<div class="hero-label">Ahora ({DIAS[dia]}, {hora:02d}:00), ve a</div>'
            f'<div class="hero-stand">{top["nombre"]}</div>'
            f'<span class="badge">Demanda {top["nivel"].lower()}</span>'
            f'<div class="hero-why">Es la parada con más movimiento previsto a esta hora.</div>'
            f'</div>', unsafe_allow_html=True)
        dibujar_mapa_paradas(items, noche)
    else:
        st.info("Aún no tengo las paradas (`paradas_terrassa.csv`) o el mapa (`terrassa_distritos.geojson`).")


def modo_registrar():
    st.subheader("Registrar un ticket")
    st.caption("Haz una foto del ticket o sube varias. Revisas los datos y se guardan en el registro.")
    api_key = obtener_api_key()
    if not api_key:
        api_key = st.text_input("Clave de Google AI Studio", type="password")
    foto = st.camera_input("Hacer una foto ahora")
    subidas = st.file_uploader("...o subir varias fotos", type=["jpg", "jpeg", "png"],
                               accept_multiple_files=True)
    imagenes = ([foto] if foto is not None else []) + (subidas or [])

    if imagenes and api_key and st.button(f"Leer {len(imagenes)} ticket(s)"):
        filas = []
        barra = st.progress(0.0)
        for i, img in enumerate(imagenes, 1):
            try:
                filas.append(extraer(img, api_key))
            except Exception as e:
                st.error(f"No pude leer {getattr(img, 'name', 'la foto')}: {e}")
            barra.progress(i / len(imagenes))
        if filas:
            st.session_state["tickets"] = pd.DataFrame(filas)

    if "tickets" in st.session_state:
        st.markdown("**Revisa y corrige antes de guardar:**")
        editado = st.data_editor(st.session_state["tickets"], use_container_width=True, num_rows="dynamic")
        if st.button("Añadir al registro"):
            try:
                destino = guardar(editado)
                st.success(f"Añadidas {len(editado)} carrera(s) al registro ({destino}).")
                del st.session_state["tickets"]
            except Exception as e:
                st.error(f"No pude guardar: {e}")


def modo_analisis(perfil, nombres):
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
    st.subheader("Tu rentabilidad (datos reales)")
    reg = leer_registro()
    if reg is None or len(reg) == 0:
        st.info("Aún no hay carreras registradas. Aparecerán aquí en cuanto subas tickets.")
    else:
        imp = pd.to_numeric(reg.get("importe_eur"), errors="coerce")
        km = pd.to_numeric(reg.get("distancia_km"), errors="coerce")
        total, tot_km = imp.sum(), km.sum()
        m1, m2, m3 = st.columns(3)
        m1.metric("Carreras", int(imp.notna().sum()))
        m2.metric("Ingresos", f"{total:,.2f} €")
        m3.metric("€/km medio", f"{total / tot_km:.2f}" if tot_km and not np.isnan(tot_km) else "—")
        if "hora_recogida" in reg.columns:
            horas = pd.to_datetime(reg["hora_recogida"], errors="coerce", format="%H:%M").dt.hour
            por_hora = imp.groupby(horas).sum().dropna()
            if len(por_hora):
                st.markdown("**Tus mejores horas (ingresos)**")
                st.bar_chart(por_hora)


# =============================== Página ===============================
def main():
    perfil = cargar_perfil()
    geo, nombres = cargar_geo()
    paradas = cargar_paradas()

    st.markdown(CSS, unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1])
    c1.markdown('<div class="brandbar"><div class="avatar">T</div>'
                '<div><div class="title">Taxi<b>Terrassa</b></div>'
                '<div class="sub">Dónde hay trabajo, ahora mismo</div></div></div>',
                unsafe_allow_html=True)
    modo = c2.radio("Vista", ["Conductor", "Registrar", "Análisis"],
                    label_visibility="collapsed")
    noche = c2.toggle("Modo noche")
    if noche:
        st.markdown(CSS_NIGHT, unsafe_allow_html=True)

    if modo == "Conductor":
        modo_conductor(perfil, geo, nombres, paradas, noche)
    elif modo == "Registrar":
        modo_registrar()
    else:
        modo_analisis(perfil, nombres)


if __name__ == "__main__":
    main()
