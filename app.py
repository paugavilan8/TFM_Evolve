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
secretos (GEMINI_API_KEY, CARTO_API_KEY para el mapa, SHEET_ID, cuenta de servicio).

    python -m pip install streamlit folium streamlit-folium branca plotly pandas openpyxl \
                          google-generativeai gspread google-auth pillow holidays
    python -m streamlit run app.py
"""

import datetime as dt
import html as _html
import io
import json
import os
import re
import unicodedata
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
NAV = [("Conductor", "explore"), ("Registrar", "receipt_long"), ("Análisis", "insights")]

# Paleta única: rojo de marca, ámbar y gris. La demanda alta es roja.
ROJO = "#C0392B"
ROJO_OSCURO = "#8E2018"
COLOR = {"Alta": "#C0392B", "Media": "#E0902E", "Baja": "#9AA5B1"}
# Sobre fondo oscuro el rojo de marca se queda en 3,2:1 de contraste, y WCAG AA pide
# 4,5:1 para texto pequeño. Sólo "Alta" necesita aclararse; ámbar y gris ya cumplen.
COLOR_OSCURO = {**COLOR, "Alta": "#E4715C"}


def colores(oscuro: bool) -> dict:
    return COLOR_OSCURO if oscuro else COLOR

# El geojson trae nombres genéricos ("Terrassa distrito 01"). Se traducen al nombre
# oficial del distrito, y no al de un barrio, porque cada distrito agrupa varios.
ALIAS_DISTRITO = {
    "Terrassa distrito 01": "Centre",
    "Terrassa distrito 02": "Llevant",
    "Terrassa distrito 03": "Sud",
    "Terrassa distrito 04": "Ponent",
    "Terrassa distrito 05": "Nord-oest",
    "Terrassa distrito 06": "Nord-est",
    "Terrassa distrito 07": "Sud-est",
}

# Un hueco mayor entre dos carreras no es circulación en vacío: es fin de turno,
# comida o descanso. Se usa para no inflar la métrica del objetivo 1.2.
TOPE_VACIO_MIN = 90
# Umbral de similitud para emparejar el texto libre de un ticket con una parada.
# Por debajo se considera que la carrera no empezó en ninguna parada conocida.
UMBRAL_EMPAREJE = 0.5
TOP_K = 3          # el sistema "acierta" si la parada real está entre las K primeras

MODELO = "gemini-2.5-flash"
COLUMNAS = ["fecha", "hora_recogida", "hora_fin", "zona_recogida", "zona_destino",
            "distancia_km", "importe_eur", "origen_servicio", "tarifa"]
# Lo que ve la conductora al revisar un ticket; por dentro se mantienen las claves del JSON.
ETIQUETAS = {"fecha": "Fecha", "hora_recogida": "Hora inicio", "hora_fin": "Hora fin",
             "zona_recogida": "Origen", "zona_destino": "Destino", "distancia_km": "Km",
             "importe_eur": "Importe (€)", "origen_servicio": "Servicio", "tarifa": "Tarifa"}
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
    # El gris secundario da 4,8:1 sobre blanco: cumple WCAG AA.
    "light": {"bg": "#F4F5F7", "surface": "#FFFFFF", "ink": "#1A1A1A", "muted": "#6B7280",
              "line": "#EAEDF1", "shadow": "rgba(20,32,43,.07)", "wash": "#FCEDEB",
              "red-ink": "#C0392B"},
    "dark": {"bg": "#0E1117", "surface": "#161B22", "ink": "#E6EDF3", "muted": "#9AA5B1",
             "line": "#2B333D", "shadow": "rgba(0,0,0,.45)", "wash": "#25181A",
             "red-ink": "#E4715C"},
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
/* El header fijo de Streamlit ocupa 56px. Sin este hueco, la cabecera de marca
   queda por debajo y se ve cortada. */
.block-container { padding: calc(56px + 1rem) .9rem 7.5rem !important; max-width: 780px; }
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
.tt-rank { display: flex; align-items: center; gap: 16px; padding: 16px 20px;
  background: var(--tt-surface); border: 1px solid var(--tt-line); border-radius: 20px;
  margin-bottom: 10px; box-shadow: 0 3px 10px var(--tt-shadow); }
/* La primera parada es justo la del hero: se destaca con el lavado de marca para que
   la recomendación se reconozca también dentro de la lista. */
.tt-rank.top { background: var(--tt-wash); border-color: transparent; }
.tt-rank .n { width: 34px; height: 34px; border-radius: 50%; flex: none; display: flex;
  align-items: center; justify-content: center; background: var(--tt-wash);
  color: var(--tt-ink); font-weight: 700; font-size: .88rem; }
.tt-rank.top .n { background: var(--tt-surface); }
.tt-rank .bd { flex: 1; min-width: 0; }
.tt-rank .nombre { display: flex; align-items: center; gap: 7px; font-weight: 600;
  font-size: 1.02rem; color: var(--tt-ink); margin-bottom: 10px; }
.tt-rank .nombre svg { width: 16px; height: 16px; color: var(--tt-muted); flex: none; }
.tt-rank .nombre span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tt-bar { height: 7px; border-radius: 999px; background: var(--tt-wash); overflow: hidden; }
.tt-rank.top .tt-bar { background: var(--tt-surface); }
.tt-bar i { display: block; height: 100%; border-radius: 999px; }
.tt-rank .lvl { font-size: .85rem; font-weight: 700; flex: none; }

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
.tt-leg { display: flex; gap: 14px; justify-content: center; width: fit-content;
  margin: 12px auto 4px; padding: 7px 16px; border-radius: 999px;
  background: var(--tt-surface); border: 1px solid var(--tt-line);
  box-shadow: 0 3px 10px var(--tt-shadow);
  font-size: .8rem; font-weight: 600; color: var(--tt-muted); }
.tt-leg span { display: inline-flex; align-items: center; gap: 6px; }
.tt-leg i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }

/* ---------- "Ahora mismo" como tarjeta ---------- */
.st-key-tt_ahora { background: var(--tt-surface); border: 1px solid var(--tt-line);
  border-radius: 16px; padding: 12px 18px; box-shadow: 0 4px 12px var(--tt-shadow);
  margin-bottom: 14px; }
/* Las columnas de Streamlit no centran ni empujan por sí solas: hay que centrar la
   fila y mandar el toggle al extremo derecho. */
.st-key-tt_ahora [data-testid="stHorizontalBlock"] { align-items: center; }
.st-key-tt_ahora [data-testid="stColumn"] > div { display: flex; align-items: center;
  min-height: 30px; }
/* El contenedor del toggle se encoge a su contenido (38px), así que no basta con
   alinear: hay que estirarlo primero. 'st-key-tt_vivo' viene de la key del widget. */
.st-key-tt_ahora .st-key-tt_vivo { width: 100% !important; display: flex;
  justify-content: flex-end; }
.st-key-tt_ahora [data-testid="stCheckbox"] { justify-content: flex-end; }
.tt-inline { display: flex; align-items: center; gap: 9px; font-weight: 600;
  color: var(--tt-ink); font-size: .96rem; }
.tt-inline svg { width: 18px; height: 18px; color: var(--tt-red); flex: none; }

/* ---------- Navegación inferior ---------- */
.st-key-tt_nav { position: fixed; left: 0; right: 0; bottom: 0; z-index: 998;
  background: var(--tt-surface); border-top: 1px solid var(--tt-line);
  padding: .55rem 1rem calc(.55rem + env(safe-area-inset-bottom));
  box-shadow: 0 -6px 22px var(--tt-shadow); }
.st-key-tt_nav [data-testid="stHorizontalBlock"] { max-width: 780px; margin: 0 auto; gap: 0; }
.st-key-tt_nav [data-testid="stColumn"] { min-width: 0; }
.st-key-tt_nav .stButton > button { background: transparent !important; border: none !important;
  box-shadow: none !important; padding: 4px 0 2px !important; min-height: 0 !important;
  color: var(--tt-muted) !important; }
.st-key-tt_nav .stButton > button p { display: flex !important; flex-direction: column;
  align-items: center; gap: 5px; margin: 0; line-height: 1.15;
  font-size: .76rem; font-weight: 600; letter-spacing: .01em; }
/* El icono es un <span role="img"> con estilos inline: hay que ganarle con !important. */
.st-key-tt_nav .stButton > button span[role="img"] { font-size: 22px !important;
  display: flex !important; width: 58px; height: 30px; border-radius: 999px;
  align-items: center; justify-content: center; vertical-align: middle !important;
  transition: background .16s ease, color .16s ease; }
.st-key-tt_nav .stButton > button:hover { color: var(--tt-ink) !important; }
.st-key-tt_nav .stButton > button:hover span[role="img"] { background: var(--tt-wash); }
/* La etiqueta activa usa --tt-red-ink, que se aclara en oscuro para no bajar de
   4,5:1 de contraste sobre la superficie. */
.st-key-tt_nav .stButton > button[kind="primary"] { color: var(--tt-red-ink) !important; }
.st-key-tt_nav .stButton > button[kind="primary"] span[role="img"] {
  background: var(--tt-red); color: #fff; }

/* ---------- Retoques a widgets nativos ---------- */
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 18px; }
iframe[title="streamlit_folium.st_folium"] { border-radius: 18px; }
.stButton > button, .stDownloadButton > button { border-radius: 12px; font-weight: 600; }
[data-testid="stExpander"] details { border-radius: 14px; border-color: var(--tt-line); }

@media (max-width: 640px) {
  /* Ojo: también aquí hay que reservar los 56px del header fijo. */
  .block-container { padding: calc(56px + .8rem) .7rem 7.5rem !important; }
  /* Por debajo de 640px Streamlit apila las columnas (min-width: calc(100% - 22.5px)).
     En esta tarjeta no queremos eso: etiqueta y toggle van en la misma línea. */
  .st-key-tt_ahora [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; }
  .st-key-tt_ahora [data-testid="stColumn"] { min-width: 0 !important; }
  .st-key-tt_ahora [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; }
  .tt-title { font-size: 1.78rem; }
  .tt-rank { padding: 13px 15px; gap: 12px; }
  .tt-rank .nombre { font-size: .95rem; margin-bottom: 9px; }
  .tt-rank .n { width: 30px; height: 30px; font-size: .84rem; }
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
def _secreto(nombre):
    try:
        if nombre in st.secrets:
            return st.secrets[nombre]
    except Exception:
        pass
    return os.environ.get(nombre)


def obtener_api_key():
    return _secreto("GEMINI_API_KEY")


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


def _como_lista(resultado):
    """Gemini devuelve un objeto por ticket, o una lista si en la foto hay varios."""
    if isinstance(resultado, list):
        return [r for r in resultado if isinstance(r, dict)]
    return [resultado] if isinstance(resultado, dict) else []


def _falta(valor) -> bool:
    if valor is None:
        return True
    if isinstance(valor, str):
        return valor.strip().lower() in ("", "none", "null", "nan")
    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):
        return False


def ticket_legible(fila) -> bool:
    """Todo ticket de taxi lleva fecha e importe. Si Gemini no encuentra ninguno de los
    dos, la foto no es un ticket o no se puede leer, y no debe llegar a la tabla."""
    return not (_falta(fila.get("fecha")) and _falta(fila.get("importe_eur")))


def revisar_para_guardar(df):
    """Separa las carreras listas para guardar de las que están a medias.

    Las filas vacías (una fila añadida sin querer en la tabla) se descartan sin más. Las
    que no tienen fecha o importe no se guardan: se devuelve su posición en la tabla,
    contando desde 1, para que la conductora sepa cuál corregir.
    """
    listas, a_medias = [], []
    for pos, (_, fila) in enumerate(df.iterrows(), 1):
        if all(_falta(fila.get(c)) for c in COLUMNAS):
            continue
        if _falta(fila.get("fecha")) or _falta(fila.get("importe_eur")):
            a_medias.append(pos)
        else:
            listas.append(fila)
    return pd.DataFrame(listas).reset_index(drop=True), a_medias


def _filas_en_texto(posiciones) -> str:
    if len(posiciones) == 1:
        return f"la fila {posiciones[0]}"
    return "las filas " + ", ".join(map(str, posiciones[:-1])) + f" y {posiciones[-1]}"


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
        # El Excel etiqueta las columnas de otra forma que Google Sheets: se llevan
        # todas al nombre canónico para que el análisis funcione con ambas fuentes.
        df = df.rename(columns={"Fecha": "fecha", "Hora recogida": "hora_recogida",
                                "Hora fin": "hora_fin", "Zona recogida": "zona_recogida",
                                "Zona destino": "zona_destino",
                                "Distancia (km)": "distancia_km", "Importe (€)": "importe_eur",
                                "Origen del servicio": "origen_servicio",
                                "Min. en vacío antes": "vacio_declarado"})
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


def niveles_por_tercil(valores):
    """Reparte Alta / Media / Baja por terciles sobre los valores DISTINTOS.

    Con umbrales fijos sobre el máximo (>=0,66 Alta, >=0,33 Media) "Baja" no salía
    nunca: las 14 paradas viven entre el 0,47 y el 1,00 del máximo, porque el único
    distrito que baja de ese umbral (0827907) no tiene ninguna parada de taxi.

    Se trabaja sobre los valores distintos, no sobre las paradas, para que dos paradas
    del mismo distrito -que por fuerza empatan- reciban siempre la misma etiqueta.
    """
    u = sorted(set(valores), reverse=True)
    if not u:
        return {}
    if len(u) < 3:
        return {v: ("Alta" if i == 0 else "Baja") for i, v in enumerate(u)}
    corte_alta = u[(len(u) - 1) // 3]
    corte_media = u[(2 * (len(u) - 1)) // 3]
    return {v: "Alta" if v >= corte_alta else "Media" if v >= corte_media else "Baja"
            for v in u}


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


# =============================== Ranking de paradas ===============================
@st.cache_data(show_spinner=False)
def paradas_con_distrito(_paradas, _geo):
    """Asigna a cada parada su distrito una sola vez.

    El punto-en-polígono se recalculaba en cada rerun para las catorce paradas; y la
    evaluación del recomendador lo necesitaría además para cada carrera registrada.
    """
    filas = []
    if _paradas is None or _geo is None:
        return filas
    for _, p in _paradas.iterrows():
        if pd.isna(p["lat"]) or pd.isna(p["lon"]):
            continue
        filas.append({"nombre": p["nombre"], "lat": float(p["lat"]), "lon": float(p["lon"]),
                      "plazas": float(p.get("plazas") or 0),
                      "direccion": str(p.get("direccion") or ""),
                      "distrito_id": distrito_de(p["lon"], p["lat"], _geo)})
    return filas


def calcular_items(perfil, paradas_dist, nombres, dia, hora, evento=None):
    """Ranking de paradas para un (día, hora).

    Es la ÚNICA fuente del orden: la usan la vista Conductor y también la evaluación
    del apartado "¿Acierta el sistema?". Si cada una calculase el suyo, la evaluación
    estaría midiendo un sistema distinto del que ve la conductora.
    """
    dem = demanda_distritos(perfil, dia, hora)
    vmax = float(dem.max()) if len(dem) else 0.0
    medias = perfil[perfil["dow"] == dia].groupby("id_str")["viajes"].mean()

    items = []
    for p in paradas_dist:
        did = p["distrito_id"]
        nom_d = nombres.get(did, "")
        items.append(dict(p,
                          valor=float(dem.get(did, 0)) if did else 0.0,
                          media_dia=float(medias.get(did, 0)) if did else 0.0,
                          distrito=ALIAS_DISTRITO.get(nom_d, nom_d)))

    if evento:
        for it in items:
            if it["nombre"] == evento:
                it["valor"] = vmax * 2 + 1

    # El nivel se calcula sobre el conjunto ya completo (incluido el evento), para que
    # mapa, leyenda y ranking usen exactamente la misma escala.
    mapa_niveles = niveles_por_tercil([it["valor"] for it in items])
    for it in items:
        it["nivel"] = mapa_niveles[it["valor"]]

    # La demanda es por distrito, así que varias paradas comparten valor. Deshacemos el
    # empate por número de plazas en lugar de dejarlo al orden del CSV.
    items.sort(key=lambda d: (d["valor"], d.get("plazas", 0)), reverse=True)
    return items


# =============================== Registro: derivadas ===============================
def _sin_acentos(s) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", s)


def _a_fecha(serie):
    """Las fechas llegan en ISO desde el escáner y en formato local desde el Excel.

    Se prueba ISO primero a propósito: con dayfirst=True, "2026-06-01" se interpreta
    como el 6 de enero, lo que desplazaría en silencio el día de la semana de todas
    las carreras de los primeros doce días de cada mes.
    """
    try:
        s = pd.to_datetime(serie, errors="coerce", format="ISO8601")
    except (ValueError, TypeError):
        s = pd.to_datetime(serie, errors="coerce")
    faltan = s.isna()
    if faltan.any():
        s = s.where(~faltan,
                    pd.to_datetime(serie.where(faltan), errors="coerce", dayfirst=True))
    return s


def _a_hora(serie):
    """Acepta '14:21', '14:21:00' y objetos time; devuelve datetime con la hora."""
    s = serie.astype(str).str.strip().str.slice(0, 5)
    return pd.to_datetime(s, format="%H:%M", errors="coerce")


def preparar_registro(reg):
    """Normaliza el registro y deriva duración de la carrera y hueco entre carreras.

    El hueco entre el final de una carrera y el inicio de la siguiente es la medida
    directa del objetivo del trabajo: el tiempo circulando sin pasaje.
    """
    d = reg.copy()
    d["fecha"] = _a_fecha(d.get("fecha"))
    for c in ("importe_eur", "distancia_km"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce") if c in d else np.nan

    h_ini, h_fin = _a_hora(d.get("hora_recogida", pd.Series(dtype=str))), None
    if "hora_fin" in d:
        h_fin = _a_hora(d["hora_fin"])

    def _combinar(h):
        if h is None:
            return pd.Series(pd.NaT, index=d.index)
        return d["fecha"] + pd.to_timedelta(h.dt.hour, unit="h") \
                          + pd.to_timedelta(h.dt.minute, unit="m")

    d["t_ini"] = _combinar(h_ini)
    d["t_fin"] = _combinar(h_fin)
    d["hora"] = h_ini.dt.hour
    # dayofweek de pandas es 0=lunes; el perfil del MITMA usa 1=lunes..7=domingo.
    d["dow"] = d["fecha"].dt.dayofweek + 1

    d = d.dropna(subset=["t_ini"]).sort_values("t_ini").reset_index(drop=True)
    if not len(d):
        return d

    dur = (d["t_fin"] - d["t_ini"]).dt.total_seconds() / 60
    dur = dur.where(dur >= 0, dur + 24 * 60)      # carrera que cruza medianoche
    d["dur_min"] = dur

    hueco = (d["t_ini"] - d["t_fin"].shift(1)).dt.total_seconds() / 60
    mismo_dia = d["fecha"].eq(d["fecha"].shift(1))
    d["hueco_min"] = hueco.where(mismo_dia & hueco.between(0, TOPE_VACIO_MIN))
    return d


def horas_de_turno(d) -> float:
    """Horas comprometidas: de la primera recogida al último final, por día."""
    if not len(d) or d["t_fin"].isna().all():
        return 0.0
    por_dia = d.groupby(d["fecha"].dt.date).agg(ini=("t_ini", "min"), fin=("t_fin", "max"))
    span = (por_dia["fin"] - por_dia["ini"]).dt.total_seconds() / 3600
    return float(span.clip(lower=0).sum())


def emparejar_parada(texto, referencias):
    """Empareja el texto libre de un ticket con una parada, o None si no se parece.

    Los tickets traen la dirección de recogida en texto libre ("RESTAURANTE X
    (Avinguda Y 38)"), no el nombre de una parada, así que hace falta un emparejado
    aproximado. Las carreras no emparejadas se excluyen y se reportan.
    """
    t = _sin_acentos(texto)
    if not t.strip():
        return None
    pal = {w for w in t.split() if len(w) >= 4 and not w.isdigit()}
    num = {w for w in t.split() if w.isdigit()}

    mejor, mejor_p = None, 0.0
    for nombre, ref in referencias:
        partes = ref.split()
        rp = {w for w in partes if len(w) >= 4 and not w.isdigit()}
        rn = {w for w in partes if w.isdigit()}

        comunes = pal & rp
        if not comunes:
            p = 0.0
        else:
            # Cobertura sobre el conjunto menor: un ticket escueto no debe salir
            # penalizado sólo porque la dirección de referencia sea larga.
            p = len(comunes) / max(1, min(len(pal), len(rp)))
            if len(comunes) < 2:
                p *= 0.5        # una sola palabra en común es un indicio débil
        # El número de portal es lo único que separa dos paradas de la misma calle
        # (Rambla d Egara 132 es la del FGC; la 390, la del CAP).
        if num and rn:
            p += 0.35 if (num & rn) else -0.25
        if p > mejor_p:
            mejor, mejor_p = nombre, p
    return mejor if mejor_p >= UMBRAL_EMPAREJE else None


# =============================== Piezas de interfaz ===============================
def encabezado(icono: str, texto: str):
    st.markdown(f'<div class="tt-h">{ICONO[icono]}<span>{esc(texto)}</span></div>',
                unsafe_allow_html=True)


def hero(top, dia, hora, distrito, indice):
    chips = [f"Demanda {top['nivel'].lower()}"]
    if distrito:
        chips.append(distrito)
    if indice:
        chips.append(f"{indice} % de su media")
    chips_html = "".join(f'<span class="tt-chip">{esc(c)}</span>' for c in chips)
    st.markdown(
        f'<div class="tt-hero">'
        f'<div class="tt-eyebrow">{ICONO["bolt"]}'
        f'<span>{esc(DIAS[dia].upper())} · {hora:02d}:00 — VE A</span></div>'
        f'<div class="tt-title">{esc(top["nombre"])}</div>'
        f'<div class="tt-chips">{chips_html}</div>'
        f'<p class="tt-why">Es la parada con más movimiento previsto a esta hora.</p>'
        f'</div>', unsafe_allow_html=True)


def ranking(items, oscuro, n=None):
    """Las barras se estiran sobre el rango visible (no sobre 0) porque la demanda
    entre distritos de Terrassa varía poco y, en absoluto, todas quedarían al 90-100%."""
    vis = items if n is None else items[:n]
    if not vis:
        return
    paleta = colores(oscuro)
    vals = [i["valor"] for i in vis]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    filas = []
    for k, it in enumerate(vis, 1):
        pct = 100 if hi == lo else 20 + round(80 * (it["valor"] - lo) / span)
        c = paleta[it["nivel"]]
        clase = "tt-rank top" if k == 1 else "tt-rank"
        filas.append(
            f'<div class="{clase}"><div class="n">{k}</div><div class="bd">'
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


def leyenda(oscuro, niveles=None):
    paleta = colores(oscuro)
    presentes = [k for k in paleta if niveles is None or k in niveles]
    partes = "".join(f'<span><i style="background:{paleta[k]}"></i>{k}</span>' for k in presentes)
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


def capa_base(oscuro, clave=None):
    """Fondo del mapa: URL de las teselas, atribución y filtro CSS.

    CARTO exige una clave gratuita desde 2026 y, sin ella, sirve las teselas con una marca
    de agua. Si no hay clave se usa OpenStreetMap pasado a gris, para que los colores de
    los niveles destaquen igual que sobre el mapa de CARTO.
    """
    osm = ('&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
           'contributors')
    if clave:
        from urllib.parse import quote
        estilo = "dark_all" if oscuro else "light_all"
        url = (f"https://basemaps.cartocdn.com/rastertiles/{estilo}/{{z}}/{{x}}/{{y}}{{r}}.png"
               f"?key={quote(str(clave), safe='')}")
        return url, osm + ' &copy; <a href="https://carto.com/attributions">CARTO</a>', ""
    filtro = ("grayscale(1) invert(1) brightness(.85) contrast(.9)" if oscuro
              else "grayscale(1) brightness(1.05) contrast(.9)")
    return "https://tile.openstreetmap.org/{z}/{x}/{y}.png", osm, filtro


def dibujar_mapa_paradas(items, oscuro):
    try:
        import folium
        from streamlit_folium import st_folium
    except Exception:
        st.warning("Instala el mapa: python -m pip install folium streamlit-folium")
        return
    paleta = colores(oscuro)
    url, atribucion, filtro = capa_base(oscuro, _secreto("CARTO_API_KEY"))
    # Sin zoom con la rueda: al bajar por la página con el ratón, el mapa se alejaba.
    m = folium.Map(location=CENTRO, zoom_start=14, tiles=None, zoom_control=False,
                   scroll_wheel_zoom=False)
    folium.TileLayer(tiles=url, attr=atribucion, max_zoom=19, class_name="tt-fondo").add_to(m)
    if filtro:
        m.get_root().header.add_child(
            folium.Element(f"<style>.tt-fondo {{ filter: {filtro}; }}</style>"))
    for i, it in enumerate(items):
        if pd.isna(it["lat"]) or pd.isna(it["lon"]):
            continue
        es_top = (i == 0)
        c = paleta[it["nivel"]]
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
    leyenda(oscuro, {it["nivel"] for it in items})


# =============================== Vistas ===============================
def vista_conductor(perfil, geo, nombres, paradas, oscuro):
    ahora = dt.datetime.now()

    # El hero es lo primero que hay que leer, pero depende de los controles que van
    # debajo. Reservamos su hueco y lo rellenamos cuando ya sabemos día y hora.
    hueco_hero = st.container()

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

    paradas_dist = paradas_con_distrito(paradas, geo)
    evento = None
    if paradas_dist:
        with st.expander("¿Hay algún evento hoy? (opcional)"):
            ev = st.selectbox("Parada cercana al evento",
                              ["(ninguno)"] + [p["nombre"] for p in paradas_dist])
            evento = None if ev == "(ninguno)" else ev

    items = calcular_items(perfil, paradas_dist, nombres, dia_efectivo, hora, evento)

    if not items:
        st.info("Aún no tengo las paradas (`paradas_terrassa.csv`) "
                "o el mapa (`terrassa_distritos.geojson`).")
        return

    top = items[0]
    # Se compara con la media diaria de la propia parada: informa de si el momento es
    # bueno o flojo para ella, cosa que el cociente sobre el máximo no haría.
    media = top.get("media_dia") or 0
    indice = round(100 * top["valor"] / media) if media else None
    with hueco_hero:
        hero(top, dia, hora, top.get("distrito"), indice)

    if festivo:
        st.info("Hoy es festivo: uso el patrón de demanda de un domingo.")
    clima = clima_actual()
    if clima and clima.get("lluvia", 0) > 0:
        st.info("Está lloviendo ahora mismo: suele haber más carreras.")

    dibujar_mapa_paradas(items, oscuro)
    encabezado("trend", "Ranking de paradas")
    ranking(items, oscuro)


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
                                          width="stretch"):
        filas = []
        barra = st.progress(0.0)
        for i, img in enumerate(imagenes, 1):
            cual = ("La foto" if len(imagenes) == 1
                    else f"La foto «{getattr(img, 'name', i)}»")
            try:
                leidas = _como_lista(extraer(img, api_key))
            except Exception as e:
                st.error(f"{cual} no se ha podido leer. Comprueba que el ticket se ve entero "
                         "y con buena luz, y vuelve a probar.")
                with st.expander("Detalle técnico"):
                    st.code(str(e))
                leidas = None
            if leidas is not None:
                buenas = [f for f in leidas if ticket_legible(f)]
                if not buenas:
                    st.warning(f"{cual} no parece un ticket de taxi: no encuentro ni la "
                               "fecha ni el importe. Prueba con otra foto.")
                filas.extend(buenas)
            barra.progress(i / len(imagenes))
        barra.empty()
        if filas:
            st.session_state["tickets"] = pd.DataFrame(filas).reindex(columns=COLUMNAS)

    if "tickets" in st.session_state:
        encabezado("grid", "Revisa y corrige antes de guardar")
        editado = st.data_editor(
            st.session_state["tickets"], width="stretch", num_rows="dynamic",
            key="tt_editor", hide_index=True,
            column_config={c: st.column_config.Column(e) for c, e in ETIQUETAS.items()})
        if st.button("Añadir al registro", type="primary", width="stretch"):
            listas, a_medias = revisar_para_guardar(editado)
            if a_medias:
                una = len(a_medias) == 1
                st.error(f"Falta la fecha o el importe en {_filas_en_texto(a_medias)}. "
                         f"{'Complétala o bórrala' if una else 'Complétalas o bórralas'} "
                         "antes de guardar.")
            elif listas.empty:
                st.warning("No hay ninguna carrera que guardar.")
            else:
                try:
                    destino = guardar(listas)
                    st.success(f"Añadidas {len(listas)} carrera(s) al registro ({destino}).")
                    del st.session_state["tickets"]
                except Exception as e:
                    st.error("No se han podido guardar las carreras. Comprueba la conexión "
                             "y vuelve a probar.")
                    with st.expander("Detalle técnico"):
                        st.code(str(e))


def vista_analisis(perfil, geo, nombres, paradas, oscuro):
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
    detalle = None
    if reg is None or len(reg) == 0:
        tarjetas_metrica([("route", "—", "Carreras"), ("euro", "—", "Ingresos"),
                          ("gauge", "—", "€/km")])
        tarjetas_metrica([("clock", "—", "€/hora"), ("bolt", "—", "Min. en vacío"),
                          ("route", "—", "Min. por carrera")])
        st.info("Aún no hay carreras registradas. Aparecerán aquí en cuanto subas tickets.")
        imp = None
    else:
        detalle = preparar_registro(reg)
        imp = pd.to_numeric(reg.get("importe_eur"), errors="coerce")
        km = pd.to_numeric(reg.get("distancia_km"), errors="coerce")
        total, tot_km = imp.sum(), km.sum()
        eur_km = f"{total / tot_km:.2f}" if tot_km and not np.isnan(tot_km) else "—"
        tarjetas_metrica([("route", int(imp.notna().sum()), "Carreras"),
                          ("euro", f"{total:,.0f} €".replace(",", "."), "Ingresos"),
                          ("gauge", eur_km, "€/km")])

        # €/km premia las carreras largas y lentas; lo que un taxista optimiza es el
        # euro por hora de turno. Y los minutos en vacío son el objetivo declarado
        # del trabajo, así que van en portada.
        horas = horas_de_turno(detalle) if len(detalle) else 0.0
        ing = float(detalle["importe_eur"].sum()) if len(detalle) else 0.0
        eur_h = f"{ing / horas:.2f}" if horas > 0 else "—"
        vac = detalle["hueco_min"].dropna() if len(detalle) else pd.Series(dtype=float)
        dur = detalle["dur_min"].dropna() if len(detalle) else pd.Series(dtype=float)
        tarjetas_metrica([
            ("clock", eur_h, "€/hora de turno"),
            ("bolt", f"{vac.median():.0f}" if len(vac) else "—", "Min. en vacío (mediana)"),
            ("route", f"{dur.median():.0f}" if len(dur) else "—", "Min. por carrera"),
        ])

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
                        width="stretch", config={"displayModeBar": False})
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
        st.plotly_chart(estilo_grafico(fig, oscuro, alto=300), width="stretch",
                        config={"displayModeBar": False})
    else:
        st.dataframe(piv, width="stretch")

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
                            width="stretch", config={"displayModeBar": False})
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
                                width="stretch", config={"displayModeBar": False})
            else:
                st.bar_chart(ingresos)

    # --- Tiempo en vacío: el objetivo declarado del trabajo ---
    if detalle is not None and len(detalle) and detalle["hueco_min"].notna().any():
        encabezado("clock", "Tiempo en vacío")
        st.markdown(
            f'<div class="tt-sub">Minutos entre el final de una carrera y la siguiente. '
            f'Los huecos de más de {TOPE_VACIO_MIN} minutos se descartan: son descanso o '
            f'fin de turno, no circulación en vacío.</div>', unsafe_allow_html=True)
        v = detalle.dropna(subset=["hueco_min"])
        por_hora_v = v.groupby("hora")["hueco_min"].mean()
        if tiene_px and len(por_hora_v):
            fig = px.bar(x=por_hora_v.index, y=por_hora_v.values)
            fig.update_traces(marker_color=ROJO, marker_line_width=0,
                              hovertemplate="%{x}:00 · %{y:.0f} min<extra></extra>")
            st.plotly_chart(estilo_grafico(fig, oscuro, sufijo_x="h", alto=220),
                            width="stretch", config={"displayModeBar": False})
        elif len(por_hora_v):
            st.bar_chart(por_hora_v)

        if "zona_destino" in v.columns:
            por_destino = (v.groupby(v["zona_destino"].astype(str).str.slice(0, 34))
                            ["hueco_min"].agg(["mean", "size"]))
            por_destino = por_destino[por_destino["size"] >= 2].sort_values("mean")
            if len(por_destino):
                st.markdown('<div class="tt-sub">Dónde cuesta más volver a cargar tras '
                            'dejar al cliente:</div>', unsafe_allow_html=True)
                st.dataframe(por_destino.rename(columns={"mean": "Min. en vacío",
                                                         "size": "Carreras"}).round(0),
                             width="stretch")

    # --- ¿Acierta el sistema? Evaluación del recomendador ---
    encabezado("gauge", "¿Acierta el sistema?")
    paradas_dist = paradas_con_distrito(paradas, geo)
    if detalle is None or not len(detalle) or not paradas_dist \
            or "zona_recogida" not in detalle.columns:
        st.info("Con carreras registradas, aquí se compara dónde recogiste de verdad "
                "con lo que el sistema recomendaba a esa hora.")
    else:
        refs = [(q["nombre"], _sin_acentos(q["nombre"] + " " + q["direccion"]))
                for q in paradas_dist]
        aciertos = emparejadas = 0
        centro = None
        for _, c in detalle.iterrows():
            if pd.isna(c.get("dow")) or pd.isna(c.get("hora")):
                continue
            real = emparejar_parada(c.get("zona_recogida"), refs)
            if real is None:
                continue
            emparejadas += 1
            orden = calcular_items(perfil, paradas_dist, nombres,
                                   int(c["dow"]), int(c["hora"]))
            if real in [o["nombre"] for o in orden[:TOP_K]]:
                aciertos += 1
            if centro is None:
                centro = orden[0]["nombre"]

        if not emparejadas:
            st.info("Ninguna de las carreras registradas ha podido emparejarse con una "
                    "parada conocida: los tickets recogen direcciones de calle, no "
                    "nombres de parada.")
        else:
            tasa = 100 * aciertos / emparejadas
            azar = 100 * TOP_K / len(paradas_dist)
            tarjetas_metrica([
                ("gauge", f"{tasa:.0f} %", f"Acierto en top-{TOP_K}"),
                ("grid", f"{azar:.0f} %", "Si fuese al azar"),
                ("route", f"{emparejadas}/{len(detalle)}", "Carreras emparejadas"),
            ])
            if tasa > azar:
                st.success(f"El sistema supera al azar: {tasa:.0f} % frente a "
                           f"{azar:.0f} %.")
            else:
                st.warning(f"El sistema no supera al azar ({tasa:.0f} % frente a "
                           f"{azar:.0f} %). Con pocas carreras el dato aún no es "
                           "concluyente.")
            st.caption(f"Se considera acierto que la parada donde empezó la carrera "
                       f"estuviese entre las {TOP_K} primeras del ranking a esa hora y "
                       f"ese día de la semana. Las carreras que no se pueden emparejar "
                       f"con una parada se excluyen del cálculo.")

    # --- Flujos origen-destino de las carreras reales ---
    if detalle is not None and len(detalle) and "zona_destino" in detalle.columns:
        flu = detalle.dropna(subset=["zona_recogida", "zona_destino"])
        if len(flu):
            encabezado("route", "De dónde a dónde")
            tabla_flu = (flu.assign(
                            Origen=flu["zona_recogida"].astype(str).str.slice(0, 30),
                            Destino=flu["zona_destino"].astype(str).str.slice(0, 30))
                         .groupby(["Origen", "Destino"])
                         .agg(Carreras=("importe_eur", "size"),
                              Importe=("importe_eur", "mean"))
                         .sort_values("Carreras", ascending=False).head(15).round(2))
            st.dataframe(tabla_flu, width="stretch")


# =============================== Página ===============================
def _ir_a(destino: str):
    st.session_state["tt_vista"] = destino


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
        vista_analisis(perfil, geo, nombres, paradas, oscuro)

    # Navegación inferior fija. Se dibuja al final para que el estado ya esté leído arriba.
    with st.container(key="tt_nav"):
        for col, (nombre, icono) in zip(st.columns(len(NAV)), NAV):
            col.button(f":material/{icono}: {nombre}", key=f"tt_nav_{nombre}",
                       width="stretch", on_click=_ir_a, args=(nombre,),
                       type="primary" if nombre == vista else "tertiary")


if __name__ == "__main__":
    main()
