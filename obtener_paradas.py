"""
Descarga las paradas de taxi de Terrassa desde OpenStreetMap (Overpass) -> paradas_terrassa.csv
TFM Pau Gavilán

Ejecuta una vez en TU máquina (necesita internet):
    python obtener_paradas.py

Después puedes abrir paradas_terrassa.csv y añadir/corregir las paradas que tu madre
conozca de verdad (es la experta del terreno). Columnas: nombre, lat, lon.
"""

import csv
import json
import urllib.parse
import urllib.request

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

    with open("paradas_terrassa.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["nombre", "lat", "lon"])
        w.writeheader()
        w.writerows(filas)

    print(f"{len(filas)} paradas guardadas en paradas_terrassa.csv")
    if len(filas) == 0:
        print("OSM no tenía paradas etiquetadas en Terrassa. "
              "Crea el CSV a mano con tu madre: columnas nombre, lat, lon.")


if __name__ == "__main__":
    main()
