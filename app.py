"""
TaxiTerrassa — App unificada (Fase 4)
TFM Pau Gavilán

Tres vistas, navegación inferior tipo app:
  Conductor  — recomienda la parada a la que ir (mapa, ranking, niveles de demanda).
  Registrar  — foto del ticket -> Gemini extrae -> guarda en Google Sheets (o Excel local).
  Análisis   — patrón de demanda por día, transferencia NYC<->Terrassa y rentabilidad real.

Datos que consume (rutas relativas a la raíz del proyecto):
  data/external/  perfil_movilidad_terrassa.csv, terrassa_distritos.geojson, paradas_terrassa.csv
  data/registro/  Registro_carreras_TFM.xlsx  (si no hay Google Sheets configurado)
  data/processed/ demanda_nyc_2023.parquet    (opcional: bloque de transferencia NYC)
Configuración: .streamlit/config.toml y, para escáner/rentabilidad en la nube, los
secretos (GEMINI_API_KEY, SHEET_ID, cuenta de servicio).

    python -m pip install streamlit folium streamlit-folium branca plotly pandas openpyxl \
                          google-generativeai gspread google-auth pillow holidays
    python -m streamlit run app.py
"""

import datetime as dt
import html as _html
import io
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="TaxiTerrassa", page_icon="🚕",
                   layout="centered", initial_sidebar_state="collapsed")

# =============================== Constantes ===============================
# La app vive en la raíz (entrypoint de Streamlit Cloud). Las rutas se anclan al
# fichero para que no dependan del directorio desde el que se lance.
DATA_DIR = Path(__file__).resolve().parent / "data"
PERFIL_CSV = DATA_DIR / "external" / "perfil_movilidad_terrassa.csv"
GEOJSON = DATA_DIR / "external" / "terrassa_distritos.geojson"
PARADAS_CSV = DATA_DIR / "external" / "paradas_terrassa.csv"
REGISTRO_XLSX = DATA_DIR / "registro" / "Registro_carreras_TFM.xlsx"
NYC_PARQUET = DATA_DIR / "processed" / "demanda_nyc_2023.parquet"
CENTRO = [41.5631, 2.0089]
DIAS = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes", 6: "Sábado", 7: "Domingo"}
DIAS_CORTO = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 7: "Dom"}
VISTAS = ["Conductor", "Registrar", "Análisis"]

# Paleta única: rojo de marca + ámbar + gris. La demanda alta es ROJA (antes era verde,
# lo que contradecía el resto de la interfaz).
ROJO = "#C0392B"
ROJO_OSCURO = "#8E2018"
COLOR = {"Alta": "#C0392B", "Media": "#E0902E", "Baja": "#9AA5B1"}

# El geojson trae nombres genéricos ("Terrassa distrito 01"). Rellena esto con los
# barrios reales y aparecerán en el chip del hero y en el mapa de calor.
ALIAS_DISTRITO = {
    # "Terrassa distrito 01": "Centre",
    # "Terrassa distrito 02": "Ca n'Aurell",
}

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

# =============================== Tema y estilos ===============================
# Los widgets nativos de Streamlit siguen [theme] / [theme.dark] de config.toml.
# Aquí sólo definimos los tokens de las tarjetas propias, alineados con ese tema.
TOKENS = {
    "light": {"bg": "#F4F5F7", "surface": "#FFFFFF", "ink": "#1A1A1A", "muted": "#7A828C",
              "line": "#EAEDF1", "shadow": "rgba(20,32,43,.07)", "wash": "#FCEDEB"},
    "dark": {"bg": "#0E1117", "surface": "#161B22", "ink": "#E6EDF3", "muted": "#9AA5B1",
             "line": "#2B333D", "shadow": "rgba(0,0,0,.45)", "wash": "#25181A"},
}
ESCALA = {
    "light": [[0.0, "#FDF0EE"], [0.35, "#F0B4A8"], [0.7, "#D2604F"], [1.0, "#8E2018"]],
    "dark": [[0.0, "#1E1517"], [0.35, "#6B2A22"], [0.7, "#B14434"], [1.0, "#E4715C"]],
}

ICONO = {
    "bolt": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 4 14h6l-1 8 9-12h-6z"/></svg>',
    "clock": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></svg>',
    "trend": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/></svg>',
    "pin": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>',
    "route": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="5.5" r="2.5"/><path d="M8 18.5h6a3.5 3.5 0 0 0 0-7H10a3.5 3.5 0 0 1 0-7h6"/></svg>',
    "euro": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 6.5A6.5 6.5 0 1 0 17 17.5"/><path d="M4 10.5h9M4 14h9"/></svg>',
    "gauge": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4.5-5"/></svg>',
    "receipt": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9.5 8h5M9.5 12h5"/></svg>',
    "chart": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 20V11M12 20V5M19 20v-6"/></svg>',
    "grid": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
}

CSS_BASE = """
.stApp { background: var(--tt-bg); }
footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none !important; }
.block-container { padding: 1rem .9rem 7rem !important; max-width: 780px; }
h1, h2, h3 { letter-spacing: -.02em; }

/* ---------- Cabecera de marca ---------- */
.tt-brand { display: flex; align-items: center; gap: 12px; padding: 2px 0 14px;
  border-bottom: 1px solid var(--tt-line); margin-bottom: 18px; }
.tt-brand .av { width: 44px; height: 44px; border-radius: 50%; flex: none; color: #fff;
  background: linear-gradient(145deg, #D4483A, #8E2018); display: flex; align-items: center;
  justify-content: center; font-weight: 800; font-size: 20px; }
.tt-brand .nm { font-weight: 800; font-size: 1.22rem; color: var(--tt-ink); line-height: 1.1; }
.tt-brand .nm b { color: var(--tt-red); }
.tt-brand .sb { color: var(--tt-muted); font-size: .84rem; }

/* ---------- Tarjeta genérica ---------- */
.tt-card { background: var(--tt-surface); border: 1px solid var(--tt-line); border-radius: 18px;
  padding: 18px 20px; box-shadow: 0 6px 18px var(--tt-shadow); margin-bottom: 14px; }
.tt-h { display: flex; align-items: center; gap: 9px; font-weight: 800; font-size: 1.06rem;
  color: var(--tt-ink); margin: 22px 0 12px; letter-spacing: -.01em; }
.tt-h svg { width: 19px; height: 19px; color: var(--tt-red); flex: none; }
.tt-sub { color: var(--tt-muted); font-size: .9rem; margin: -6px 0 16px; }

/* ---------- Hero de recomendación ---------- */
.tt-hero { background: linear-gradient(135deg, #C0392B 0%, #A32A1E 55%, #7E1B14 100%);
  color: #fff; border-radius: 22px; padding: 22px 24px 24px; margin: 4px 0 16px;
  box-shadow: 0 16px 34px rgba(142,32,24,.32); }
.tt-eyebrow { display: flex; align-items: center; gap: 8px; font-size: .72rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .1em; opacity: .93; }
.tt-eyebrow svg { width: 15px; height: 15px; }
.tt-title { font-size: 2.15rem; font-weight: 800; line-height: 1.05; margin: .28em 0 .5em;
  letter-spacing: -.03em; }
.tt-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.tt-chip { padding: 5px 13px; border-radius: 999px; font-size: .8rem; font-weight: 600;
  background: rgba(255,255,255,.2); }
.tt-why { opacity: .92; font-size: .93rem; margin: 14px 0 0; }

/* ---------- Ranking de paradas ---------- */
.tt-rank { display: flex; align-items: center; gap: 14px; padding: 13px 16px;
  background: var(--tt-surface); border: 1px solid var(--tt-line); border-radius: 16px;
  margin-bottom: 9px; box-shadow: 0 3px 10px var(--tt-shadow); }
.tt-rank .n { width: 30px; height: 30px; border-radius: 50%; flex: none; display: flex;
  align-items: center; justify-content: center; background: var(--tt-wash);
  color: var(--tt-red); font-weight: 700; font-size: .84rem; }
.tt-rank .bd { flex: 1; min-width: 0; }
.tt-rank .nombre { display: flex; align-items: center; gap: 6px; font-weight: 600;
  font-size: .95rem; color: var(--tt-ink); margin-bottom: 7px; }
.tt-rank .nombre svg { width: 15px; height: 15px; color: var(--tt-muted); flex: none; }
.tt-rank .nombre span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tt-bar { height: 6px; border-radius: 999px; background: var(--tt-wash); overflow: hidden; }
.tt-bar i { display: block; height: 100%; border-radius: 999px; }
.tt-rank .lvl { font-size: .8rem; font-weight: 700; flex: none; }

/* ---------- Tarjetas de métrica ---------- */
.tt-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 6px; }
.tt-stat { background: var(--tt-surface); border: 1px solid var(--tt-line); border-radius: 18px;
  padding: 15px 16px; box-shadow: 0 5px 14px var(--tt-shadow); }
.tt-stat svg { width: 20px; height: 20px; color: var(--tt-red); }
.tt-stat .v { font-size: 1.55rem; font-weight: 800; color: var(--tt-ink); letter-spacing: -.03em;
  margin: 8px 0 1px; }
.tt-stat .l { font-size: .8rem; color: var(--tt-muted); }

/* ---------- Pasos numerados ---------- */
.tt-step { display: flex; gap: 15px; align-items: flex-start; background: var(--tt-surface);
  border: 1px solid var(--tt-line); border-radius: 16px; padding: 14px 17px; margin-bottom: 9px;
  box-shadow: 0 3px 10px var(--tt-shadow); }
.tt-step .n { width: 30px; height: 30px; border-radius: 50%; flex: none; display: flex;
  align-items: center; justify-content: center; background: var(--tt-wash);
  color: var(--tt-red); font-weight: 700; font-size: .86rem; }
.tt-step .t { font-weight: 700; color: var(--tt-ink); font-size: .96rem; }
.tt-step .d { color: var(--tt-muted); font-size: .86rem; margin-top: 2px; }

/* ---------- Leyenda del mapa ---------- */
.tt-leg { display: flex; gap: 16px; justify-content: center; margin: 10px 0 4px;
  font-size: .82rem; color: var(--tt-muted); }
.tt-leg span { display: inline-flex; align-items: center; gap: 6px; }
.tt-leg i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }

/* ---------- "Ahora mismo" como tarjeta ---------- */
.st-key-tt_ahora { background: var(--tt-surface); border: 1px solid var(--tt-line);
  border-radius: 16px; padding: 6px 16px; box-shadow: 0 4px 12px var(--tt-shadow); }
.tt-inline { display: flex; align-items: center; gap: 9px; font-weight: 600;
  color: var(--tt-ink); font-size: .96rem; }
.tt-inline svg { width: 18px; height: 18px; color: var(--tt-red); }

/* ---------- Navegación inferior ---------- */
.st-key-tt_nav { position: fixed; left: 0; right: 0; bottom: 0; z-index: 998;
  background: var(--tt-surface); border-top: 1px solid var(--tt-line);
  padding: .55rem 1rem calc(.55rem + env(safe-area-inset-bottom));
  box-shadow: 0 -6px 22px var(--tt-shadow); }
.st-key-tt_nav > div { max-width: 780px; margin: 0 auto; }
.st-key-tt_nav [data-baseweb="button-group"] { width: 100%; gap: 4px; }
.st-key-tt_nav [data-baseweb="button-group"] button { flex: 1 1 0; border: none !important;
  background: transparent !important; font-weight: 600; }
.st-key-tt_nav [data-baseweb="button-group"] button[aria-checked="true"],
.st-key-tt_nav [data-baseweb="button-group"] button[aria-pressed="true"] {
  background: var(--tt-wash) !important; color: var(--tt-red) !important; }

/* ---------- Retoques a widgets nativos ---------- */
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 18px; }
iframe[title="streamlit_folium.st_folium"] { border-radius: 18px; }
.stButton > button, .stDownloadButton > button { border-radius: 12px; font-weight: 600; }
[data-testid="stExpander"] details { border-radius: 14px; border-color: var(--tt-line); }

@media (max-width: 640px) {
  .block-container { padding: .8rem .7rem 7rem !important; }
  .tt-title { font-size: 1.78rem; }
  .tt-stats { gap: 7px; }
  .tt-stat { padding: 12px 12px; }
  .tt-stat .v { font-size: 1.28rem; }
}
"""


def tema_oscuro() -> bool:
    """Tema activo elegido por el usuario; si no se puede leer, cae al base de config.toml."""
    try:
        t = getattr(st, "context", None)
        tipo = getattr(getattr(t, "theme", None), "type", None)
        if tipo:
            return str(tipo).lower() == "dark"
    except Exception:
        pass
    try:
        return str(st.get_option("theme.base") or "light").lower() == "dark"
    except Exception:
        return False


def inyectar_css(oscuro: bool):
    t = TOKENS["dark" if oscuro else "light"]
    variables = "".join(f"--tt-{k}:{v};" for k, v in t.items()) + f"--tt-red:{ROJO};"
    st.markdown(f"<style>.stApp{{{variables}}}{CSS_BASE}</style>", unsafe_allow_html=True)


def esc(x) -> str:
    return _html.escape(str(x))


# =============================== Carga (sin cambios) ===============================
@st.cache_data
def cargar_perfil():
    df = pd.read_csv(PERFIL_CSV)
    df["id_str"] = df["id_origin"].astype(str).str.zfill(7)
    return df


@st.cache_data
def cargar_geo():
    p = GEOJSON
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
    p = PARADAS_CSV
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if not {"nombre", "lat", "lon"}.issubset(df.columns):
        return None
    df = df.dropna(subset=["lat", "lon"])
    return df if len(df) else None


# =============================== Gemini / Sheets (sin cambios) ===============================
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
    if not REGISTRO_XLSX.exists():
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
    p = REGISTRO_XLSX
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


# =============================== Geometría / demanda (sin cambios) ===============================
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


# =============================== Piezas de interfaz ===============================
def encabezado(icono: str, texto: str):
    st.markdown(f'<div class="tt-h">{ICONO[icono]}<span>{esc(texto)}</span></div>',
                unsafe_allow_html=True)


def hero(top, dia, hora, distrito, indice):
    chips = [f"Demanda {top['nivel'].lower()}"]
    if distrito:
        chips.append(distrito)
    chips.append(f"Índice {indice}")
    chips_html = "".join(f'<span class="tt-chip">{esc(c)}</span>' for c in chips)
    st.markdown(
        f'<div class="tt-hero">'
        f'<div class="tt-eyebrow">{ICONO["bolt"]}'
        f'<span>{esc(DIAS[dia].upper())} · {hora:02d}:00 — VE A</span></div>'
        f'<div class="tt-title">{esc(top["nombre"])}</div>'
        f'<div class="tt-chips">{chips_html}</div>'
        f'<p class="tt-why">Es la parada con más movimiento previsto a esta hora.</p>'
        f'</div>', unsafe_allow_html=True)


def ranking(items, n=6):
    """Las barras se estiran sobre el rango visible (no sobre 0) porque la demanda
    entre distritos de Terrassa varía poco y, en absoluto, todas quedarían al 90-100%."""
    vis = items[:n]
    if not vis:
        return
    vals = [i["valor"] for i in vis]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    filas = []
    for k, it in enumerate(vis, 1):
        pct = 100 if hi == lo else 20 + round(80 * (it["valor"] - lo) / span)
        c = COLOR[it["nivel"]]
        filas.append(
            f'<div class="tt-rank"><div class="n">{k}</div><div class="bd">'
            f'<div class="nombre">{ICONO["pin"]}<span>{esc(it["nombre"])}</span></div>'
            f'<div class="tt-bar"><i style="width:{pct}%;background:{c}"></i></div>'
            f'</div><div class="lvl" style="color:{c}">{esc(it["nivel"])}</div></div>')
    st.markdown("".join(filas), unsafe_allow_html=True)


def tarjetas_metrica(trios):
    """trios: lista de (clave_icono, valor, etiqueta)."""
    celdas = "".join(
        f'<div class="tt-stat">{ICONO[ic]}<div class="v">{esc(v)}</div>'
        f'<div class="l">{esc(l)}</div></div>' for ic, v, l in trios)
    st.markdown(f'<div class="tt-stats">{celdas}</div>', unsafe_allow_html=True)


def pasos(lista):
    html = "".join(
        f'<div class="tt-step"><div class="n">{i}</div><div><div class="t">{esc(t)}</div>'
        f'<div class="d">{esc(d)}</div></div></div>'
        for i, (t, d) in enumerate(lista, 1))
    st.markdown(html, unsafe_allow_html=True)


def leyenda(niveles=None):
    presentes = [k for k in COLOR if niveles is None or k in niveles]
    partes = "".join(f'<span><i style="background:{COLOR[k]}"></i>{k}</span>' for k in presentes)
    st.markdown(f'<div class="tt-leg">{partes}</div>', unsafe_allow_html=True)


def estilo_grafico(fig, oscuro, sufijo_x=None, alto=280):
    t = TOKENS["dark" if oscuro else "light"]
    fig.update_layout(
        height=alto, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, 'Segoe UI', sans-serif", size=12, color=t["muted"]),
        margin=dict(l=6, r=6, t=6, b=6), showlegend=False,
        hoverlabel=dict(bgcolor=t["surface"], bordercolor=t["line"],
                        font=dict(color=t["ink"], size=12)),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, showline=True, linecolor=t["line"],
                     ticksuffix=sufijo_x or "", title_text=None)
    fig.update_yaxes(gridcolor=t["line"], zeroline=False, showline=False, title_text=None)
    return fig


def dibujar_mapa_paradas(items, oscuro):
    try:
        import folium
        from streamlit_folium import st_folium
    except Exception:
        st.warning("Instala el mapa: python -m pip install folium streamlit-folium")
        return
    tiles = "cartodbdark_matter" if oscuro else "cartodbpositron"
    m = folium.Map(location=CENTRO, zoom_start=14, tiles=tiles, zoom_control=False)
    for i, it in enumerate(items):
        if pd.isna(it["lat"]) or pd.isna(it["lon"]):
            continue
        es_top = (i == 0)
        c = COLOR[it["nivel"]]
        if es_top:
            folium.CircleMarker(location=[it["lat"], it["lon"]], radius=20, color=c,
                                weight=2, fill=True, fill_color=c, fill_opacity=0.18,
                                opacity=0.5).add_to(m)
        folium.CircleMarker(
            location=[it["lat"], it["lon"]],
            radius=13 if es_top else 7,
            color="#ffffff", weight=2.5 if es_top else 1.5,
            fill=True, fill_color=c, fill_opacity=0.98,
            tooltip=f'{it["nombre"]} — demanda {it["nivel"].lower()}',
        ).add_to(m)
    st_folium(m, height=390, use_container_width=True, returned_objects=[])
    leyenda({it["nivel"] for it in items})


# =============================== Vistas ===============================
def vista_conductor(perfil, geo, nombres, paradas, oscuro):
    ahora = dt.datetime.now()

    with st.container(key="tt_ahora"):
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.markdown(f'<div class="tt-inline">{ICONO["clock"]}<span>Ahora mismo</span></div>',
                    unsafe_allow_html=True)
        en_vivo = c2.toggle("Ahora mismo", value=True, label_visibility="collapsed",
                            key="tt_vivo")

    if en_vivo:
        dia, hora, fecha = ahora.isoweekday(), ahora.hour, ahora.date()
    else:
        d1, d2 = st.columns([1, 2])
        dia = d1.selectbox("Día", list(DIAS), format_func=lambda d: DIAS[d],
                           index=ahora.isoweekday() - 1)
        hora = d2.slider("Hora", 0, 23, ahora.hour)
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
            nom_d = nombres.get(did, "")
            items.append({"nombre": p["nombre"], "lat": float(p["lat"]), "lon": float(p["lon"]),
                          "valor": v, "nivel": nivel(v, vmax),
                          "distrito": ALIAS_DISTRITO.get(nom_d, nom_d),
                          "plazas": float(p.get("plazas") or 0)})

    if items:
        with st.expander("¿Hay algún evento hoy? (opcional)"):
            ev = st.selectbox("Parada cercana al evento",
                              ["(ninguno)"] + [it["nombre"] for it in items])
            if ev != "(ninguno)":
                for it in items:
                    if it["nombre"] == ev:
                        it["valor"] = vmax * 2 + 1
                        it["nivel"] = "Alta"

    # La demanda es por distrito, así que varias paradas comparten valor. Deshacemos
    # el empate por número de plazas en lugar de dejarlo al orden del CSV.
    items.sort(key=lambda d: (d["valor"], d.get("plazas", 0)), reverse=True)

    if not items:
        st.info("Aún no tengo las paradas (`paradas_terrassa.csv`) "
                "o el mapa (`terrassa_distritos.geojson`).")
        return

    top = items[0]
    tope = max((i["valor"] for i in items), default=0) or 1
    hero(top, dia, hora, top.get("distrito"), round(100 * top["valor"] / tope))

    if festivo:
        st.info("Hoy es festivo: uso el patrón de demanda de un domingo.")
    clima = clima_actual()
    if clima and clima.get("lluvia", 0) > 0:
        st.info("Está lloviendo ahora mismo: suele haber más carreras.")

    dibujar_mapa_paradas(items, oscuro)
    encabezado("trend", "Ranking de paradas")
    ranking(items)


def vista_registrar():
    encabezado("receipt", "Registrar un ticket")
    st.markdown('<div class="tt-sub">Haz una foto del ticket o sube varias. '
                'Revisas los datos y se guardan en tu registro.</div>', unsafe_allow_html=True)

    api_key = obtener_api_key()
    if not api_key:
        api_key = st.text_input("Clave de Google AI Studio", type="password")

    fuente = st.segmented_control("Origen de las fotos", ["Hacer una foto", "Subir fotos"],
                                  default="Hacer una foto", label_visibility="collapsed",
                                  key="tt_fuente") or "Hacer una foto"

    imagenes = []
    if fuente == "Hacer una foto":
        foto = st.camera_input("Enfoca el ticket", label_visibility="collapsed")
        if foto is not None:
            imagenes = [foto]
    else:
        subidas = st.file_uploader("Fotos de tickets", type=["jpg", "jpeg", "png"],
                                   accept_multiple_files=True, label_visibility="collapsed")
        imagenes = list(subidas or [])

    if not imagenes:
        pasos([
            ("Fotografía el ticket", "Con la cámara del móvil, sin escribir nada."),
            ("Revisa los datos", "Fecha, hora, zona, kilómetros e importe."),
            ("Guarda la carrera", "Se suma a tu registro y a los gráficos de Análisis."),
        ])

    if imagenes and api_key and st.button(f"Leer {len(imagenes)} ticket(s)", type="primary",
                                          use_container_width=True):
        filas = []
        barra = st.progress(0.0)
        for i, img in enumerate(imagenes, 1):
            try:
                filas.append(extraer(img, api_key))
            except Exception as e:
                st.error(f"No pude leer {getattr(img, 'name', 'la foto')}: {e}")
            barra.progress(i / len(imagenes))
        barra.empty()
        if filas:
            st.session_state["tickets"] = pd.DataFrame(filas)

    if "tickets" in st.session_state:
        encabezado("grid", "Revisa y corrige antes de guardar")
        editado = st.data_editor(st.session_state["tickets"], use_container_width=True,
                                 num_rows="dynamic", key="tt_editor")
        if st.button("Añadir al registro", type="primary", use_container_width=True):
            try:
                destino = guardar(editado)
                st.success(f"Añadidas {len(editado)} carrera(s) al registro ({destino}).")
                del st.session_state["tickets"]
            except Exception as e:
                st.error(f"No pude guardar: {e}")


def vista_analisis(perfil, nombres, oscuro):
    try:
        import plotly.express as px
        tiene_px = True
    except Exception:
        tiene_px = False

    st.markdown('<div class="tt-h" style="margin-top:4px">Análisis</div>'
                '<div class="tt-sub">Patrón de demanda de Terrassa y rentabilidad '
                'de tus carreras.</div>', unsafe_allow_html=True)

    # --- Rentabilidad real, arriba porque es lo que el conductor mira primero ---
    reg = leer_registro()
    if reg is None or len(reg) == 0:
        tarjetas_metrica([("route", "—", "Carreras"), ("euro", "—", "Ingresos"),
                          ("gauge", "—", "€/km")])
        st.info("Aún no hay carreras registradas. Aparecerán aquí en cuanto subas tickets.")
        imp = None
    else:
        imp = pd.to_numeric(reg.get("importe_eur"), errors="coerce")
        km = pd.to_numeric(reg.get("distancia_km"), errors="coerce")
        total, tot_km = imp.sum(), km.sum()
        eur_km = f"{total / tot_km:.2f}" if tot_km and not np.isnan(tot_km) else "—"
        tarjetas_metrica([("route", int(imp.notna().sum()), "Carreras"),
                          ("euro", f"{total:,.0f} €".replace(",", "."), "Ingresos"),
                          ("gauge", eur_km, "€/km")])

    # --- Selector de día ---
    dia = st.segmented_control("Día de la semana", list(DIAS),
                               format_func=lambda d: DIAS_CORTO[d],
                               default=dt.datetime.now().isoweekday(),
                               label_visibility="collapsed", key="tt_dia")
    if dia is None:
        dia = dt.datetime.now().isoweekday()

    sub = perfil[perfil["dow"] == dia]

    encabezado("chart", "Demanda media por hora")
    por_hora = sub.groupby("hour")["viajes"].mean().reindex(range(24))
    if tiene_px:
        fig = px.line(x=por_hora.index, y=por_hora.values)
        fig.update_traces(line=dict(color=ROJO, width=3.2, shape="spline", smoothing=0.9),
                          hovertemplate="%{x}:00 · %{y:,.0f} viajes<extra></extra>")
        fig.update_yaxes(rangemode="tozero")
        st.plotly_chart(estilo_grafico(fig, oscuro, sufijo_x="h", alto=250),
                        use_container_width=True, config={"displayModeBar": False})
    else:
        st.line_chart(por_hora)

    encabezado("grid", "Mapa de calor por parada")
    piv = sub.pivot_table(index="id_str", columns="hour", values="viajes", aggfunc="mean")
    piv = piv.reindex(columns=range(24))
    piv.index = [ALIAS_DISTRITO.get(nombres.get(i, i), nombres.get(i, i)) for i in piv.index]
    piv = piv.loc[piv.mean(axis=1).sort_values(ascending=False).index]
    if tiene_px:
        fig = px.imshow(piv, aspect="auto",
                        color_continuous_scale=ESCALA["dark" if oscuro else "light"])
        fig.update_traces(xgap=3, ygap=3,
                          hovertemplate="%{y} · %{x}:00 · %{z:,.0f}<extra></extra>")
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(estilo_grafico(fig, oscuro, alto=300), use_container_width=True,
                        config={"displayModeBar": False})
    else:
        st.dataframe(piv, use_container_width=True)

    # --- Transferencia NYC (sin cambios de lógica) ---
    if NYC_PARQUET.exists():
        encabezado("trend", "Transferencia: NYC vs Terrassa")
        nyc = pd.read_parquet(NYC_PARQUET)
        nh = nyc.groupby("hora")["demanda"].mean()
        th = perfil.groupby("hour")["viajes"].mean()
        comp = pd.DataFrame({"NYC (taxi)": nh / nh.sum(), "Terrassa": th / th.sum()})
        r = np.corrcoef(comp["NYC (taxi)"], comp["Terrassa"])[0, 1]
        if tiene_px:
            fig = px.line(comp)
            fig.update_traces(line=dict(width=2.8, shape="spline", smoothing=0.9))
            fig.data[0].line.color = "#9AA5B1"
            fig.data[1].line.color = ROJO
            fig.update_layout(showlegend=True,
                              legend=dict(orientation="h", y=1.15, x=0, title_text=""))
            st.plotly_chart(estilo_grafico(fig, oscuro, sufijo_x="h", alto=240),
                            use_container_width=True, config={"displayModeBar": False})
        else:
            st.line_chart(comp)
        tarjetas_metrica([("trend", f"r = {r:.3f}", "Correlación horaria"),
                          ("clock", f"{int(th.idxmax()):02d}:00", "Pico Terrassa"),
                          ("clock", f"{int(nh.idxmax()):02d}:00", "Pico NYC")])

    # --- Mejores horas del conductor ---
    if imp is not None and "hora_recogida" in reg.columns:
        horas = pd.to_datetime(reg["hora_recogida"], errors="coerce", format="%H:%M").dt.hour
        ingresos = imp.groupby(horas).sum().dropna()
        if len(ingresos):
            encabezado("euro", "Tus mejores horas")
            if tiene_px:
                fig = px.bar(x=ingresos.index, y=ingresos.values)
                fig.update_traces(marker_color=ROJO, marker_line_width=0,
                                  hovertemplate="%{x}:00 · %{y:,.2f} €<extra></extra>")
                st.plotly_chart(estilo_grafico(fig, oscuro, sufijo_x="h", alto=230),
                                use_container_width=True, config={"displayModeBar": False})
            else:
                st.bar_chart(ingresos)


# =============================== Página ===============================
def main():
    oscuro = tema_oscuro()
    inyectar_css(oscuro)

    perfil = cargar_perfil()
    geo, nombres = cargar_geo()
    paradas = cargar_paradas()

    st.markdown('<div class="tt-brand"><div class="av">T</div>'
                '<div><div class="nm">Taxi<b>Terrassa</b></div>'
                '<div class="sb">Dónde hay trabajo, ahora mismo</div></div></div>',
                unsafe_allow_html=True)

    vista = st.session_state.get("tt_vista") or "Conductor"
    if vista == "Conductor":
        vista_conductor(perfil, geo, nombres, paradas, oscuro)
    elif vista == "Registrar":
        vista_registrar()
    else:
        vista_analisis(perfil, nombres, oscuro)

    # Navegación inferior fija. Se dibuja al final para que el estado ya esté leído arriba.
    with st.container(key="tt_nav"):
        st.segmented_control("Vista", VISTAS, default="Conductor",
                             label_visibility="collapsed", key="tt_vista")


if __name__ == "__main__":
    main()
