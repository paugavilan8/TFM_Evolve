# Entrega 4 — Diseño del análisis y estrategia de modelado

**Proyecto:** Sistema inteligente de predicción de demanda para taxistas autónomos
**Autor:** Pau Gavilán

---

## Nota preliminar sobre el estado del proyecto

Este documento recoge el diseño del análisis y la estrategia de modelado tal y como se planteó al inicio de la fase de modelado. Conviene advertir, sin embargo, que el proyecto se encuentra hoy por delante del calendario de entregas: los modelos descritos aquí han sido ya entrenados y comparados, y existe un prototipo del producto desplegado y en uso.

Por trazabilidad y honestidad metodológica, cada apartado presenta primero **la decisión de diseño y su justificación** —que es lo que esta entrega pide— y añade, cuando procede, un bloque **`Resultado obtenido`** con la evidencia ya disponible. Esto permite juzgar no solo si el diseño era razonable, sino si las decisiones se sostuvieron al contrastarlas con los datos.

Ninguna decisión previa de las entregas 1 a 3 se ha eliminado. Las modificaciones respecto al diseño original se señalan en el apartado 9.

---

## 1. Problema que se busca resolver

### 1.1 Qué ocurre actualmente y por qué supone un problema

El taxista autónomo decide dónde y cuándo posicionarse basándose exclusivamente en su intuición y en la experiencia acumulada. No dispone de ninguna herramienta analítica que le indique dónde es más probable que aparezca un servicio en la próxima hora.

Esta situación tiene dos consecuencias medibles:

1. **Kilómetros en vacío.** Tiempo y combustible invertidos circulando sin pasaje, buscando dónde colocarse. Es coste puro.
2. **Asimetría competitiva.** Las plataformas de vehículo con conductor (VTC) operan con sistemas sofisticados de predicción de demanda y asignación automática. El taxista tradicional compite contra ellas sin ninguna capacidad analítica equivalente.

A esto se añade un tercer problema, de naturaleza distinta: el conductor autónomo **no conoce con precisión su propia rentabilidad**. Sabe lo que factura, pero no cuánto gana por hora de turno, ni en qué franjas o zonas pierde más tiempo en vacío.

### 1.2 Quién utilizará el resultado y para qué decisión

El usuario es una **taxista autónoma en activo en Terrassa** (cooperativa Tele-Taxi Egara), sin conocimientos técnicos, que utilizará el sistema desde el navegador de su teléfono móvil durante el turno.

La decisión que apoya el sistema es concreta e inmediata: *«acabo de dejar a un cliente, ¿a qué parada me dirijo ahora?»*. El horizonte de la decisión es de aproximadamente una hora, lo que condiciona directamente el horizonte de predicción del modelo (apartado 4.4).

Secundariamente, el sistema le permite responder a una pregunta de balance: *«¿qué franjas y qué zonas me están saliendo rentables?»*.

### 1.3 Qué resultado concreto debería producir el proyecto

| Resultado | Forma concreta | Condición de utilidad |
|---|---|---|
| Predicción de demanda | Estimación de recogidas por (zona, hora) | Reducir el error del baseline ingenuo en al menos un 20 % relativo (WAPE) |
| Recomendación accionable | Ranking de las 14 paradas de Terrassa a la hora actual | Tasa de acierto en el top-3 significativamente superior al 21 % que daría el azar |
| Retorno al usuario | Métricas de rentabilidad reales (€/h de turno, €/km, tiempo en vacío) | Que la conductora pueda leerlas sin ayuda y le digan algo que no supiera |

---

## 2. Análisis de datos planteado y utilidad esperada

El análisis no es un catálogo de gráficos: cada bloque está formulado como una pregunta cuya respuesta condiciona una decisión posterior de modelado o de producto.

### 2.1 Preguntas que se quieren responder

| # | Pregunta | Qué decide |
|---|---|---|
| P1 | ¿Cómo se distribuye la demanda? ¿Es una variable de conteo con exceso de ceros? | La métrica de error y la función objetivo del modelo |
| P2 | ¿Cuál es la señal temporal dominante: la hora, el día de la semana, el mes? | Qué variables construir y cómo codificarlas |
| P3 | ¿El fin de semana cambia el *nivel* de la demanda o su *forma*? | Si basta un indicador binario o hacen falta interacciones |
| P4 | ¿Todas las zonas se comportan igual, o cada una tiene su propio perfil horario? | Si el modelo puede ser único o debe distinguir por zona |
| P5 | ¿Hay tendencia anual que obligue a usar varios años de histórico? | El tamaño del conjunto de entrenamiento y el diseño de la partición |
| P6 | ¿La forma temporal de la demanda de Nueva York se parece a la movilidad de Terrassa? | Si la estrategia de transferencia es viable |
| P7 | ¿Cuánta variación explica la dimensión espacial frente a la temporal en el perfil local? | Cuánta resolución espacial puede prometer el producto |

### 2.2 Análisis previos al modelado (exploratorio)

- **Distribución y dispersión** de la demanda sobre la rejilla zona × hora. Histograma recortado al percentil 99 y proporción de celdas a cero.
- **Perfil horario** medio: demanda media por hora del día.
- **Perfil semanal**: demanda media por día de la semana, y curva horaria separando laborables de fines de semana (superposición, no solo comparación de medias).
- **Interacción hora × día de la semana**: mapa de calor.
- **Análisis espacial**: ranking de zonas por demanda acumulada anual, y matriz zona × hora para las principales.
- **Estabilidad anual**: serie diaria agregada durante todo el año.

### 2.3 Análisis específicos de la hipótesis de transferencia

- **Perfil local de movilidad** de Terrassa (distrito × hora × día de la semana) a partir de las matrices origen-destino del MITMA.
- **Comparación de formas normalizadas** entre ambos contextos, cuantificada con correlación de Pearson sobre el perfil horario y sobre el semanal.
- **Contraste contra un modelo nulo** (añadido respecto al diseño inicial; véase 8.5): test de permutación y correlaciones internas entre distritos de la propia Terrassa, para establecer el suelo sobre el que la correlación observada debe destacar.
- **Descomposición de la varianza** del perfil local: cuánta variación explica el distrito frente a la combinación hora × día.
- **Control de confusión espacial**: correlación entre los viajes totales de cada distrito y su población, para comprobar si el ranking espacial es señal de demanda o simple reflejo del tamaño poblacional.

### 2.4 Análisis posteriores al modelado

- **Importancia de variables** del modelo ganador, interpretada con cautela por el sesgo conocido de la métrica por número de divisiones hacia variables categóricas de alta cardinalidad.
- **Análisis de errores por segmento**: WAPE desagregado por franja horaria, por tipo de día y por nivel de demanda de la zona, para identificar dónde falla el modelo y no solo cuánto falla en promedio.
- **Evaluación del recomendador** contra el registro real de carreras: tasa de acierto en las k primeras posiciones.

### 2.5 Hipótesis a comprobar

- **H1.** La hora del día es la variable con mayor capacidad explicativa de la demanda.
- **H2.** El fin de semana no traslada la curva horaria: le cambia la forma, desplazando actividad de la punta de la mañana hacia la madrugada.
- **H3.** El comportamiento es heterogéneo entre zonas: cada zona tiene su propia hora punta.
- **H4.** La *forma* del patrón temporal es razonablemente común entre ciudades, mientras que la escala y la geografía son específicas de cada lugar.

### 2.6 Qué se incorpora al MVP

| Elemento del análisis | Dónde aparece en el producto |
|---|---|
| Ranking de paradas por demanda estimada | Modo Conductor: recomendación destacada y mapa interactivo |
| Niveles de demanda (alta / media / baja) | Modo Conductor: mapa y lista |
| Perfil horario de demanda | Modo Análisis |
| Comparación de formas NY–Terrassa | Modo Análisis |
| Rentabilidad real (€/h, €/km) y tiempo en vacío | Modo Análisis |
| Tasa de acierto del recomendador | Modo Análisis |

> **Resultado obtenido**
> H1, H2 y H3 se confirman. H4 se confirma parcialmente: la correlación de las formas horarias normalizadas es r = 0,883 y la de las formas semanales r = 0,734 — aunque el contraste contra el modelo nulo del apartado 8.5 obliga a matizar su lectura. El 61,5 % de las celdas de la rejilla registra cero recogidas, lo que confirma P1 y determina las decisiones del apartado 7. La descomposición de la varianza del perfil local (P7) arroja 36,3 % explicado por el distrito frente a 53,3 % por la combinación hora × día, y la correlación entre viajes y población por distrito es de 0,885 — un hallazgo incómodo que obliga a moderar lo que el producto promete espacialmente.

---

## 3. Tipo de modelos que se van a plantear

### 3.1 Tipo de tarea

**Regresión de conteos con estructura espacio-temporal.** La variable objetivo es el número de recogidas en un par (zona, hora): un entero no negativo con fuerte exceso de ceros.

Conviene precisar por qué **no** se plantea como un problema clásico de *forecasting* univariante. Un enfoque de series temporales puras trataría cada zona como una serie independiente, lo que impide aprovechar la información cruzada entre zonas y complica la incorporación de variables de contexto. Al construir variables de retardo, el problema se convierte en **tabular de tamaño medio**, terreno en el que la literatura reciente favorece de forma consistente a los modelos basados en árboles (Grinsztajn et al., 2022; Elsayed et al., 2021).

### 3.2 Alternativas planteadas

| Alternativa | Tipo | Por qué se plantea | Limitación principal |
|---|---|---|---|
| **Baseline: persistencia semanal** | Regla ingenua: la demanda de una zona-hora es la de esa misma hora la semana anterior | Aprovecha la estacionalidad semanal, que es la señal más obvia del problema. Es deliberadamente difícil de superar de forma trivial: cualquier modelo que no lo bata no aporta nada | No reacciona a festivos, eventos ni cambios de contexto. Hereda cualquier anomalía de la semana anterior |
| **Prophet** | Modelo clásico de series temporales con descomposición aditiva | Referencia estándar del sector, modela estacionalidad múltiple y festivos de forma explícita e interpretable | Ajusta cada zona de forma aislada; no aprovecha información cruzada entre zonas. Coste de ajuste elevado al multiplicarlo por centenares de series |
| **LightGBM** (candidato principal) | Gradient boosting sobre árboles, objetivo Poisson | Maneja de forma nativa el objetivo de conteo no negativo, la variable de zona categórica de alta cardinalidad y las relaciones no lineales entre retardos y calendario. Entrenamiento rápido e importancia de variables interpretable | Requiere que las variables de retardo se construyan a mano; no extrapola fuera del rango observado |
| **LSTM** | Red neuronal recurrente | Comprobar si una arquitectura capaz de aprender dependencias secuenciales largas aporta ventaja sobre las variables de retardo explícitas | Coste de entrenamiento muy superior; exige construir secuencias deslizantes de 168 pasos, lo que limita el número de zonas tratables; menor interpretabilidad |

### 3.3 Justificación del recorte

Se descartan deliberadamente otras familias razonables (ARIMA/SARIMAX, redes espacio-temporales de tipo ST-ResNet, modelos jerárquicos bayesianos) por una razón de alcance: la entrega debe comparar **pocas alternativas bien evaluadas**, no muchas mal. Las cuatro seleccionadas cubren los tres puntos del espectro que interesan —regla trivial, modelo estadístico clásico, modelo tabular moderno y modelo profundo—, que es lo que permite responder a la pregunta de fondo: *¿cuánta complejidad compensa realmente en este problema?*

> **Resultado obtenido**
>
> | Modelo | MAE | RMSE | WAPE |
> |---|---|---|---|
> | Baseline (todas las zonas) | 4,98 | 18,85 | 28,5 % |
> | **LightGBM (todas las zonas)** | **2,87** | **9,57** | **16,5 %** |
> | Baseline (muestra 30 zonas) | 31,21 | 52,70 | 25,2 % |
> | LightGBM (muestra 30 zonas) | 16,95 | 26,58 | 13,7 % |
> | Prophet (muestra 30 zonas) | 42,77 | 63,23 | 34,5 % |
> | Baseline (muestra 20 zonas) | 36,30 | 60,35 | 24,8 % |
> | LightGBM (muestra 20 zonas) | 18,85 | 28,95 | 12,9 % |
> | LSTM (muestra 20 zonas) | 23,07 | 35,33 | 15,7 % |
>
> LightGBM es el ganador con claridad. Prophet no supera siquiera al baseline, por una razón estructural que conviene explicitar: tal como se ha empleado, ajusta cada zona aislada y sin variables exógenas, de modo que la comparación **no enfrenta dos modelos con la misma información de entrada**. El LSTM supera al baseline pero no a LightGBM, a un coste de entrenamiento de minutos frente a segundos; su cifra debe leerse como suelo y no como techo, ya que se entrenó sin identificador de zona ni normalización de entradas.

---

## 4. Datos de entrada del análisis y los modelos

### 4.1 Tabla de la capa gold

| Aspecto | Definición |
|---|---|
| Tabla principal | `data/gold/demanda_features_2023.parquet` — es el dataset que la entrega 3 denominó `gold_demanda_modelo.parquet` |
| Granularidad | **Una fila por (zona de recogida, fecha, hora)** |
| Clave primaria | `(zona, fecha, hora)` |
| Fecha de referencia | `datetime` — instante para el que se predice |
| Volumen | 2.303.880 filas × 20 columnas (263 zonas × 365 días × 24 horas) |
| Origen | 38,3 millones de viajes individuales de NYC TLC, año 2023, agregados con DuckDB |

**Decisión metodológica crítica — relleno explícito de ceros.** Toda combinación de zona y hora sin viajes se representa como demanda cero, no como fila ausente. De lo contrario el modelo nunca aprendería cuándo la demanda es nula, que es exactamente la información que evita enviar al conductor a una parada muerta. Esta decisión es la responsable de que el 61,5 % de la rejilla sea cero, y por tanto de las elecciones de métrica y función objetivo del apartado 7.

### 4.2 Variables de entrada

Variable objetivo: **`demanda`** (entero ≥ 0, recogidas en la zona y hora).

| Variable | Descripción | Tipo | Papel |
|---|---|---|---|
| `zona` | Zona de recogida (`PULocationID`, zonificación nativa de NYC TLC) | Categórica (263 niveles) | Permite aprender el perfil propio de cada zona |
| `hora` | Hora del día (0–23) | Entera | Señal temporal dominante |
| `hora_sin`, `hora_cos` | Codificación cíclica de la hora | Numéricas | Evita que las 23:00 y las 00:00 se traten como valores distantes |
| `dia_semana` | Día de la semana (0 = domingo … 6 = sábado) | Categórica | Segunda estacionalidad |
| `es_finde` | Indicador de sábado o domingo | Binaria | Captura el **cambio de forma** de la curva, no solo de nivel (H2) |
| `es_festivo` | Indicador de festivo federal de EE. UU. | Binaria | Los festivos rompen el patrón laborable |
| `mes` | Mes del año | Categórica | Estacionalidad de grano grueso |
| `dia_mes` | Día del mes | Entera | Efectos de calendario (nóminas, inicio/fin de mes) |
| `lag_1h` | Demanda de la misma zona una hora antes | Numérica | Autocorrelación de corto plazo |
| `lag_24h` | Demanda de la misma zona el día anterior a la misma hora | Numérica | Ciclo diario |
| `lag_168h` | Demanda de la misma zona la semana anterior a la misma hora | Numérica | Ciclo semanal |
| `roll_24h` | Media de la demanda de la zona en las 24 horas previas | Numérica | Nivel reciente de actividad de la zona |
| `roll_168h` | Media de la demanda de la zona en las 168 horas previas | Numérica | Nivel estructural de la zona |

**Total: 14 variables.**

Transformaciones necesarias: agregación de viajes a rejilla, relleno de ceros, cálculo de retardos y medias móviles **estrictamente hacia atrás y dentro de cada zona**, codificación cíclica de la hora, y cruce con el calendario de festivos. No se aplica escalado para los modelos basados en árboles, que no lo requieren.

Las columnas `nombre_zona`, `distrito`, `fecha`, `datetime` y `set` están presentes en la tabla pero **no se usan como variables**: las tres primeras son descriptivas o redundantes con `zona`, y las dos últimas sirven para la partición y la trazabilidad.

### 4.3 Variables descartadas y motivo

Este apartado es tan importante como el anterior, porque el conjunto de NYC TLC contiene campos que un modelo ingenuo incorporaría y que constituirían **fuga de información**.

| Variable descartada | Motivo |
|---|---|
| Importe, propina, peajes, recargos | **Leakage.** Solo se conocen al finalizar la carrera; en el momento de predecir no existen |
| Distancia y duración del viaje | **Leakage.** Mismo motivo |
| Zona de destino (`DOLocationID`) | **Leakage.** Desconocida en el momento de la decisión |
| Número de pasajeros, tipo de tarifa, forma de pago | **Leakage** y además irrelevantes para predecir el *volumen* de recogidas |
| Identificador de licencia o proveedor | Redundante para el objetivo y con riesgo de introducir sesgo de operador |
| Meteorología horaria | **No disponible alineada.** Incorporarla exigiría el histórico horario de Nueva York cruzado con la rejilla completa. Se emplea únicamente como información de contexto en el producto (aviso de lluvia), no como variable del modelo. Queda como línea futura |
| Direcciones de origen y destino del registro del taxista | **Privacidad.** Son dato personal indirecto; no salen del entorno de trabajo ni se publican (entrega 2, apartado 4) |

Conviene señalar que este descarte **no se implementa como un filtrado posterior**: la agregación de la fase 1 solo cuenta recogidas (`COUNT(*)` por zona, fecha y hora), de modo que ninguno de esos campos llega siquiera a la capa `processed`. La fuga es imposible por construcción, no por disciplina.

### 4.4 Información realmente disponible en el momento de la predicción

Es necesario precisar esto porque determina la lectura de todas las métricas:

- Las **variables de calendario** son conocidas con antelación indefinida.
- Las **variables de retardo** requieren que el histórico esté actualizado hasta el instante anterior. En un sistema en explotación esto es realista para `lag_1h`, ya que la demanda de la hora recién terminada se conoce.
- En consecuencia, el modelo se evalúa a **horizonte de una hora (predicción a un paso)**. Esto es coherente con el caso de uso —el conductor decide dónde colocarse en la próxima hora, no la próxima semana— pero debe declararse: **a horizontes mayores `lag_1h` deja de estar disponible** y tendría que sustituirse por la propia predicción del modelo, acumulando error. Las métricas reportadas no deben leerse como capacidad predictiva a largo plazo.

### 4.5 Fuentes secundarias

| Tabla | Granularidad | Uso |
|---|---|---|
| `data/external/perfil_movilidad_terrassa.csv` | Distrito × hora × día de la semana (1.176 filas) | Perfil local para la comparación de formas y para la recomendación actual del MVP |
| `data/external/paradas_terrassa.csv` | Una fila por parada (14) | Geolocalización de las paradas |
| `data/external/terrassa_distritos.geojson` | Un polígono por distrito (7) | Asignación parada → distrito y población |
| Registro de carreras (Sheets / `data/registro/`) | Una fila por carrera registrada | Verdad de campo para evaluar el recomendador y calcular rentabilidad |

---

## 5. Datos de salida y forma de consumo

### 5.1 Definición de la salida

La salida principal es una **predicción de conteo** (número esperado de recogidas), a partir de la cual se deriva un **ranking** de paradas, que es la forma en que realmente se consume.

| Campo de salida | Descripción | Tipo | Uso posterior |
|---|---|---|---|
| `nombre` | Identificador de la parada de taxi (o `zona` en el contexto de Nueva York) | string / integer | Trazabilidad y unión con la geolocalización |
| `datetime` | Instante al que se refiere la predicción | datetime | Alineación temporal y evaluación posterior |
| `valor` | Estimación de demanda esperada | float ≥ 0 | Cálculo del ranking |
| `nivel` | Nivel discretizado: alta / media / baja | categoría | **Es lo que se muestra al usuario** |
| `posicion` | Posición de la parada en el ranking de ese instante | integer | Recomendación destacada y orden de la lista |
| `distrito` | Distrito al que pertenece la parada | string | Contexto mostrado en la recomendación |
| `factores_contexto` | Festivo, lluvia y otros elementos de contexto aplicados | texto | Explicación al usuario |

### 5.2 Formato y consumo

- **Formato interno:** tabla en la capa gold (Parquet), regenerable desde la capa raw. El modelo entrenado se serializa en `models/lgbm_demanda_nyc.txt`, en el formato nativo de LightGBM, acompañado de un JSON con las variables, el mapeo de categorías, los hiperparámetros y las métricas.
- **Consumo:** aplicación web desarrollada con Streamlit, accesible desde el navegador del móvil y añadible a la pantalla de inicio. El usuario no instala nada.
- **Acción que habilita:** el conductor consulta el modo Conductor al terminar una carrera y se dirige a la parada destacada.

### 5.3 Qué explicación e incertidumbre se muestran

Este punto merece una decisión de diseño explícita, y no la trivial.

**La salida numérica no se muestra al usuario.** Se muestran niveles (alta / media / baja), asignados por terciles sobre los valores presentes en cada instante, no mediante umbrales fijos. Hay dos razones:

1. **Honestidad sobre la precisión.** Mostrar «7,3 carreras esperadas» transmitiría una exactitud que el dato no tiene, especialmente mientras la recomendación se apoya en un proxy de movilidad general y no en demanda de taxi medida.
2. **Razón empírica.** Con umbrales fijos sobre el máximo, ninguna parada alcanzaba nunca el nivel bajo, porque el único distrito de actividad reducida de Terrassa (el 07, que agrupa Can Parellada y les Fonts) no contiene ninguna parada de taxi. El criterio por terciles corrige ese artefacto.

Se muestran además, como contexto y no como predicción: el aviso de lluvia, la marca de festivo, y —en la evaluación— la **proporción de carreras emparejadas**, para que quien lea la métrica pueda juzgar su cobertura.

---

## 6. Estrategia para diseñar y seleccionar el modelo

### 6.1 Proceso

1. **Preparación del dataset** a partir de la capa gold: relleno de ceros, construcción de retardos y medias móviles hacia atrás por zona, variables de calendario y codificación cíclica.
2. **Definición de la variable objetivo**: `demanda` por (zona, hora).
3. **Construcción del baseline** de persistencia semanal, calculado sobre exactamente las mismas filas que evaluarán los modelos.
4. **Entrenamiento de los candidatos** sobre la misma partición y las mismas variables, salvo donde una limitación estructural lo impida (documentada más abajo).
5. **Comparación** según los criterios de 6.3.
6. **Aplicación de la regla de decisión** de 6.4.

### 6.2 Preprocesamiento

| Tratamiento | Decisión | Motivo |
|---|---|---|
| Nulos | No hay nulos por construcción tras el relleno de ceros, salvo en los retardos del arranque de cada zona, que se descartan | El retardo semanal no existe para las primeras 168 horas de cada serie |
| Escalado | No se aplica para modelos de árbol | Invariantes a transformaciones monótonas |
| Codificación de la zona | Categórica nativa de LightGBM | Evita crear 263 columnas *dummy* |
| Codificación de la hora | Cíclica (seno y coseno), además de la variable entera | Preserva la contigüidad entre las 23:00 y las 00:00 |
| Desbalance / exceso de ceros | No se remuestrea; se aborda mediante la **función objetivo Poisson** | Remuestrear distorsionaría la distribución que precisamente se quiere aprender |

> ⚠️ **Limitación declarada**: el LSTM se entrenó **sin normalizar las entradas y sin identificador de zona**, lo que lo sitúa en desventaja respecto a LightGBM. Su resultado debe interpretarse como cota inferior de lo que una red recurrente podría dar en este problema, no como demostración de que el enfoque profundo no funciona.

### 6.3 Criterios de comparación

| Criterio | Peso en la decisión |
|---|---|
| Calidad predictiva (WAPE sobre el conjunto de prueba) | Principal, pero no único |
| Estabilidad entre segmentos y periodos | Alto: un modelo que gana en media pero falla en las horas punta no sirve |
| Interpretabilidad | Alto: el producto debe poder explicar por qué recomienda una parada |
| Coste computacional y reproducibilidad | Medio: el proyecto debe poder reentrenarse en un equipo personal |
| Utilidad para el MVP | Alto: la salida debe integrarse sin fricción en la aplicación |

### 6.4 Regla de decisión final

Un modelo se selecciona como modelo de producción si y solo si cumple **todas** estas condiciones:

1. **Supera el baseline** en WAPE con una mejora relativa de al menos el **20 %**.
2. Se **entrena y evalúa de forma reproducible** en un equipo personal en un tiempo asumible (orden de minutos, no de horas).
3. Permite **explicar la recomendación** al menos a nivel de importancia de variables.
4. En caso de empate práctico entre dos modelos (diferencia de WAPE inferior a 1 punto porcentual), **gana el más simple, más rápido y más interpretable**.

Esta última cláusula es deliberada: la mejor métrica no es el único criterio. Un modelo ligeramente menos preciso pero estable, explicable y reentrenable es preferible para un producto que una persona sin perfil técnico va a usar a diario.

> **Resultado obtenido**
> LightGBM cumple las cuatro condiciones. La mejora relativa sobre el baseline es del 42 % en WAPE (del 28,5 % al 16,5 %), muy por encima del umbral del 20 %. El LSTM cumple la condición 1 pero no la 2 (coste de minutos frente a segundos) ni la 3, y además queda por debajo en métrica, por lo que la cláusula 4 ni siquiera llega a aplicarse. Prophet no cumple la condición 1.
>
> Los hiperparámetros de LightGBM se fijaron a valores habituales para problemas de conteo de este tamaño, **sin búsqueda sistemática**. Es una limitación real: no puede afirmarse que sea la configuración óptima, solo que la configuración razonable elegida ya cumple el criterio de aceptación con holgura.

---

## 7. Estrategia de validación y evaluación

### 7.1 Separación de los datos

**Partición temporal, no aleatoria.** Se entrena con los meses de enero a octubre y se evalúa con noviembre y diciembre. La partición se materializa en la columna `set` de la capa gold, de modo que todos los scripts evalúan exactamente sobre las mismas filas.

El motivo es directo: una separación aleatoria permitiría al modelo entrenar con observaciones posteriores a las que predice, es decir, **«ver el futuro»**. Con variables de retardo y fuerte autocorrelación, esto produciría métricas espectaculares y completamente falsas. La partición temporal reproduce el uso real del sistema, donde solo se dispone del pasado.

Volumen resultante: 1.874.664 filas de entrenamiento y 385.032 de prueba, tras descartar las filas de arranque sin retardo.

### 7.2 Cómo se evita la contaminación

| Riesgo | Cómo se controla |
|---|---|
| Información futura en las variables | Los retardos y medias móviles se calculan **exclusivamente hacia atrás** y dentro de cada zona; las medias móviles parten de `shift(1)` para no incluir el instante actual |
| Variables no disponibles en el momento real de uso | Nunca llegan a la capa `processed`: la agregación solo cuenta recogidas (apartado 4.3) |
| Solape entre entrenamiento y prueba | El corte es un único instante temporal global: ninguna zona ve su propio futuro |
| Fuga por normalización | No se aplica escalado global previo a la partición en los modelos de árbol |
| Divergencia entre el sistema evaluado y el desplegado | El ranking que evalúa el recomendador se calcula con **la misma función** que alimenta la vista del conductor |

### 7.3 Métricas

| Métrica | Por qué |
|---|---|
| **WAPE** (error porcentual absoluto ponderado) — *métrica principal* | Es interpretable como porcentaje y, a diferencia del MAPE, **es estable con ceros** porque pondera por el volumen total en lugar de dividir observación a observación |
| **MAE** | Error medio en unidades interpretables (carreras) |
| **RMSE** | Penaliza los errores grandes; informa sobre el comportamiento en los picos, que es donde reside el valor para el usuario |
| **MAPE** — *descartado* | Exige dividir por el valor real. Con un 61,5 % de celdas a cero se vuelve indefinido o desproporcionado |
| **Hit-rate@3** — *métrica de producto* | Evalúa lo que el usuario realmente consume (un ranking), no lo que el modelo produce internamente |

### 7.4 Comparación con el baseline

El baseline se **recalcula sobre exactamente las mismas filas** que cada modelo evalúa. Esto importa: cuando Prophet y el LSTM se evalúan sobre submuestras de zonas (30 y 20 respectivamente, por coste computacional), tanto el baseline como LightGBM se reentrenan y recalculan sobre esas mismas zonas. De lo contrario la comparación mediría poblaciones distintas y no diría nada.

### 7.5 Análisis de errores

El WAPE global oculta dónde falla el modelo. Se desagrega sobre tres cortes (`pipeline/fase3_analisis_errores.py`).

> **Resultado obtenido**
>
> | Corte | Segmento | Demanda media | WAPE baseline | WAPE LightGBM | Mejora |
> |---|---|---|---|---|---|
> | Franja horaria | Madrugada (0–5) | 5,60 | 51,8 % | 28,7 % | 44,6 % |
> | Franja horaria | Mañana (6–11) | 14,74 | 28,2 % | 16,7 % | 40,9 % |
> | Franja horaria | Tarde (12–16) | 24,95 | 21,4 % | 13,0 % | 39,1 % |
> | Franja horaria | Punta (17–20) | 27,01 | 26,5 % | 14,9 % | 43,7 % |
> | Franja horaria | Noche (21–23) | 21,27 | 34,2 % | 19,1 % | 44,2 % |
> | Tipo de día | Laborable | 18,16 | 25,6 % | 15,5 % | 39,3 % |
> | Tipo de día | Fin de semana | 16,49 | 31,7 % | 18,2 % | 42,6 % |
> | Tipo de día | **Festivo** | 14,29 | 50,4 % | **19,9 %** | **60,5 %** |
> | Nivel de la zona | **Zona baja** | 0,06 | 169,8 % | **167,8 %** | **1,2 %** |
> | Nivel de la zona | Zona media | 0,39 | 131,1 % | 116,3 % | 11,2 % |
> | Nivel de la zona | Zona alta | 51,68 | 27,6 % | 15,5 % | 43,7 % |
>
> Tres lecturas, y la tercera es incómoda:
>
> 1. **El modelo mejora al baseline en todos los segmentos sin excepción**, entre un 39 % y un 60 %. No hay ningún corte en el que la ganancia media se deba a compensación entre subgrupos.
> 2. **La mayor ganancia está en los festivos (60,5 %).** Es coherente: el baseline copia la semana anterior y por tanto falla sistemáticamente cuando el día rompe el patrón, mientras que el modelo dispone de `es_festivo`. Es exactamente la debilidad que se le atribuía al baseline en el apartado 3.2, ahora cuantificada.
> 3. **El modelo es inservible en las zonas de demanda baja.** Con una demanda media de 0,06 recogidas por hora, el WAPE es del 167,8 % y la mejora sobre el baseline apenas del 1,2 %. El WAPE global del 16,5 % está enteramente sostenido por las zonas de demanda alta, que concentran el volumen. Esto **no invalida el resultado** —el usuario opera en zonas con actividad, no en las muertas— pero sí acota con precisión dónde el sistema tiene valor y dónde no lo tiene, y es una limitación que el número agregado escondía por completo.

### 7.6 Criterio de aceptación y plan si no se alcanza

**Resultado mínimo aceptable:** una mejora relativa del 20 % en WAPE sobre el baseline de persistencia semanal.

**Si ningún modelo lo alcanzara**, el plan por orden de aplicación sería:

1. **Enriquecer las variables** antes que cambiar de modelo: más retardos, interacciones zona × hora explícitas, histórico meteorológico.
2. **Reducir la ambición del horizonte** o agregar a franjas de dos o tres horas, si la resolución horaria resulta demasiado ruidosa.
3. **Degradar a un sistema basado en reglas**: recomendar según el perfil histórico medio de cada zona por hora y día de la semana, sin modelo entrenado.

Esta tercera alternativa no es hipotética: **es exactamente lo que alimenta hoy la recomendación del MVP**, mientras la calibración local no dispone de datos suficientes. El proyecto tiene, por tanto, su plan B ya implementado y en funcionamiento.

### 7.7 Resumen de decisiones

| Elemento | Decisión | Justificación |
|---|---|---|
| Separación de datos | Split temporal: ene–oct entrenamiento, nov–dic prueba | Evita ver el futuro y reproduce el uso real |
| Métrica principal | WAPE | Interpretable y estable ante el 61,5 % de ceros |
| Métricas secundarias | MAE, RMSE | Unidades interpretables y sensibilidad a los picos |
| Métrica de producto | Hit-rate@3 frente al 21 % del azar | Mide lo que el usuario consume |
| Baseline | Persistencia semanal, recalculado por submuestra | Mide la mejora real, no una comparación desalineada |
| Criterio de aceptación | ≥ 20 % de mejora relativa en WAPE | Umbral por debajo del cual el modelo no justifica su complejidad |

> **Limitación declarada**: la validación emplea **un único corte temporal**. Un esquema de validación cruzada de origen móvil, con varios cortes sucesivos, permitiría acompañar las métricas de intervalos de confianza y descartar que el resultado dependa del bimestre concreto elegido. No se ha implementado por coste de cómputo.

---

## 8. Riesgos y alternativas

### 8.1 ¿La variable objetivo representa realmente el fenómeno?

**Parcialmente, y conviene ser preciso.** La variable objetivo es el número de recogidas *efectivamente realizadas*, es decir, **demanda atendida**, no demanda latente. No se observan los clientes que no encontraron taxi, ni los que optaron por otro medio. En una zona saturada, la demanda real puede ser sistemáticamente superior a la registrada.

Para el caso de uso esto es aceptable —al conductor le interesa dónde consigue carreras, no dónde hay demanda insatisfecha teórica— pero es un sesgo que debe declararse y que impediría usar el modelo para dimensionar una flota.

### 8.2 Riesgo de data leakage

**Identificado y controlado, pero con un matiz que hay que declarar.** Las variables post-carrera no llegan siquiera a la capa `processed` (4.3) y los retardos se calculan solo hacia atrás. El riesgo residual no es de contaminación, sino de **interpretación**: al incluir `lag_1h`, el modelo opera a horizonte de una hora con el valor real inmediatamente anterior ya observado. Las métricas son honestas para ese horizonte, pero **sobreestimarían la capacidad del sistema si se leyeran como predicción a largo plazo**. Se declara en el apartado 4.4 y se recoge como limitación en la memoria.

### 8.3 ¿Son suficientes el volumen, el histórico y la calidad?

| Fuente | Suficiencia |
|---|---|
| NYC TLC | **Sí, holgadamente.** 38,3 M de viajes, 2,3 M de filas en la rejilla, un año completo. La ausencia de tendencia anual marcada respalda el uso de un solo año |
| MITMA | **Suficiente para comparar formas, insuficiente para calibrar.** Muestra parcial del año, resolución de distrito |
| Registro del taxista | **Insuficiente hoy.** Es la limitación principal del proyecto y se acumula de forma continua a través de la aplicación |

### 8.4 Desbalance, cambios temporales y sesgos de cobertura

- **Exceso de ceros (61,5 %):** abordado mediante objetivo Poisson y métrica WAPE, no mediante remuestreo.
- **Concentración espacial extrema:** confirmada y cuantificada en 7.5. Las zonas de demanda baja tienen un WAPE del 167,8 % y el modelo no las mejora. El WAPE global las oculta porque pondera por volumen.
- **Sesgo de cobertura del proxy local:** la señal espacial del MITMA correlaciona a **0,885 con la población del distrito**, de modo que el ranking espacial reproduce en buena parte la distribución poblacional y no una intensidad de demanda de taxi por habitante. Es el sesgo más serio del sistema actual.
- **Resolución espacial insuficiente:** 7 distritos para 14 paradas. Cuatro paradas caen en el distrito 01 y comparten por construcción el mismo valor. El sistema puede ordenar distritos, no discriminar entre paradas de un mismo distrito.
- **Cambio de contexto entre ciudades:** Terrassa arranca antes y de forma más abrupta por la mañana; Nueva York mantiene una cola nocturna mucho más alta. Ambas diferencias señalan los tramos donde la recalibración local será más necesaria.

### 8.5 Qué parte genera más incertidumbre

**La transferencia.** El resto del proyecto se apoya en datos abundantes y validación estándar; la transferencia se sostiene sobre una correlación de formas normalizadas entre un dataset de viajes de taxi y un proxy de movilidad general de otra ciudad, otro país y otra escala.

El diseño inicial se limitaba a reportar esa correlación. Es insuficiente: dado que *cualquier* par de perfiles de movilidad urbana comparte valle nocturno y meseta diurna, una correlación alta puede ser en parte automática. Se ha añadido por ello un **contraste contra un modelo nulo** (`pipeline/fase3_analisis_errores.py`).

> **Resultado obtenido**
>
> | Medida | Valor | Lectura |
> |---|---|---|
> | r observado (NYC vs Terrassa) | **0,883** | Correlación de las formas horarias normalizadas |
> | Media del nulo por permutación | 0,002 | Correlación esperada si la alineación horaria fuese casual |
> | Percentil 95 del nulo | 0,350 | Umbral que hay que superar para no ser azar |
> | p-valor (20.000 permutaciones) | **0,00005** | Proporción de permutaciones que igualan o superan el r observado |
> | r medio entre distritos de Terrassa | **0,980** | Suelo urbano genérico: dos perfiles de la *misma* ciudad |
> | r mínimo entre distritos de Terrassa | 0,935 | El par de distritos menos parecido entre sí |
> | r NYC vs distrito más parecido | 0,916 | Distrito 03 (Sud) |
> | r NYC vs distrito menos parecido | 0,774 | Distrito 04 (Ponent) |
>
> La lectura tiene dos mitades y la segunda obliga a moderar el discurso.
>
> **La correlación no es casual.** Frente a una media nula de 0,002 y un percentil 95 de 0,350, el valor observado de 0,883 arroja un p-valor de 0,00005. La alineación horaria entre ambos perfiles es real y no un artefacto de la métrica.
>
> **Pero tampoco es una afinidad particular entre estas dos ciudades.** Dos distritos cualesquiera de la propia Terrassa correlacionan de media a 0,980 —y en el peor de los casos a 0,935—, es decir, **más entre sí que Terrassa con Nueva York**. El 0,883 confirma la existencia de un ritmo urbano común, no que Nueva York sea un buen sustituto de Terrassa en particular. La dispersión por distritos (de 0,774 a 0,916) apunta en la misma dirección: la calidad de la transferencia depende del distrito, y el peor de ellos queda claramente por debajo del suelo urbano genérico.
>
> Esto **no invalida la estrategia** —transferir la forma temporal sigue siendo defendible y es lo único posible sin datos locales—, pero sí obliga a formularla con precisión: lo que se transfiere es el ritmo urbano general, no un patrón específico de demanda de taxi. La calibración local no es un refinamiento opcional; es lo que separaría este sistema de aplicar una curva diaria genérica.

### 8.6 Alternativas si la estrategia no funciona

| Si falla | Alternativa |
|---|---|
| Ningún modelo supera el baseline | Enriquecer variables → agregar a franjas de 2–3 h → degradar a sistema de reglas sobre perfil histórico (**ya implementado**) |
| La transferencia no se sostiene | Reformular el trabajo como *evaluación de la viabilidad* de la transferencia. Un resultado negativo bien medido sigue siendo un hallazgo publicable y defendible |
| El proxy local resulta inservible | Sustituirlo por una ponderación de cada parada según sus atractores de demanda (estaciones, hospitales, zonas de ocio) |
| El volumen local nunca llega a ser suficiente | Mantener el sistema como herramienta de análisis de rentabilidad, que ya aporta valor con los datos actuales, y documentar la predicción como no calibrada localmente |

---

## 9. Cambios respecto a entregas anteriores

El enunciado exige mantener la trazabilidad de las decisiones modificadas. Las entregas 1 a 3 se conservan sin alterar; los cambios se documentan aquí.

### 9.1 Cambios de alcance

| # | Entrega | Decisión original | Estado actual | Motivo |
|---|---|---|---|---|
| 1 | 1 (idea 3) | La idea se planteaba como **plataforma de gestión integral**: agenda, ingresos, **gastos** y **clientes habituales**, además de la predicción de demanda | Acotada a predicción de demanda, análisis de rentabilidad y registro de viajes. Gastos y agenda quedan fuera | Cada función añadida al registro aumenta la fricción, señalada como riesgo en la entrega 2 (apartado 3). Además, el taxi de calle no funciona por cita previa, de modo que la agenda no aporta a la decisión de posicionamiento |
| 2 | 2 (apartado 1) | El LSTM figuraba explícitamente **«como línea futura»** | **Ejecutado y comparado** con el resto de modelos | Se resolvió la incompatibilidad del entorno (TensorFlow no publica distribuciones para Python 3.14; se migró el proyecto a 3.12) |

### 9.2 Cambios en las variables

| # | Entrega | Decisión original | Estado actual | Motivo |
|---|---|---|---|---|
| 3 | 2 (apartado 2) | La **meteorología** figuraba entre las variables de contexto necesarias, como «deseable pero no obligatoria» | Se emplea **solo como información de contexto** mostrada al conductor (aviso de lluvia), no como variable del modelo | Incorporarla exigiría el histórico meteorológico horario de Nueva York alineado con la rejilla completa, que no se ha obtenido. Queda como línea futura |
| 4 | 3 (apartado 4) | `dia_semana` se definía como `int (0–6)` sin especificar la convención | **0 = domingo** en la tabla de Nueva York (convención `EXTRACT(dow)` de DuckDB); **1 = lunes** en el perfil del MITMA | Son fuentes distintas con convenciones distintas. La ambigüedad era una fuente real de error al cruzarlas y ha obligado a conversiones explícitas en el código |
| 5 | 3 (apartado 4) | `gold_carreras_rentabilidad` preveía almacenar `duracion_min`, `eur_por_km` y `eur_por_hora` como columnas | Se **derivan en tiempo de ejecución** a partir de las horas y los importes registrados | El registro guarda únicamente lo observado en el ticket. Almacenar magnitudes derivadas obligaría a recalcularlas ante cualquier corrección |

### 9.3 Cambios en la capa gold

| # | Entrega | Decisión original | Estado actual | Motivo |
|---|---|---|---|---|
| 6 | 3 (apartados 3 y 4) | Capa gold con **cuatro datasets**: `gold_demanda_modelo.parquet`, `gold_perfil_terrassa.csv`, `gold_carreras_rentabilidad.csv` y `gold_paradas_terrassa.csv` | Solo la tabla de modelado vive en `data/gold/` (como `demanda_features_2023.parquet`). El perfil del MITMA y las paradas están en `data/external/`, y el registro de carreras en `data/registro/` | Se impuso una distinción que la entrega 3 no hacía: `gold/` contiene lo **derivado y regenerable** desde `raw/`; `external/` lo que procede de terceros y se versiona tal cual; y `registro/` el dato personal, excluido del control de versiones. Agruparlo todo bajo `gold/` habría mezclado tres regímenes distintos de regeneración y de privacidad |
| 7 | 3 (apartado 4) | `gold_perfil_terrassa` preveía los campos `viajes_norm` (normalizado 0–1) y `nivel_demanda` (alta/media/baja) precalculados | El fichero guarda el **conteo bruto** (`viajes`); la normalización y el nivel se calculan en tiempo de ejecución | Precalcular el nivel obliga a fijar umbrales, y los umbrales fijos resultaron inservibles: ninguna parada alcanzaba nunca el nivel bajo (véase 5.3). El criterio por terciles debe recalcularse sobre los valores presentes en cada instante |
| 8 | 3 (apartado 3) | Se preveía que `gold_demanda_modelo.parquet` fuese una **copia** de `demanda_features_2023.parquet` | No se duplica: la tabla de `gold/` **es** la tabla de modelado | Mantener dos copias del mismo fichero de 13 MB introduce riesgo de divergencia sin aportar nada |

### 9.4 Reglas de limpieza previstas y no implementadas

Este apartado merece detalle porque son divergencias que **no se han corregido**, y conviene declararlas antes que ocultarlas.

| # | Entrega | Regla prevista | Estado | Valoración |
|---|---|---|---|---|
| 9 | 3 (apartado 8) | «Descartes: viajes NYC con **distancia ≤ 0, importe ≤ 0 o duración fuera de rango**» | **No implementada** | Sin efecto práctico: la agregación de la fase 1 solo cuenta recogidas (`COUNT(*)` por zona, fecha y hora), de modo que distancia, importe y duración no intervienen en ningún cálculo. Un viaje con importe negativo sigue siendo una recogida que ocurrió |
| 10 | 3 (apartado 6) | «`zona`: excluir **264/265** (desconocidas)» | **No implementada** | Sí tiene efecto y debe declararse. Ambas zonas permanecen en la rejilla y acumulan **387.213 recogidas** (356.727 en la 264 y 30.486 en la 265), en torno al 1 % del total. No son lugares físicos —264 es «desconocida» y 265 «fuera de Nueva York»—, de modo que el modelo aprende el patrón de dos categorías residuales. No afecta al producto, porque la recomendación opera sobre paradas de Terrassa y no sobre zonas de Nueva York, pero sí introduce un pequeño sesgo en las métricas globales. **Pendiente de corregir**; hacerlo obligaría a reentrenar y a actualizar todas las cifras reportadas |
| 11 | 3 (apartado 8) | «Fechas y horas: **conversión a zona horaria local** de cada contexto antes de construir features» | **No implementada** | Sin efecto: cada contexto se trabaja en su propia hora local (las marcas de NYC TLC ya vienen en hora local de Nueva York, y el perfil del MITMA en hora peninsular) y **nunca se cruzan por marca temporal**. La comparación entre ambos es de forma horaria normalizada, no de instantes concretos |

Como nota de precisión sobre el recuento de zonas: la rejilla contiene **263 zonas** porque el catálogo de NYC TLC define 265 y las zonas **103 y 104** no registran ninguna recogida en todo 2023, por lo que no entran en el producto cartesiano.

### 9.5 Precisiones añadidas en esta entrega

Decisiones que las entregas anteriores no fijaban y que este diseño concreta.

| # | Aspecto | Precisión |
|---|---|---|
| 12 | Horizonte de predicción | No se fijaba explícitamente. Se establece en **una hora (predicción a un paso)**, con `lag_1h` observado. Determina la lectura de todas las métricas (apartado 4.4) |
| 13 | Validación de la transferencia | La entrega 2 daba por buena la correlación de 0,88. Se añade un **contraste contra modelo nulo** —test de permutación y correlaciones internas entre distritos— porque una correlación alta entre dos perfiles urbanos puede ser en parte automática (apartado 8.5) |
| 14 | Análisis de errores | Estaba planteado pero no ejecutado. **Ejecutado y reportado** en 7.5. Reveló que el modelo es inservible en zonas de demanda baja, limitación que el WAPE global ocultaba |
| 15 | Medición del objetivo | El objetivo de reducir kilómetros en vacío, declarado en las entregas 1 y 2, no tenía forma de medirse. El producto **mide ahora el tiempo en vacío** a partir del hueco entre carreras registradas |
| 16 | Muestra del MITMA | La entrega 2 indicaba «una semana por trimestre de 2023». Se concreta: 28 días, las semanas del 13–19 de febrero, 15–21 de mayo, 11–17 de septiembre y 13–19 de noviembre, extraídos con el paquete `spanishoddata` a nivel de distrito (`ver = 2`) y filtrados por el código INE 08279 |

Ninguna de estas modificaciones altera la idea de producto seleccionada, el usuario al que se dirige ni las fuentes de datos previstas.

---

## 10. Referencias

- Elsayed, S., Thyssens, D., Rashed, A., Schmidt-Thieme, L. y Jomaa, H. S. (2021). *Do We Really Need Deep Learning Models for Time Series Forecasting?* arXiv:2101.02118.
- Grinsztajn, L., Oyallon, E. y Varoquaux, G. (2022). *Why do tree-based models still outperform deep learning on typical tabular data?* NeurIPS 35.
- Ke, G. et al. (2017). *LightGBM: A Highly Efficient Gradient Boosting Decision Tree.* NeurIPS 30.
- Taylor, S. J. y Letham, B. (2018). *Forecasting at Scale.* The American Statistician, 72(1), 37–45.
- Zhang, J., Zheng, Y. y Qi, D. (2017). *Deep Spatio-Temporal Residual Networks for Citywide Crowd Flows Prediction.* AAAI 31(1).
