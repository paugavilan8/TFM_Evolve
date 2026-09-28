# TaxiTerrassa

**Pau Gavilán** · TFM del Máster en Data Science e Inteligencia Artificial

Aplicación web que ayuda a una taxista autónoma de Terrassa a decidir a qué parada ir
cuando termina una carrera y no tiene ningún aviso. Ordena las catorce paradas de la
ciudad según la demanda esperada para el día y la hora, registra las carreras reales a
partir de una foto del ticket y muestra la rentabilidad del trabajo.

Forma parte del TFM *Sistema inteligente de predicción de demanda para taxistas
autónomos*.

## Qué hace

- **Conductor.** Ranking de paradas para ahora mismo o para cualquier día y hora, con mapa
  y niveles de demanda alta, media y baja. Trata los festivos como domingos, avisa cuando
  llueve y permite marcar una parada con un evento.
- **Registrar.** Lee la foto del ticket con Gemini y guarda la carrera en Google Sheets.
- **Análisis.** Euros por hora de turno, tiempo en vacío, trayectos más frecuentes y una
  evaluación de si la recomendación acierta: para cada carrera registrada se reconstruye
  el ranking que mostraba la app en ese momento y se comprueba si la parada real estaba
  entre las tres primeras.

La recomendación se calcula a partir del perfil de movilidad del MITMA por distrito, día
y hora.

### Modo demostración

Con `?demo=1` al final de la dirección
([apptaxistfm.streamlit.app/?demo=1](https://apptaxistfm.streamlit.app/?demo=1)) la app
usa dos semanas de carreras inventadas y no guarda nada en el registro. Sirve para
enseñarla sin mostrar los datos reales de la conductora. La app nunca enseña direcciones
de recogida o destino: son datos de sus clientes, y Análisis solo muestra en qué parada
empezó cada carrera o si fue en la calle.

## Ejecutar en local

Python 3.12.

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Registrar y el registro de carreras en la nube necesitan una clave de Gemini y una
cuenta de servicio de Google Sheets en `.streamlit/secrets.toml`, que no se incluye en el
repositorio. Sin ellas, la vista Conductor funciona igual.

El mapa usa los fondos de CARTO, que desde 2026 piden una clave gratuita
([carto.com/basemaps/apikey](https://carto.com/basemaps/apikey)). Se añade a los mismos
secretos:

```toml
CARTO_API_KEY = "tu-clave"
```

Sin clave, el mapa usa OpenStreetMap en gris.

## Pruebas

```bash
python tests/test_analisis.py
```

50 comprobaciones con casos de respuesta conocida sobre la duración de las carreras, el
tiempo en vacío, el emparejamiento de direcciones con paradas, la tasa de acierto del
recomendador, la revisión de los tickets antes de guardarlos, el fondo del mapa, los
festivos y el modo demostración.

## Datos

| Fichero en `data/external/` | Contenido | Fuente |
|---|---|---|
| `perfil_movilidad_terrassa.csv` | Viajes por distrito, día de la semana y hora (7 × 7 × 24) | Estudio de movilidad del MITMA con datos de telefonía móvil, cuatro semanas de 2023 |
| `terrassa_distritos.geojson` | Límites de los siete distritos | Zonificación del MITMA |
| `paradas_terrassa.csv` | Catorce paradas de taxi con dirección, plazas y coordenadas | OpenStreetMap y Ajuntament de Terrassa, geocodificadas con Nominatim |

El registro de carreras reales contiene direcciones, que son datos personales, y no se
publica.

## Entregas

Las cuatro entregas del proyecto están en [`docs/entregas/`](docs/entregas):

1. [Ideas de producto](docs/entregas/01_ideas_producto.md)
2. [Datos necesarios](docs/entregas/02_datos_necesarios.md)
3. [Modelo de datos](docs/entregas/03_modelo_datos.md)
4. [Análisis y modelado](docs/entregas/04_analisis_modelado.md)

## Modelo de demanda: repositorio privado

El modelo de demanda, entrenado y evaluado con 38,3 millones de viajes de taxi de Nueva
York, está en el repositorio privado
[TFM_Evolve_privado](https://github.com/paugavilan8/TFM_Evolve_privado), al que tiene
acceso el profesor. Se guarda aparte porque incluye la memoria y el material de la
defensa. Todo el código es de scripts `.py` ejecutables de principio a fin; los
notebooks quedan en su propia carpeta, solo para exploración.

```
pipeline/     fase1_descarga_demanda.py     descarga los viajes de 2023 y los agrega con DuckDB
              fase2_features_baseline.py    variables (retardos, calendario) y baseline
              fase2_modelos.py              LightGBM frente a baseline y Prophet
              fase2_lstm.py                 red LSTM
              fase2_entrenar_final.py       modelo final, guardado en formato nativo de LightGBM
              fase3_analisis_errores.py     errores por segmento y contraste NYC-Terrassa
              fase3_validacion_robusta.py   validación de origen móvil y bootstrap
notebooks/    exploración de la demanda y comparación de patrones
scripts/      paradas, geocodificación y extracción del MITMA en R
models/       modelo entrenado y sus metadatos
results/      tablas de resultados
```

Resultado principal: LightGBM reduce el error del baseline un 42 % (WAPE del 16,5 % frente
al 28,5 %), con un intervalo de confianza del 95 % entre el 36,5 % y el 47,4 %, y gana en
los cuatro meses de la validación de origen móvil.

## Estructura

```
app.py                 aplicación Streamlit (punto de entrada del despliegue)
requirements.txt       dependencias de la app
.streamlit/config.toml tema y configuración de Streamlit
data/external/         datos de la app
tests/                 pruebas de la lógica de análisis
docs/entregas/         entregas del proyecto
```
