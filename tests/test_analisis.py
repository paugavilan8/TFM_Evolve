"""
Pruebas de la lógica de análisis del registro y de la evaluación del recomendador.
TFM Pau Gavilán

Con dos carreras reales registradas no se puede saber si estos cálculos son correctos,
así que se comprueban con casos sintéticos de respuesta conocida.

    python tests/test_analisis.py
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402

fallos = []


def check(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print("  %-58s %s" % (nombre, "OK" if ok else "FALLA  (%r != %r)" % (obtenido, esperado)))
    if not ok:
        fallos.append(nombre)


# --------------------------------------------------------------------------
print("1) preparar_registro: duración, hueco y corte de fin de turno")
reg = pd.DataFrame([
    # dos carreras seguidas: hueco de 15 min entre el fin de la 1ª y el inicio de la 2ª
    {"fecha": "2026-06-01", "hora_recogida": "08:00", "hora_fin": "08:20",
     "zona_recogida": "A", "zona_destino": "B", "distancia_km": 3, "importe_eur": 9},
    {"fecha": "2026-06-01", "hora_recogida": "08:35", "hora_fin": "08:50",
     "zona_recogida": "B", "zona_destino": "C", "distancia_km": 2, "importe_eur": 7},
    # hueco de 3 h: es fin de turno, no debe contar como vacío
    {"fecha": "2026-06-01", "hora_recogida": "11:50", "hora_fin": "12:10",
     "zona_recogida": "C", "zona_destino": "D", "distancia_km": 4, "importe_eur": 11},
    # otro día: el hueco no debe cruzar la frontera de día
    {"fecha": "2026-06-02", "hora_recogida": "09:00", "hora_fin": "09:30",
     "zona_recogida": "D", "zona_destino": "A", "distancia_km": 5, "importe_eur": 13},
    # carrera que cruza medianoche: 23:50 -> 00:10 son 20 minutos, no -1420
    {"fecha": "2026-06-02", "hora_recogida": "23:50", "hora_fin": "00:10",
     "zona_recogida": "A", "zona_destino": "B", "distancia_km": 6, "importe_eur": 15},
])
d = app.preparar_registro(reg)

check("filas procesadas", len(d), 5)
check("duración de la 1ª carrera (min)", float(d.loc[0, "dur_min"]), 20.0)
check("duración cruzando medianoche (min)", float(d.loc[4, "dur_min"]), 20.0)
check("hueco de la 2ª carrera (min)", float(d.loc[1, "hueco_min"]), 15.0)
check("hueco de 3 h descartado (> TOPE_VACIO_MIN)", pd.isna(d.loc[2, "hueco_min"]), True)
check("hueco al cambiar de día descartado", pd.isna(d.loc[3, "hueco_min"]), True)
check("huecos válidos contados", int(d["hueco_min"].notna().sum()), 1)
check("dow 2026-06-01 es lunes = 1", int(d.loc[0, "dow"]), 1)
check("hora de recogida extraída", int(d.loc[0, "hora"]), 8)

# horas de turno: día 1 de 08:00 a 12:10 = 4,1667 h; día 2 de 09:00 a 09:30 = 0,5 h
check("horas de turno (redondeado a 2 dec)", round(app.horas_de_turno(d), 2), 4.67)

# --------------------------------------------------------------------------
print("\n2) emparejar_parada: texto libre del ticket -> parada")
geo, nombres = app.cargar_geo()
paradas = app.cargar_paradas()
pd_dist = app.paradas_con_distrito(paradas, geo)
refs = [(q["nombre"], app._sin_acentos(q["nombre"] + " " + q["direccion"])) for q in pd_dist]

check("'Rambla d'Egara 132' -> FGC Terrassa Rambla",
      app.emparejar_parada("Rambla d'Egara, 132", refs), "FGC Terrassa Rambla")
check("'HOSPITAL MUTUA DE TERRASSA' -> Hospital Mútua Terrassa",
      app.emparejar_parada("HOSPITAL MUTUA DE TERRASSA", refs), "Hospital Mútua Terrassa")
check("'Estacio del Nord' -> Estació del Nord",
      app.emparejar_parada("Estacio del Nord", refs), "Estació del Nord")
check("texto sin relación -> None",
      app.emparejar_parada("Calle Falsa 123, Springfield", refs), None)
check("texto vacío -> None", app.emparejar_parada("", refs), None)

# --------------------------------------------------------------------------
print("\n3) calcular_items: el ranking es determinista y compartido")
perfil = app.cargar_perfil()
orden_a = [i["nombre"] for i in app.calcular_items(perfil, pd_dist, nombres, 4, 11)]
orden_b = [i["nombre"] for i in app.calcular_items(perfil, pd_dist, nombres, 4, 11)]
check("dos llamadas iguales dan el mismo orden", orden_a, orden_b)
check("devuelve las 14 paradas", len(orden_a), 14)
niveles = {i["nivel"] for i in app.calcular_items(perfil, pd_dist, nombres, 4, 11)}
check("aparecen los tres niveles", niveles == {"Alta", "Media", "Baja"}, True)

con_evento = app.calcular_items(perfil, pd_dist, nombres, 4, 11, evento="Parc Vallès")
check("el evento pone esa parada la primera", con_evento[0]["nombre"], "Parc Vallès")

# --------------------------------------------------------------------------
print("\n4) tasa de acierto: casos construidos con respuesta conocida")


def tasa_acierto(recogidas, dia=4, hora=11):
    """Reproduce el cálculo de la vista Análisis sobre una lista de textos."""
    aciertos = emparejadas = 0
    for texto in recogidas:
        real = app.emparejar_parada(texto, refs)
        if real is None:
            continue
        emparejadas += 1
        top = [o["nombre"] for o in
               app.calcular_items(perfil, pd_dist, nombres, dia, hora)[:app.TOP_K]]
        if real in top:
            aciertos += 1
    return aciertos, emparejadas


top3 = orden_a[:3]
ultimas3 = orden_a[-3:]
direcciones = {q["nombre"]: q["direccion"] for q in pd_dist}

a, e = tasa_acierto([direcciones[n] for n in top3])
check("recogidas en las 3 primeras -> 100 %% de acierto", (a, e), (3, 3))

a, e = tasa_acierto([direcciones[n] for n in ultimas3])
check("recogidas en las 3 últimas -> 0 %% de acierto", (a, e), (0, 3))

a, e = tasa_acierto([direcciones[top3[0]], "Calle Falsa 123", direcciones[ultimas3[0]]])
check("las no emparejables se excluyen del cálculo", (a, e), (1, 2))

# --------------------------------------------------------------------------
print("\n" + "=" * 70)
if fallos:
    print("FALLAN %d comprobaciones: %s" % (len(fallos), fallos))
    sys.exit(1)
print("Todas las comprobaciones pasan.")
