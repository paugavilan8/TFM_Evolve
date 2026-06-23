"""
Escáner de tickets de taxi -> registro (Fase 4, captura de datos desde el móvil)
TFM Pau Gavilán

Haz una foto del ticket (o sube varias). Un modelo de visión (Gemini) extrae los datos,
tú los revisas/corriges, y se guardan:
  - en GOOGLE SHEETS si está configurado (para usarlo desde el móvil, desplegado), o
  - en el Excel local (Registro_carreras_TFM.xlsx) si no hay Sheets configurado.

Claves necesarias (en .streamlit/secrets.toml y/o en los Secrets de Streamlit Cloud):
  GEMINI_API_KEY = "AIza..."            # de aistudio.google.com (requiere facturación activada)
  SHEET_ID = "id_de_tu_google_sheet"    # solo para guardar en Sheets
  [gcp_service_account]                  # solo para Sheets: contenido del JSON de la cuenta de servicio
  ...

Ejecutar:
    python -m pip install streamlit google-generativeai gspread google-auth openpyxl pillow pandas
    python -m streamlit run escanear_tickets.py
"""

import io
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

REGISTRO = "Registro_carreras_TFM.xlsx"
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
            return datetime.strptime(str(s), fmt).date()
        except ValueError:
            pass
    return s


# ----------------------------- Guardado -----------------------------
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


def _guardar_sheets(df):
    import gspread
    from google.oauth2.service_account import Credentials
    info = _service_account_info()
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    ws = gspread.authorize(creds).open_by_key(st.secrets["SHEET_ID"]).sheet1
    for _, r in df.iterrows():
        fila = ["" if pd.isna(r.get(c)) else r.get(c) for c in COLUMNAS]
        fila[0] = str(parse_fecha(r.get("fecha")))
        ws.append_row(fila, value_input_option="USER_ENTERED")
    return "Google Sheets"


def _guardar_excel(df):
    from openpyxl import load_workbook
    if not Path(REGISTRO).exists():
        raise FileNotFoundError(f"No encuentro '{REGISTRO}'.")
    wb = load_workbook(REGISTRO)
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
        put(fila, "Hora fin", r.get("hora_fin"))
        put(fila, "Zona recogida", r.get("zona_recogida"))
        put(fila, "Zona destino", r.get("zona_destino"))
        put(fila, "Distancia (km)", r.get("distancia_km"))
        put(fila, "Importe (€)", r.get("importe_eur"))
        put(fila, "Origen del servicio", r.get("origen_servicio"))
        tarifa = r.get("tarifa")
        put(fila, "Notas", f"Tarifa {tarifa}" if pd.notna(tarifa) else None)
        fila += 1
    wb.save(REGISTRO)
    return "Excel local"


def guardar(df):
    if _usar_sheets():
        return _guardar_sheets(df)
    return _guardar_excel(df)


# =============================== UI ===============================
st.set_page_config(page_title="Escanear tickets de taxi", layout="centered")
st.title("Escanear tickets de taxi")
st.caption("Haz una foto del ticket o sube varias. Revisas los datos y se guardan en el registro.")

api_key = obtener_api_key()
if api_key:
    st.caption("Clave configurada correctamente.")
else:
    api_key = st.text_input("Clave de Google AI Studio (solo si no la has guardado)",
                            type="password", help="Gratis en aistudio.google.com/apikey")

st.subheader("1. Añade los tickets")
foto = st.camera_input("Hacer una foto ahora")
subidas = st.file_uploader("...o subir varias fotos", type=["jpg", "jpeg", "png"],
                           accept_multiple_files=True)

imagenes = []
if foto is not None:
    imagenes.append(foto)
if subidas:
    imagenes.extend(subidas)

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
    st.subheader("2. Revisa y corrige")
    st.caption("Comprueba que los datos son correctos antes de guardar. Edita cualquier celda.")
    editado = st.data_editor(st.session_state["tickets"], use_container_width=True, num_rows="dynamic")

    st.subheader("3. Guardar")
    if st.button("Añadir al registro"):
        try:
            destino = guardar(editado)
            st.success(f"Añadidas {len(editado)} carrera(s) al registro ({destino}).")
            del st.session_state["tickets"]
        except Exception as e:
            st.error(f"No pude guardar: {e}")
