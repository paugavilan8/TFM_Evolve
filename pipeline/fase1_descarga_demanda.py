"""
Fase 1 — Descarga y agregación del NYC Yellow Taxi a TABLA DE DEMANDA
TFM Pau Gavilán — Sistema de predicción de demanda para taxistas autónomos

Qué hace este script:
  1. Descarga los 12 Parquet mensuales de Yellow Taxi (fuente oficial TLC, vía CloudFront).
  2. Agrega los millones de viajes a una tabla de demanda: (zona, fecha, hora) -> nº de recogidas.
  3. RELLENA CEROS: toda combinación zona×fecha×hora sin viajes = 0 (no es un dato que falta;
     es "no hubo demanda"). Sin esto el modelo nunca aprende cuándo NO hay demanda.
  4. Une el nombre de zona (Taxi Zone Lookup) y guarda el resultado en Parquet (+ CSV opcional).

Requiere conexión a internet.
Requisitos:  pip install duckdb pandas pyarrow
Uso:         python fase1_descarga_demanda.py
"""

import os
import urllib.request
from pathlib import Path

import duckdb

# ----------------------------- Configuración -----------------------------
YEAR = 2023                       # 1 año reciente = estacionalidad completa. Evita 2020-2021 (COVID).
MONTHS = range(1, 13)
# Raíz del proyecto (este script vive en pipeline/), para que las rutas de datos
# no dependan del directorio desde el que lo lances.
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"          # parquet originales de la TLC
OUT_DIR = ROOT / "data" / "processed"    # tabla de demanda agregada
BASE = "https://d37ci6vzurychx.cloudfront.net/trip-data"            # host de descarga que enlaza la TLC
ZONE_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"
EXPORT_CSV = False                # el CSV de la rejilla completa es grande (~2M filas). Parquet basta.
# Si algún enlace da 404, confirma la URL exacta en:
#   https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
# -------------------------------------------------------------------------

RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)


def download(url, dest):
    if os.path.exists(dest):
        print(f"  ya existe: {dest}")
        return
    print(f"  descargando: {url}")
    urllib.request.urlretrieve(url, dest)


# 1) Descargar -------------------------------------------------------------
print("1) Descargando ficheros (puede tardar; ~50-60 MB por mes)...")
for m in MONTHS:
    fn = f"yellow_tripdata_{YEAR}-{m:02d}.parquet"
    download(f"{BASE}/{fn}", RAW_DIR / fn)
zone_csv = RAW_DIR / "taxi_zone_lookup.csv"
download(ZONE_URL, zone_csv)

# 2) + 3) Agregar y rellenar ceros con DuckDB ------------------------------
print("2) Agregando viajes -> tabla de demanda (zona × fecha × hora)...")
con = duckdb.connect()
# as_posix(): DuckDB recibe las rutas con '/' también en Windows.
glob = (RAW_DIR / f"yellow_tripdata_{YEAR}-*.parquet").as_posix()

# Conteos observados (solo zona-hora que SÍ tuvieron viajes)
con.execute(f"""
CREATE TABLE conteos AS
SELECT
    PULocationID                              AS zona,
    CAST(tpep_pickup_datetime AS DATE)        AS fecha,
    EXTRACT(hour FROM tpep_pickup_datetime)   AS hora,
    COUNT(*)                                  AS demanda
FROM read_parquet('{glob}', union_by_name = true)
WHERE tpep_pickup_datetime >= DATE '{YEAR}-01-01'
  AND tpep_pickup_datetime <  DATE '{YEAR + 1}-01-01'   -- descarta timestamps corruptos fuera de rango
  AND PULocationID IS NOT NULL
GROUP BY 1, 2, 3
""")

# Rejilla COMPLETA: cada zona × cada fecha observada × las 24 horas
con.execute("""
CREATE TABLE rejilla AS
SELECT z.zona, d.fecha, h.hora
FROM (SELECT DISTINCT zona  FROM conteos) z
CROSS JOIN (SELECT DISTINCT fecha FROM conteos) d
CROSS JOIN (SELECT UNNEST(range(0, 24)) AS hora) h
""")

# Left join -> los huecos se rellenan con 0
con.execute("""
CREATE TABLE demanda AS
SELECT r.zona, r.fecha, r.hora, COALESCE(c.demanda, 0) AS demanda
FROM rejilla r
LEFT JOIN conteos c USING (zona, fecha, hora)
""")

# 4) Nombre de zona + variables de calendario base -------------------------
con.execute(f"""
CREATE TABLE zonas AS
SELECT LocationID AS zona, Zone AS nombre_zona, Borough AS distrito
FROM read_csv_auto('{zone_csv.as_posix()}')
""")

con.execute("""
CREATE TABLE demanda_final AS
SELECT
    d.zona, z.nombre_zona, z.distrito,
    d.fecha, d.hora,
    EXTRACT(dow FROM d.fecha) AS dia_semana,   -- 0 = domingo ... 6 = sábado
    (EXTRACT(dow FROM d.fecha) IN (0, 6)) AS es_finde,
    d.demanda
FROM demanda d
LEFT JOIN zonas z USING (zona)
ORDER BY d.zona, d.fecha, d.hora
""")

# Guardar ------------------------------------------------------------------
out_parquet = OUT_DIR / f"demanda_nyc_{YEAR}.parquet"
con.execute(f"COPY demanda_final TO '{out_parquet.as_posix()}' (FORMAT PARQUET)")
if EXPORT_CSV:
    out_csv = OUT_DIR / f"demanda_nyc_{YEAR}.csv"
    con.execute(f"COPY demanda_final TO '{out_csv.as_posix()}' (HEADER, DELIMITER ',')")

# Resumen rápido (un mini-EDA de sanidad)
n, nz, tot = con.execute(
    "SELECT COUNT(*), COUNT(DISTINCT zona), SUM(demanda) FROM demanda_final"
).fetchone()
print(f"\nTabla de demanda lista: {n:,} filas | {nz} zonas | {tot:,} recogidas totales")
print(f"   Guardada en: {out_parquet}")
print("\n   Demanda media por hora del día (chequeo de sanidad):")
print(con.execute("""
    SELECT hora, ROUND(AVG(demanda), 1) AS demanda_media
    FROM demanda_final GROUP BY hora ORDER BY hora
""").df().to_string(index=False))
