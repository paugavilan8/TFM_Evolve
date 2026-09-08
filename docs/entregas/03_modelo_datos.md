# Entrega 3 — Diseño del modelo de datos y capa gold del proyecto

**Proyecto:** Sistema inteligente de predicción de demanda para taxistas autónomos — transferencia de modelos de Nueva York a Terrassa
**Autor:** Pau Gavilán

> Nota: la estructura descrita refleja el estado real del repositorio. La capa de modelado ya existe (`data/processed/demanda_features_2023.parquet`); esta entrega la formaliza como capa *gold* y define el contrato de datos para las fases posteriores.

---

## 1. Resumen de la idea y datos del proyecto

- **Problema.** El taxista autónomo decide dónde y cuándo posicionarse por intuición, sin herramientas de predicción de demanda, lo que genera kilómetros en vacío y falta de visibilidad sobre su rentabilidad.
- **Solución.** Un modelo de predicción de demanda espacio-temporal (zona × franja horaria) entrenado con datos abundantes de Nueva York y **transferido a Terrassa** (se transfiere la *forma* del patrón temporal, se recalibra la *escala* con fuentes locales), materializado en una app Streamlit que recomienda paradas y muestra la rentabilidad real.
- **Fuentes y qué aporta cada una:**

| Fuente | Qué aporta |
|---|---|
| **NYC TLC (Yellow Taxi 2023)** | Base de entrenamiento: millones de viajes → demanda agregada por zona/hora |
| **NYC TLC — Taxi Zone Lookup** | Tabla dimensión: LocationID → zona, borough |
| **MITMA — movilidad Big Data** | Perfil de movilidad local de Terrassa por distrito/hora/día (proxy de demanda) |
| **Open-Meteo** | Variables meteorológicas horarias (contexto) — *previsto, aún no integrado en la tabla de features* |
| **Calendario de festivos** | Indicador de festivo (festivos de EE. UU. para la tabla NYC) |
| **Registro real del taxista (Tele-Taxi Egara)** | Carreras reales: validación y cálculo de rentabilidad |

---

## 2. Tecnología o formato de almacenamiento elegido

Se opta por una **combinación de formatos ligeros basados en ficheros**, sin base de datos relacional, que es exactamente lo que ya usa el repositorio. La justificación es la coherencia con el proyecto: la carga de trabajo es **analítica y de solo lectura** (se construyen tablas, se entrena un modelo, se pintan mapas), no transaccional; no hay concurrencia ni necesidad de integridad referencial en tiempo de ejecución, por lo que una BD relacional (SQLite/PostgreSQL) añadiría complejidad sin aportar valor.

| Formato | Dónde se usa (ficheros reales del repo) | Por qué |
|---|---|---|
| **Parquet** | `yellow_tripdata_2023-*.parquet`, `demanda_nyc_2023.parquet`, `demanda_features_2023.parquet` (~millones de filas) | Columnar, comprimido y eficiente para grandes volúmenes; es el formato nativo de descarga de NYC TLC |
| **CSV** | `taxi_zone_lookup.csv` y las tablas pequeñas de la capa gold (perfil, paradas, carreras) | Legible, versionable en Git y trivial de inspeccionar; volúmenes de decenas a miles de filas |
| **Google Sheets** | Captura en vivo del registro de carreras (vía `escaner_tickets.py`) | Ya integrado en el producto (foto de ticket → modelo de visión → hoja en la nube); se exporta a CSV para el pipeline |

Los cruces y agregaciones se resuelven en memoria con **pandas** durante la construcción de las capas; no se necesita un motor SQL.

---

## 3. Estructura de capas de datos

El repositorio ya sigue la estructura por capas. Solo se añade la carpeta `gold/` para formalizar el contrato de datos:

```
data/
|-- raw/                                    [EXISTE]
|   |-- taxi_zone_lookup.csv                tabla dimensión de zonas NYC
|   `-- yellow_tripdata_2023-01..12.parquet viajes originales (12 ficheros mensuales)
|-- processed/                              [EXISTE]
|   |-- demanda_nyc_2023.parquet            rejilla zona x fecha x hora (relleno de ceros)
|   `-- demanda_features_2023.parquet       rejilla + lags + calendario + objetivo
`-- gold/                                   [EXISTE]
    |-- gold_demanda_modelo.parquet         copia de demanda_features_2023.parquet
    |-- gold_perfil_terrassa.csv            perfil MITMA (planificado)
    |-- gold_carreras_rentabilidad.csv      export de Google Sheets (planificado)
    `-- gold_paradas_terrassa.csv           14 paradas de Terrassa (planificado)
```

**Scripts del pipeline (reales):** `fase1_descarga_demanda.py` (raw → `demanda_nyc_2023`), `fase1b_eda.ipynb` (EDA), `fase2_features_baseline.py` (→ `demanda_features_2023` + baseline), `fase2_modelos.py` (LightGBM), `fase2_lstm.py` (LSTM, futuro), `escaner_tickets.py` (OCR de tickets), `app.py` (Streamlit).

| Capa | Contenido en este proyecto |
|---|---|
| **Raw** | Datos originales sin modificar: parquets mensuales de NYC TLC y `taxi_zone_lookup.csv`. |
| **Processed** | Datos limpios e intermedios: `demanda_nyc_2023.parquet` (rejilla con relleno de ceros) y `demanda_features_2023.parquet` (rejilla enriquecida con features). |
| **Gold** | Datasets finales listos para consumir: la tabla de modelado (ya existente) más las tablas de perfil, carreras y paradas. |

---

## 4. Definición de la capa gold

Vista general (contrato de datos):

| Dataset gold | Estado | Granularidad | Campos clave | Nº aprox. registros | Uso posterior |
|---|---|---|---|---|---|
| `gold_demanda_modelo.parquet` | Existe en `data/gold/` (copia de `demanda_features_2023.parquet`) | Una fila por **zona × fecha × hora** | `zona, fecha, hora, lags…, demanda` | ~2.303.880 | Modelo predictivo (LightGBM) |
| `gold_perfil_terrassa.csv` | Planificado | Una fila por **distrito × día_semana × hora** | `distrito_id, dia_semana, hora, viajes_norm, nivel_demanda` | ~1.176 | App / dashboard + validación de transferencia |
| `gold_carreras_rentabilidad.csv` | En Google Sheets | Una fila por **carrera** | `id_carrera, fecha, importe_eur, eur_por_km` | Decenas–cientos (creciente) | Dashboard de rentabilidad |
| `gold_paradas_terrassa.csv` | Planificado | Una fila por **parada de taxi** | `id_parada, nombre, lat, lon, distrito_id` | 14 | Mapa de la app (modo Conductor) |

**Detalle por dataset:**

### `gold_demanda_modelo.parquet`  *(copia de `data/processed/demanda_features_2023.parquet`)*
- **Descripción funcional:** tabla de entrenamiento del modelo de predicción de demanda. Cada fila es la demanda observada en una zona y hora, con sus variables predictoras. La genera `fase2_features_baseline.py` a partir de `demanda_nyc_2023.parquet`.
- **Granularidad:** zona × fecha × hora (resolución horaria). Rejilla regular y completa (relleno de ceros), ~263 zonas × 8.760 horas ≈ **2.303.880 filas**.
- **Clave primaria:** (`zona`, `fecha`, `hora`) — equivalente a (`zona`, `datetime`).
- **Campos y tipos (esquema real):**

| Campo | Tipo | Rol | Descripción |
|---|---|---|---|
| `zona` | int | feature | Zona de recogida (= `LocationID` de NYC TLC) |
| `fecha` | date | — | Día del registro |
| `hora` | int (0–23) | feature | Franja horaria |
| `hora_sin` | float | feature | Codificación cíclica de la hora (seno) |
| `hora_cos` | float | feature | Codificación cíclica de la hora (coseno) |
| `dia_semana` | int (0–6) | feature | Día de la semana |
| `es_finde` | int (0/1) | feature | Indicador de fin de semana |
| `mes` | int (1–12) | feature | Mes |
| `dia_mes` | int (1–31) | feature | Día del mes |
| `es_festivo` | int (0/1) | feature | Festivo (calendario EE. UU. 2023) |
| `lag_1h` | float | feature | Demanda de la zona 1 h antes |
| `lag_24h` | float | feature | Demanda 24 h antes |
| `lag_168h` | float | feature | Demanda 168 h antes (misma hora, semana anterior) |
| `roll_24h` | float | feature | Media móvil 24 h (`shift(1)` + `rolling(24)`) |
| `roll_168h` | float | feature | Media móvil 168 h |
| `datetime` | datetime | auxiliar | Marca temporal (`fecha` + `hora`), usada para ordenar y particionar |
| `set` | str | auxiliar | Partición temporal: `train` (ene–oct) / `test` (nov–dic) |
| **`demanda`** | int | **objetivo** | **Variable objetivo:** nº de carreras (conteo) |

- **Variable objetivo:** `demanda` (conteo → objetivo Poisson en LightGBM). El baseline "misma hora, semana anterior" usa `lag_168h`.
- **Consumida por:** entrenamiento y evaluación del modelo (`fase2_modelos.py`, `fase2_lstm.py`), con partición **temporal** (`set`), nunca aleatoria.
- **Nota:** las primeras 168 h de cada zona tienen `lag_*`/`roll_*` a `NaN`; el script de modelado aplica `dropna()` sobre esas columnas antes de entrenar. Meteo (Open-Meteo) es una feature **deseable aún no integrada** en esta tabla.

### `gold_perfil_terrassa.csv`  *(planificado)*
- **Descripción funcional:** perfil normalizado de movilidad de Terrassa; aporta la dimensión espacial/temporal local y traduce la predicción a niveles de demanda por zona.
- **Granularidad:** distrito × día_semana × hora.
- **Clave primaria:** (`distrito_id`, `dia_semana`, `hora`).
- **Campos:** `distrito_id` (int), `dia_semana` (int), `hora` (int), `viajes_norm` (float, 0–1), `nivel_demanda` (categórico: alta/media/baja).
- **Consumida por:** app (mapa y recomendación de paradas) y validación de la transferencia (correlación con el patrón de NYC).

### `gold_carreras_rentabilidad.csv`  *(hoy en Google Sheets, vía `escaner_tickets.py`)*
- **Descripción funcional:** carreras reales del taxista con métricas de rentabilidad derivadas.
- **Granularidad:** una fila por carrera.
- **Clave primaria:** `id_carrera`.
- **Campos:** `id_carrera` (str), `fecha` (date), `hora_inicio` (time), `hora_fin` (time), `origen` (str), `destino` (str), `distancia_km` (float), `importe_eur` (float), `tipo_servicio` (str), `duracion_min` (float, derivado), `eur_por_km` (float, derivado), `eur_por_hora` (float, derivado).
- **Métricas relevantes:** `eur_por_km`, `eur_por_hora`.
- **Consumida por:** dashboard de rentabilidad (modo Análisis) y, a futuro, calibración local.

### `gold_paradas_terrassa.csv`  *(planificado)*
- **Descripción funcional:** las 14 paradas de taxi reales de Terrassa, geolocalizadas y asignadas a distrito.
- **Granularidad:** una fila por parada.
- **Clave primaria:** `id_parada`.
- **Campos:** `id_parada` (int), `nombre` (str), `lat` (float), `lon` (float), `distrito_id` (int).
- **Consumida por:** mapa interactivo de la app (modo Conductor).

---

## 5. Relaciones entre datos

- **`gold_demanda_modelo.zona` → `taxi_zone_lookup.LocationID`** — relación **N:1**. La tabla de zonas es una dimensión que da nombre/borough a cada zona de recogida (join por `LocationID`).
- **`gold_paradas_terrassa.distrito_id` → `gold_perfil_terrassa.distrito_id`** — **N:1** (cada parada pertenece a un distrito; cada distrito tiene un perfil por día/hora). Permite asignar a cada parada el nivel de demanda previsto.
- **`gold_carreras_rentabilidad`** se relaciona con los distritos **N:1** tras **geocodificar** `origen`/`destino` a `distrito_id` (join no directo: requiere geocodificación previa).
- **NYC (`zona`) ↔ Terrassa (`distrito_id`): NO existe join por clave.** La conexión entre ambos mundos es **conceptual, a nivel de patrón temporal normalizado** (la *forma* horaria/semanal), no una unión por identificador. Es el punto metodológico central del proyecto y conviene dejarlo explícito.
- **Joins/agregaciones necesarios:** agregación de viajes NYC → rejilla zona/hora (`demanda_nyc_2023`); enriquecimiento con lags, meteo (por fecha+hora) y festivos (por fecha) → `demanda_features_2023`; agregación de matrices MITMA → perfil por distrito/día/hora.
- **Problemas al combinar fuentes:** geografías distintas (zonas NY vs distritos Terrassa), husos horarios distintos (NY vs Europe/Madrid), escalas de volumen muy diferentes y que el MITMA mide movilidad general (proxy), no demanda de taxi.

---

## 6. Diccionario de datos inicial

| Campo | Descripción | Tipo | Fuente | Obligatorio | Observaciones |
|---|---|---|---|---|---|
| `zona` | Zona de recogida | int | NYC TLC / `taxi_zone_lookup` | Sí | = `LocationID`; excluir 264/265 (desconocidas) |
| `fecha` | Día del registro | date | Derivado de `tpep_pickup_datetime` | Sí | Formato `YYYY-MM-DD` |
| `hora` | Franja horaria | int (0–23) | Derivado | Sí | Codificada además como `hora_sin`/`hora_cos` |
| `demanda` | Nº de carreras | int | NYC TLC (agregado) | Sí | Variable objetivo; 0 explícito (relleno de ceros) |
| `lag_168h` | Demanda 1 semana antes | float | Derivado | Sí | Requiere rejilla continua y ordenada; NaN en las 1as 168 h |
| `roll_24h` | Media móvil 24 h | float | Derivado | Sí | `shift(1)` + `rolling(24)` dentro de cada zona |
| `es_festivo` | Indicador de festivo | int (0/1) | Calendario (`holidays`) | No | Festivos EE. UU. para NYC; España/Cataluña para Terrassa |
| `temp` | Temperatura | float | Open-Meteo | No | Deseable; aún no integrada en la tabla de features |
| `distrito_id` | Distrito censal de Terrassa | int (1–7) | MITMA | Sí | 7 distritos |
| `viajes_norm` | Movilidad normalizada | float | MITMA | Sí | Proxy; normalizado 0–1 |
| `importe_eur` | Importe de la carrera | float | Registro taxista | Sí | Limpieza de moneda; posible error de OCR |
| `distancia_km` | Distancia de la carrera | float | Registro taxista | Sí | Validar > 0 |
| `origen` / `destino` | Direcciones de la carrera | str | Registro taxista | No | Requiere geocodificación a distrito |

---

## 7. Problemas de calidad esperados (aterrizados al caso)

- **NYC TLC:** horas sin viajes que se interpretarían como *ausentes* en lugar de **demanda cero** (se resuelve con relleno de ceros en `demanda_nyc_2023`); **outliers** (distancia = 0, importes negativos, duraciones absurdas); zonas desconocidas (LocationID 264/265 en `taxi_zone_lookup`); registros en el límite entre días/meses.
- **MITMA:** es un **proxy** (movilidad general ≠ demanda de taxi); umbrales de anonimización que ocultan celdas de bajo recuento; posible desajuste entre la definición de distrito y las zonas del modelo.
- **Open-Meteo:** huecos puntuales de la API y **desfase de zona horaria** (UTC vs local) que hay que alinear.
- **Registro del taxista:** **errores de OCR** al leer el ticket por foto (importes/fechas mal reconocidos); formatos de dirección inconsistentes; campos vacíos; **volumen aún reducido**; **duplicados** si se fotografía dos veces el mismo ticket.
- **Al cruzar fuentes:** geografías distintas (no hay clave común NY↔Terrassa), husos horarios distintos y **calendario de festivos incoherente** (EE. UU. para NYC vs España para Terrassa).
- **Sesgo de cobertura:** el perfil local proviene de una muestra (una semana por trimestre) y de una sola conductora para los datos reales.

---

## 8. Decisiones de limpieza y transformación previstas

- **Valores nulos:** en la rejilla de demanda, las combinaciones sin viajes → **0** explícito (no nulo). En meteo, imputación por interpolación temporal de huecos cortos. Carreras con campos críticos nulos (fecha, importe) → se descartan.
- **Duplicados:** en carreras, deduplicación por `id_carrera` / hash del ticket. En NYC, la agregación a rejilla elimina el problema a nivel de viaje.
- **Fechas y horas:** normalización a `YYYY-MM-DD`, truncado a hora, y **conversión a zona horaria local** de cada contexto antes de construir features.
- **Textos/categorías:** normalización de `tipo_servicio` y de direcciones; **geocodificación** de `origen`/`destino` a `distrito_id`.
- **Unidades:** importes a EUR con limpieza de moneda; distancias a km.
- **Variables derivadas:** lags (1 h, 24 h, 168 h), medias móviles, `es_finde`, `es_festivo`, y métricas de rentabilidad (`eur_por_km`, `eur_por_hora`, `duracion_min`).
- **Agregaciones:** viajes NYC → conteo por zona/hora; matrices MITMA → perfil normalizado por distrito/día/hora.
- **Descartes:** viajes NYC con distancia ≤ 0, importe ≤ 0 o duración fuera de rango; zonas desconocidas.
- **Criterio de registro válido:** fecha y hora parseables, zona/distrito conocido, y (en carreras) importe y distancia positivos.

---

## 9. Riesgos del modelo de datos

- **Parte más clara:** la tabla de modelado (`demanda_features_2023.parquet` → `gold_demanda_modelo`) — ya está construida, es abundante y bien estructurada.
- **Parte con más incertidumbre:** `gold_perfil_terrassa` (por el carácter de proxy del MITMA) y la **geocodificación** de las carreras a distrito.
- **Fuente que puede dar más problemas:** el **registro real del taxista** (OCR, volumen reducido, formatos), seguida del MITMA como proxy.
- **Si no se puede construir la capa gold como está definida:** se degrada la granularidad (predicción a nivel de distrito en lugar de zona fina), se prescinde de variables opcionales (meteo) o se pospone la geocodificación, trabajando el perfil solo a nivel de distrito agregado.
- **Alternativa para simplificar:** reducir el modelo a **un único dataset gold de modelado** (la tabla que ya existe) más una tabla de rentabilidad, eliminando el crosswalk parada↔distrito y usando conjuntos abiertos equivalentes de otra ciudad (p. ej. Chicago) si NYC TLC fallara.
