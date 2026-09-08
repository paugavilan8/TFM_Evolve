# Entrega 2 — Selección de idea de proyecto y análisis de datos necesarios

**Proyecto:** Sistema inteligente de predicción de demanda para taxistas autónomos — transferencia de modelos de Nueva York a Terrassa y producto funcional para un caso real

---

## 1. Idea seleccionada

**Idea:** Un sistema de predicción de demanda y apoyo a la decisión para taxistas autónomos, aplicado a un caso de uso real en la ciudad de Terrassa.

**Problema que resuelve.** El taxista autónomo compite con plataformas de vehículos con conductor que disponen de sistemas sofisticados de predicción y asignación de demanda, mientras que él opera fundamentalmente con intuición y experiencia, sin herramientas analíticas que le ayuden a decidir dónde y cuándo posicionarse. Esto se traduce en tiempo de circulación sin pasaje (kilómetros en vacío) y en falta de visibilidad sobre su propia rentabilidad. El problema es relevante porque afecta directamente a los ingresos y a la eficiencia de un colectivo profesional concreto, y el valor de resolverlo es doble: reducir los kilómetros improductivos y dar al conductor información clara sobre cuánto gana realmente. El caso arranca de una necesidad real y cercana: una taxista autónoma en activo en Terrassa (cooperativa Tele-Taxi Egara).

**Solución planteada.** Desde un enfoque de Data Science, se entrena un modelo de predicción de demanda espacio-temporal (por zona y franja horaria). El reto metodológico central es que **no existen datos públicos de viajes de taxi a nivel local** (ni en Terrassa ni en Barcelona), por lo que la estrategia consiste en entrenar el modelo sobre un conjunto de datos abundante y abierto —los registros de taxi de Nueva York (NYC TLC)— y **transferir el patrón a Terrassa**, distinguiendo entre lo que se transfiere (la *forma* de los patrones temporales) y lo que debe recalibrarse (la *escala* y la geografía locales), apoyándose en fuentes de movilidad locales. La comparativa rigurosa de modelos (baseline ingenuo, Prophet, LightGBM y, como línea futura, LSTM) selecciona el mejor mediante métricas cuantitativas.

**MVP del proyecto final.** El producto mínimo viable es una **aplicación funcional y desplegada**, usable por un conductor sin perfil técnico desde el móvil, con tres modos integrados: (1) *Conductor* — recomienda la parada a la que dirigirse y muestra un mapa de Terrassa con la demanda prevista por zonas en niveles (alta/media/baja); (2) *Registrar* — captura las carreras fotografiando el ticket, del que un modelo de visión extrae los datos para que el usuario los confirme; y (3) *Análisis* — muestra los patrones de demanda, la validación de la transferencia y la rentabilidad real del conductor. Al final del curso podrá verse funcionando el modelo de predicción, el mapa de recomendación de paradas y el cálculo de rentabilidad en tiempo real a partir de los datos registrados.

---

## 2. Datos necesarios

**Variables o campos.**
- **Demanda agregada (variable objetivo):** número de recogidas por combinación de zona × fecha × hora.
- **Variables de calendario:** hora, día de la semana, mes, indicador de fin de semana e indicador de festivo.
- **Variables de retardo (lags) y medias móviles:** demanda de la misma zona 1 hora antes, 24 horas antes y 168 horas antes (una semana), más medias móviles. Son las de mayor capacidad predictiva, al capturar la fuerte autocorrelación temporal.
- **Variables externas de contexto:** meteorología (temperatura, precipitación, etc.) y calendario de festivos.
- **Movilidad local (proxy):** matrices origen-destino por hora y distrito censal para los siete distritos de Terrassa.
- **Datos reales de carreras del taxista:** fecha, hora de inicio y fin, direcciones de origen y destino, distancia, importe y tipo de servicio.

**Granularidad.** Resolución **horaria** y a nivel de **zona** (la zonificación nativa de Nueva York para el entrenamiento; los siete distritos de Terrassa para la transferencia). Los datos del taxista se registran a nivel de **carrera individual** (transacción).

**Profundidad histórica.** Serie temporal de al menos **un año completo** para capturar la estacionalidad diaria, semanal y anual (se usa el año 2023 de NYC TLC). Para la movilidad local, una **muestra representativa** (una semana por trimestre de 2023). Los datos del taxista se acumulan de forma **continua** desde el inicio del registro.

**Volumen aproximado.** Del orden de **millones de filas** en la tabla de entrenamiento: la rejilla zona × fecha × hora de Nueva York contiene **2.303.880 filas**. Un aspecto metodológico clave es el *relleno de ceros*: toda combinación de zona y hora sin viajes se representa explícitamente como demanda cero (no como dato ausente), para que el modelo aprenda también cuándo la demanda es nula.

**Imprescindibles vs. deseables.**
- **Imprescindibles:** registros de viajes de NYC TLC (base del entrenamiento), matrices de movilidad del MITMA para Terrassa (base de la transferencia) y datos reales del taxista (validación y caso de uso).
- **Deseables pero no obligatorios:** meteorología y festivos (mejoran la precisión pero el sistema funciona sin ellos), y un mayor volumen de datos reales del taxista para la calibración fina, parada a parada.

---

## 3. Fuentes de datos previstas

| Fuente | Qué aporta | Acceso | Formato | Histórico |
|---|---|---|---|---|
| **NYC TLC — Trip Record Data** | Viajes de Yellow Taxi (base de entrenamiento) | Abierta, pública, sin restricciones | Parquet | Sí, por meses/años |
| **MITMA — Estudio de la movilidad con Big Data** | Matrices O-D por hora y distrito (transferencia) | Abierta, pública (datos anonimizados) | Ficheros descargables / open data | Sí, por periodos |
| **Open-Meteo** | Variables meteorológicas | Abierta, API gratuita | API (JSON) | Sí, histórico y actual |
| **Registro real del taxista (Tele-Taxi Egara)** | Carreras reales (validación y rentabilidad) | Privada, con consentimiento informado | Foto de ticket → campos estructurados → hoja de cálculo en la nube | Se acumula de forma continua |

**Enlaces previstos** (verificar el enlace exacto de descarga antes de la entrega):
- NYC TLC Trip Record Data — portal de datos abiertos de la ciudad de Nueva York (`nyc.gov/site/tlc/.../tlc-trip-record-data.page`).
- MITMA — Open Data Movilidad (`opendata-movilidad.mitma.es`).
- Open-Meteo — Free Weather API (`open-meteo.com`).
- Paquete `spanishoddata` (Kotov et al.) para el acceso programático a los datos de movilidad españoles.

**Estabilidad y mantenimiento.** NYC TLC, MITMA y Open-Meteo son fuentes públicas, documentadas y mantenidas de forma estable. El registro del taxista depende de la continuidad del propio usuario.

**Riesgos detectados.**
- La fuente de movilidad local mide **movilidad general, no demanda de taxi**: actúa como *proxy*, limitación que se documenta explícitamente.
- **Ausencia total de datos públicos de viajes de taxi locales** — es precisamente el reto que estructura el proyecto.
- **Volumen aún reducido** de datos reales del taxista, en proceso de acumulación; la calibración fina requerirá más registros.
- Posibles cambios en portales/API o límites de descarga.
- Fricción en el registro manual del taxista (mitigada con la captura por fotografía del ticket).

---

## 4. Consideraciones de privacidad y protección de datos

- **Información personal identificable.** Los datos del taxista incluyen direcciones de origen y destino de carreras, potencialmente sensibles. Las fuentes públicas (NYC TLC, MITMA) ya vienen agregadas o anonimizadas; en concreto, el MITMA elabora sus matrices a partir de datos de telefonía móvil **anonimizados**, en cumplimiento de la normativa de protección de datos.
- **Anonimización / agregación / filtrado.** La recogida de datos de la participante se realiza con **consentimiento informado** y conforme al **RGPD**: finalidad exclusivamente académica, **pseudonimización** y **no cesión** de datos individuales entre participantes. Los datos de demanda se trabajan **agregados** por zona y hora.
- **Uso seguro en contexto académico.** Sí: el modelo de consentimiento firmado y la pseudonimización permiten un uso seguro para un proyecto académico. El consentimiento informado se incluye como anexo del proyecto.
- **Riesgos éticos o legales.** Se contempla que una eventual adopción masiva de la herramienta por muchos conductores podría **saturar las zonas recomendadas** (efecto de conocimiento común); queda fuera del alcance pero se documenta.
- **Datos evitados por privacidad.** No se ceden ni publican datos individuales de carreras; solo se emplean de forma agregada o pseudonimizada.

---

## 5. Viabilidad inicial del proyecto

- **¿Es viable obtener los datos?** Sí. Las fuentes principales (NYC TLC, MITMA, Open-Meteo) son abiertas, gratuitas y no requieren permisos ni pagos. Los datos reales del taxista se obtienen con consentimiento de una participante ya comprometida con el proyecto.
- **¿Calidad, granularidad e histórico suficientes?** Sí para el entrenamiento: NYC TLC ofrece millones de registros con granularidad horaria y por zona, y un año completo de histórico. La movilidad local aporta la dimensión espacio-temporal de Terrassa, con la salvedad de ser un *proxy*.
- **¿Desarrollable de forma realista en el curso?** Sí: la comparativa de modelos, la validación de la transferencia (correlación horaria r = 0,88 entre NYC y Terrassa) y una aplicación desplegada (Streamlit) son alcanzables y, de hecho, ya se ha avanzado sustancialmente.
- **Parte más arriesgada.** La **transferencia NYC→Terrassa** y la dependencia de un *proxy* de movilidad general en lugar de demanda real de taxi; y, en segundo lugar, el **volumen reducido de datos locales** para la calibración fina.
- **Alternativa si la fuente principal falla.** Si NYC TLC dejara de ser accesible, existen conjuntos abiertos equivalentes de otras ciudades (p. ej. Chicago) con estructura análoga. Si la calibración local con MITMA resultara insuficiente, el sistema puede recalibrarse progresivamente con los datos reales acumulados del taxista, apoyándose en el paquete `spanishoddata` como vía alternativa de acceso a la movilidad española.

---

## Valoración de viabilidad

El proyecto es **viable**: las fuentes de datos son abiertas y accesibles, la granularidad e histórico son adecuados para el modelado, y el alcance (modelo + transferencia + producto desplegado) es realista para la duración del curso. El principal riesgo —el carácter de *proxy* de la movilidad local— está identificado y mitigado con una estrategia de recalibración basada en datos reales.
