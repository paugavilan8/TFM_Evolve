"""
Descarga las paradas de taxi de Terrassa desde OpenStreetMap (Overpass) -> paradas_terrassa.csv
TFM Pau Gavilán

Ejecuta una vez en TU máquina (necesita internet), desde la raíz del proyecto:
    python scripts/obtener_paradas.py

Después puede abrirse data/external/paradas_terrassa.csv para añadir o corregir las que la conductora
conozca de verdad (es la experta del terreno). Columnas: nombre, lat, lon.
"""

import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

# Este script vive en scripts/; el CSV va a data/external/ de la raíz del proyecto.
SALIDA = Path(__file__).resolve().parents[1] / "data" / "external" / "paradas_terrassa.csv"

# Bounding box aproximado de Terrassa (sur, oeste, norte, este)
QUERY = """
[out:json][timeout:25];
nwr[amenity=taxi](41.52,1.95,41.61,2.07);
out center;
"""

URL = "https://overpass-api.de/api/interpreter"


def main():
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(URL, data=data, headers={"User-Agent": "TFM-taxi/1.0"})
    res = json.loads(urllib.request.urlopen(req, timeout=60).read())

    filas = []
    for el in res.get("elements", []):
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        nombre = el.get("tags", {}).get("name", "Parada de taxi")
        filas.append({"nombre": nombre, "lat": lat, "lon": lon})

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["nombre", "lat", "lon"])
        w.writeheader()
        w.writerows(filas)

    print(f"{len(filas)} paradas guardadas en {SALIDA}")
    if len(filas) == 0:
        print("OSM no tenía paradas etiquetadas en Terrassa. "
              "Crear el CSV a mano: columnas nombre, lat, lon.")


if __name__ == "__main__":
    main()
