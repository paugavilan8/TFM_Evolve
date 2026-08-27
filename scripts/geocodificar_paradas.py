"""
Añade coordenadas (lat, lon) a paradas_terrassa.csv geolocalizando las direcciones
con Nominatim (OpenStreetMap). TFM Pau Gavilán.

Ejecuta una vez en TU máquina (necesita internet), desde la raíz del proyecto:
    python scripts/geocodificar_paradas.py

Respeta el límite de Nominatim (1 consulta/segundo). Si alguna dirección no se
encuentra, la deja sin coordenadas y te avisa para que la ajustes a mano.
"""

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Este script vive en scripts/; el CSV está en data/external/ de la raíz del proyecto.
ARCHIVO = Path(__file__).resolve().parents[1] / "data" / "external" / "paradas_terrassa.csv"
URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "TFM-taxi-pau/1.0 (uso academico)"}


def geocode(direccion):
    q = f"{direccion}, Terrassa, Barcelona, España"
    params = urllib.parse.urlencode({"q": q, "format": "json", "limit": 1})
    req = urllib.request.Request(f"{URL}?{params}", headers=HEADERS)
    try:
        res = json.loads(urllib.request.urlopen(req, timeout=30).read())
        if res:
            return float(res[0]["lat"]), float(res[0]["lon"])
    except Exception as e:
        print(f"   (error: {e})")
    return "", ""


rows = list(csv.DictReader(open(ARCHIVO, encoding="utf-8")))
for r in rows:
    lat, lon = geocode(r["direccion"])
    r["lat"], r["lon"] = lat, lon
    print(f'{r["nombre"][:32]:32s} -> {lat}, {lon}')
    time.sleep(1.1)

campos = ["nombre", "direccion", "plazas", "lat", "lon"]
with open(ARCHIVO, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=campos)
    w.writeheader()
    w.writerows(rows)

faltan = [r["nombre"] for r in rows if not r["lat"]]
print(f"\nListo. {len(rows) - len(faltan)}/{len(rows)} paradas geolocalizadas en {ARCHIVO}.")
if faltan:
    print("Sin coordenadas (ponlas a mano en el CSV):", ", ".join(faltan))
