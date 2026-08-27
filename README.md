# TFM — Sistema de predicción de demanda para taxistas autónomos

**Pau Gavilán**

Modelo de predicción de demanda de taxi **entrenado y validado sobre datos reales de
Nueva York**, y **prototipo de producto** (app + sistema de captura de datos) para el
caso de uso local: una taxista autónoma en Terrassa.

## Alcance (léase antes que nada)

Este trabajo tiene dos mitades, y es importante no confundirlas:

| | Estado |
|---|---|
| **Modelo de demanda (NYC)** | Completo y evaluado. 38,3 M de viajes, comparativa contra baseline con métricas sobre un test temporal. |
| **Producto (Terrassa)** | Prototipo funcional, desplegable y en uso para **capturar** datos reales. |
| **Transferencia NYC → Terrassa** | **Trabajo futuro.** Se demuestra que las formas temporales correlacionan, pero el modelo de NYC *no* alimenta todavía la recomendación de la app. |

La recomendación que hoy muestra la app se calcula a partir del perfil de movilidad
local (MITMA), no del modelo entrenado. Cerrar ese circuito requiere un volumen de
carreras reales del que aún no se dispone; el sistema de captura de tickets existe
precisamente para generarlo.

## Estructura

```
app.py                       App Streamlit — entrypoint del despliegue
requirements.txt             Dependencias de la app (las que instala Streamlit Cloud)
requirements-pipeline.txt    Dependencias del pipeline de datos y modelado

pipeline/                    Fases 1-2: de datos crudos a modelos evaluados
  fase1_descarga_demanda.py    Descarga TLC + agrega a (zona × fecha × hora) con DuckDB
  fase2_features_baseline.py   Feature engineering (lags, calendario) + baseline ingenuo
  fase2_modelos.py             Baseline vs LightGBM vs Prophet
  fase2_lstm.py                Baseline vs LightGBM vs LSTM (requiere Python 3.12)
  fase2_entrenar_final.py      Entrena el modelo de producción y lo serializa
  figuras_memoria.py           Genera todas las figuras de la memoria
  modelo.py                    Carga del modelo guardado e inferencia

notebooks/                   Análisis narrado
  fase1b_eda.ipynb             Exploratorio de la demanda NYC
  fase3_comparacion.ipynb      Formas temporales NYC vs Terrassa

scripts/                     Utilidades de un solo uso
  obtener_paradas.py           Paradas de taxi desde OpenStreetMap
  geocodificar_paradas.py      Geocodificación de paradas con Nominatim
  escanear_tickets.py          Escáner suelto (duplica la vista Registrar de app.py)

models/                      Modelo entrenado (formato nativo LightGBM) + metadatos
results/                     Tablas de resultados para la memoria
docs/                        Memoria del TFM, figuras y script que la construye
```

### Datos

```
data/external/   Entradas de terceros — versionadas en el repositorio
                   perfil_movilidad_terrassa.csv · terrassa_distritos.geojson · paradas_terrassa.csv
data/raw/        Parquet mensuales originales de la TLC (~620 MB)      — ignorado
data/processed/  demanda_nyc_2023.parquet, tabla de demanda agregada    — ignorado
data/gold/       demanda_features_2023.parquet, lista para modelar      — ignorado
data/registro/   Registro_carreras_TFM.xlsx, carreras reales            — ignorado (datos personales)
```

`raw/`, `processed/` y `gold/` se regeneran con las Fases 1 y 2. Todas las rutas del
proyecto están ancladas al fichero que las usa, así que cualquier script o notebook
funciona desde cualquier directorio.

## Entorno: por qué Python 3.12

El proyecto se desarrolló sobre Python 3.14, pero **TensorFlow no publica
distribuciones para esa versión**, de modo que el experimento con LSTM no podía
ejecutarse. Todas las demás dependencias resuelven a versiones idénticas en 3.12 y en
3.14, así que se fija **3.12** como versión del proyecto: un único entorno reproduce el
pipeline completo, incluida la red recurrente.

```bash
uv python install 3.12
uv venv .venv --python 3.12
uv pip install -r requirements.txt -r requirements-pipeline.txt
```

Sin `uv` sirve igual `py -3.12 -m venv .venv` y luego `pip install -r ...`, siempre que
Python 3.12 esté instalado en el sistema.

## Reproducir

```bash
python pipeline/fase1_descarga_demanda.py      # descarga ~620 MB y agrega (tarda)
python pipeline/fase2_features_baseline.py     # features + baseline
python pipeline/fase2_modelos.py               # LightGBM y Prophet
python pipeline/fase2_lstm.py                  # LSTM
python pipeline/fase2_entrenar_final.py        # modelo de producción -> models/
python pipeline/figuras_memoria.py --lgbm      # figuras de la memoria
```

## El modelo entrenado

`pipeline/fase2_entrenar_final.py` guarda el modelo en `models/` en el formato nativo de
LightGBM (`.txt`) en lugar de pickle: el fichero nativo no depende de la versión de
Python ni de scikit-learn con que se creó, es texto plano inspeccionable y lo leen
también los enlaces de LightGBM para R y C++. Junto a él se guarda un `.json` con las
variables en orden, el mapeo de categorías de zona, los hiperparámetros, las métricas
sobre el conjunto de prueba y las versiones de las librerías.

Para predecir desde cualquier proceso:

```python
from pipeline.modelo import cargar, predecir
booster, meta = cargar()
y = predecir(booster, meta, df)      # df con las 14 variables del modelo
```

El script verifica la serialización comparando las predicciones del modelo en memoria
con las del recargado: la diferencia debe ser exactamente cero.

Para la app:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Datos

| Fuente | Uso |
|---|---|
| **NYC TLC Yellow Taxi 2023** | 38,3 M de viajes → 2.303.880 filas (zona × fecha × hora), 263 zonas. Verdad de campo para entrenar y evaluar. |
| **MITMA** (movilidad, vía R) | `data/external/perfil_movilidad_terrassa.csv`: 7 distritos × 24 h × 7 días. Proxy de actividad local. |
| **OpenStreetMap** | 14 paradas de taxi de Terrassa, geocodificadas. |
| **Registro propio** | `data/registro/Registro_carreras_TFM.xlsx` / Google Sheets: carreras reales capturadas por foto del ticket. |

> El script de R que genera `data/external/perfil_movilidad_terrassa.csv` no está todavía en el
> repositorio. **Pendiente de añadir** para que esa mitad de los datos sea reproducible.

## Resultados

Test temporal: entrena ene–oct 2023, evalúa nov–dic 2023. Métricas MAE / RMSE / WAPE
(WAPE en lugar de MAPE porque el 61,5 % de las celdas de la rejilla valen cero).

| Modelo | MAE | RMSE | WAPE |
|---|---|---|---|
| Baseline (misma hora, semana anterior) | 4,98 | 18,85 | 28,5 % |
| **LightGBM** (objetivo Poisson) | **2,87** | **9,57** | **16,5 %** |

**LightGBM reduce el error del baseline un 42 %.** En la submuestra de 30 zonas usada
para poder comparar con Prophet: baseline 25,2 %, LightGBM 13,7 %, Prophet 34,5 %.

## Limitaciones conocidas

Se documentan aquí porque condicionan la lectura de los resultados:

1. **Horizonte de predicción.** El modelo usa `lag_1h` como variable, es decir, evalúa
   predicción a **1 hora vista con el valor real ya observado**. La app necesitaría
   predecir con más antelación, donde ese dato no existe. Falta un experimento a h=24
   sin `lag_1h`.
2. **La comparación con Prophet no es equitativa.** LightGBM recibe los lags y Prophet
   no recibe ningún regresor. Su peor resultado dice "Prophet sin regresores es peor",
   no "Prophet es peor".
3. **El LSTM**: tal y como está implementado, la red no recibe ningún identificador de
   zona ni normalización de variables, por lo que su resultado no debe leerse como el
   techo de lo que una red recurrente puede dar en este problema.
4. **Validación única.** Un solo corte temporal, sin validación cruzada de origen móvil
   ni intervalos de confianza.
5. **Resolución espacial del prototipo.** La demanda local es por distrito (7) y las
   paradas son 14, así que varias comparten valor. En las 168 combinaciones día × hora
   solo se recomiendan **3 paradas distintas**; las otras 11 nunca salen.
6. **El perfil MITMA es en buena parte un proxy de población**: `corr(viajes totales,
   población) = 0,885`. Descomposición de varianza: distrito 36,3 %, hora × día 53,3 %.
   Normalizar por habitante cambiaría la recomendación en 107 de las 168 horas.
7. **Sin validación local.** El registro de carreras reales está prácticamente vacío,
   de modo que no hay evidencia empírica del comportamiento del sistema en Terrassa.

## Privacidad

Los tickets fotografiados se envían a la API de Gemini (Google) para extraer los campos
y se almacenan en Google Sheets o en el Excel local. Contienen direcciones de origen y
destino, que son **datos personales indirectos**. El registro no recoge nombre ni datos
identificativos del cliente. Pendiente de redactar la sección de base legal,
minimización y consentimiento de la conductora.

Las credenciales viven en `.streamlit/secrets.toml`, excluido del control de versiones
(verificado: nunca ha entrado al historial de git).
