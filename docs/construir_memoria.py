"""
Reconstruye la memoria del TFM a partir del original, conservando sus estilos
(Cambria, A4, márgenes) y añadiendo: abstract, índices, capítulo de análisis
exploratorio, figuras con pie numerado, tabla de hiperparámetros, importancia de
variables, las secciones de limitaciones que faltaban y los anexos.

    python docs/construir_memoria.py

Entrada:  docs/Memoria_TFM_Pau_Gavilan_original.docx
Salida:   docs/Memoria_TFM_Pau_Gavilan.docx
"""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figuras"
ORIGINAL = ROOT / "docs" / "Memoria_TFM_Pau_Gavilan_original.docx"
SALIDA = ROOT / "docs" / "Memoria_TFM_Pau_Gavilan.docx"

ANCHO = Inches(5.9)          # A4 con márgenes de 2,54 cm
GRIS = RGBColor(0x59, 0x59, 0x59)


# --------------------------------------------------------------------------
# Utilidades de campo de Word (índices y numeración automática de figuras)
# --------------------------------------------------------------------------
def _campo(parrafo, instruccion, marcador):
    """Inserta un campo de Word. Word lo calcula al abrir y pulsar F9."""
    r = parrafo.add_run()
    ini = OxmlElement("w:fldChar"); ini.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve")
    instr.text = instruccion
    sep = OxmlElement("w:fldChar"); sep.set(qn("w:fldCharType"), "separate")
    txt = OxmlElement("w:t"); txt.text = marcador
    fin = OxmlElement("w:fldChar"); fin.set(qn("w:fldCharType"), "end")
    for el in (ini, instr, sep, txt, fin):
        r._r.append(el)
    return parrafo


def indice(doc, instruccion, marcador):
    p = doc.add_paragraph()
    _campo(p, instruccion, marcador)
    return p


def figura(doc, archivo, pie, ancho=None):
    """Imagen centrada + pie 'Figura N. ...' con numeración automática (campo SEQ)."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True     # el pie nunca se separa de la imagen
    p.paragraph_format.space_before = Pt(10)
    p.add_run().add_picture(str(FIG / archivo), width=ancho or ANCHO)

    c = doc.add_paragraph()
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    try:
        c.style = doc.styles["Caption"]
    except KeyError:
        pass
    r = c.add_run("Figura ")
    r.font.size = Pt(9); r.font.color.rgb = GRIS; r.bold = True
    _campo(c, " SEQ Figura \\* ARABIC ", "1")
    r2 = c.add_run(". " + pie)
    r2.font.size = Pt(9); r2.font.color.rgb = GRIS
    for run in c.runs:
        run.font.size = Pt(9)


def pie_tabla(doc, texto):
    c = doc.add_paragraph()
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = c.add_run("Tabla ")
    r.font.size = Pt(9); r.font.color.rgb = GRIS; r.bold = True
    _campo(c, " SEQ Tabla \\* ARABIC ", "1")
    r2 = c.add_run(". " + texto)
    r2.font.size = Pt(9); r2.font.color.rgb = GRIS


def _bordes(t):
    """La plantilla solo trae 'Normal Table', que no pinta bordes: se añaden a mano."""
    pr = t._tbl.tblPr
    bordes = OxmlElement("w:tblBorders")
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement("w:" + lado)
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:color"), "BFBFBF")
        bordes.append(b)
    pr.append(bordes)


def _sombrear(celda, color="F2F2F2"):
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear")
    sh.set(qn("w:fill"), color)
    celda._tc.get_or_add_tcPr().append(sh)


def _repetir_cabecera(fila):
    """Si la tabla parte de página, Word repite la fila de cabecera."""
    pr = fila._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    pr.append(el)


def tabla(doc, cabecera, filas):
    t = doc.add_table(rows=1, cols=len(cabecera))
    t.style = "Normal Table"
    _bordes(t)
    _repetir_cabecera(t.rows[0])
    for i, h in enumerate(cabecera):
        celda = t.rows[0].cells[i]
        celda.text = ""
        celda.paragraphs[0].add_run(h).bold = True
        _sombrear(celda)
    for fila in filas:
        celdas = t.add_row().cells
        for i, v in enumerate(fila):
            celdas[i].text = str(v)
    doc.add_paragraph()
    return t


def salto(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# --------------------------------------------------------------------------
# Construcción
# --------------------------------------------------------------------------
doc = Document(str(ORIGINAL))
doc._body.clear_content()          # conserva estilos, fuentes y sectPr

# La plantilla no separa los párrafos ni airea los encabezados: sin esto, secciones
# como la de protección de datos se leen como un muro de texto.
pf = doc.styles["Normal"].paragraph_format
pf.space_after = Pt(8)
pf.line_spacing = 1.15
for nivel, antes, despues in [("Heading 1", 22, 10), ("Heading 2", 16, 6),
                              ("Heading 3", 12, 4)]:
    hpf = doc.styles[nivel].paragraph_format
    hpf.space_before = Pt(antes)
    hpf.space_after = Pt(despues)
    hpf.keep_with_next = True

P = doc.add_paragraph
H = doc.add_heading


def li(texto):
    """Punto de lista con la viñeta de la plantilla.

    El estilo 'List Paragraph' por sí solo no pinta viñeta: la lleva numbering.xml,
    que el original enlaza con numId 2. Al reconstruir el cuerpo hay que volver a
    enlazarlo o los puntos salen como párrafos sueltos.
    """
    p = doc.add_paragraph(texto, style="List Paragraph")
    numPr = p._p.get_or_add_pPr().get_or_add_numPr()
    numPr.get_or_add_ilvl().val = 0
    numPr.get_or_add_numId().val = 2
    return p


# ----------------------------- Portada -----------------------------
for texto, tam, negrita in [
    ("TRABAJO DE FIN DE MÁSTER", 14, True),
    ("Data Science & IA", 12, False),
    ("", 10, False),
    ("Sistema inteligente de predicción de demanda para taxistas autónomos", 20, True),
    ("Transferencia de modelos de Nueva York a Terrassa y producto funcional "
     "para un caso real", 13, False),
    ("", 10, False),
    ("Autor: Pau Gavilán", 12, False),
    ("2026", 12, False),
]:
    p = P()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(texto)
    r.font.size = Pt(tam)
    r.bold = negrita

salto(doc)

# ----------------------------- Resumen -----------------------------
H("Resumen", level=1)
P("Este trabajo desarrolla un sistema de predicción de demanda y apoyo a la decisión "
  "para taxistas autónomos, orientado a un caso de uso real en la ciudad de Terrassa. "
  "El problema central es la ausencia de datos públicos de viajes de taxi a nivel local: "
  "para resolverlo se entrena un modelo de predicción espacio-temporal sobre el conjunto "
  "de datos abierto de taxis de Nueva York (NYC TLC) y se transfiere a Terrassa apoyándose "
  "en las matrices de movilidad del Ministerio de Transportes y en datos reales registrados "
  "por una taxista en activo. La comparativa de modelos muestra que un modelo de gradient "
  "boosting (LightGBM) reduce el error porcentual (WAPE) del 28,5 % de un baseline ingenuo "
  "al 16,5 %, superando claramente a un modelo clásico de series temporales (Prophet). "
  "La transferencia se valida cuantitativamente: la forma horaria de la demanda presenta "
  "una correlación de 0,88 entre ambos contextos, lo que respalda la hipótesis de que el "
  "patrón temporal se transfiere mientras que la escala se recalibra con datos locales. "
  "El resultado se materializa en una aplicación funcional y desplegada que recomienda "
  "paradas, registra carreras mediante el reconocimiento de tickets por fotografía y "
  "muestra la rentabilidad real del usuario.")
p = P()
p.add_run("Palabras clave: ").bold = True
p.add_run("predicción de demanda, modelado espacio-temporal, transferencia de modelos, "
          "gradient boosting, movilidad urbana, taxi.")

H("Abstract", level=1)
P("This work develops a demand-forecasting and decision-support system for self-employed "
  "taxi drivers, applied to a real use case in the city of Terrassa (Spain). The core "
  "problem is the absence of public taxi-trip data at local level: to address it, a "
  "spatio-temporal forecasting model is trained on the open New York City taxi dataset "
  "(NYC TLC) and transferred to Terrassa using the mobility matrices published by the "
  "Spanish Ministry of Transport, together with real trip records logged by an active "
  "taxi driver. The model comparison shows that a gradient-boosting model (LightGBM) "
  "reduces the weighted absolute percentage error (WAPE) from 28.5 % for a naive baseline "
  "to 16.5 %, clearly outperforming a classical time-series model (Prophet). The transfer "
  "is validated quantitatively: the hourly shape of demand correlates at r = 0.88 between "
  "both contexts, supporting the hypothesis that the temporal pattern transfers while the "
  "scale must be recalibrated with local data. The outcome is a functional, deployed "
  "application that recommends taxi ranks, logs trips through photo-based ticket "
  "recognition and reports the driver's real profitability.")
p = P()
p.add_run("Keywords: ").bold = True
p.add_run("demand forecasting, spatio-temporal modelling, transfer learning, gradient "
          "boosting, urban mobility, taxi.")

salto(doc)

# ----------------------------- Índices -----------------------------
H("Índice", level=1)
indice(doc, ' TOC \\o "1-3" \\h \\z \\u ',
       "Sitúa el cursor aquí y pulsa F9 para generar el índice.")
salto(doc)

H("Índice de figuras", level=1)
indice(doc, ' TOC \\h \\z \\c "Figura" ',
       "Sitúa el cursor aquí y pulsa F9 para generar el índice de figuras.")

H("Índice de tablas", level=1)
indice(doc, ' TOC \\h \\z \\c "Tabla" ',
       "Sitúa el cursor aquí y pulsa F9 para generar el índice de tablas.")
salto(doc)

# ----------------------------- 1. Introducción -----------------------------
H("1    Introducción", level=1)
H("1.1    Motivación", level=2)
P("El sector del taxi tradicional afronta una competencia creciente por parte de las "
  "plataformas de vehículos con conductor, que disponen de sistemas sofisticados de "
  "predicción de demanda y asignación. Frente a ellas, el taxista autónomo opera en gran "
  "medida con intuición y experiencia, sin herramientas analíticas que le ayuden a decidir "
  "dónde y cuándo posicionarse. El presente trabajo nace de un caso concreto y cercano "
  "—una taxista autónoma en activo en Terrassa— con un objetivo doble: reducir el tiempo "
  "de circulación sin pasaje (kilómetros en vacío) y aportar al conductor información "
  "clara sobre su propia rentabilidad.")
P("La motivación no es únicamente técnica. Se busca construir un producto que una persona "
  "sin conocimientos de informática pueda utilizar en su día a día, lo que sitúa el foco "
  "tanto en la calidad de los modelos como en la experiencia de uso.")

H("1.2    Objetivos", level=2)
for o in [
    "Construir un modelo de predicción de demanda de taxi a nivel espacio-temporal "
    "(zona y franja horaria) y comparar de forma rigurosa distintas familias de modelos "
    "con métricas cuantitativas.",
    "Resolver la ausencia de datos locales mediante la transferencia de patrones desde un "
    "conjunto de datos abundante (Nueva York) al contexto de Terrassa, validando dicha "
    "transferencia con fuentes locales.",
    "Desarrollar un producto funcional y desplegado, usable por un conductor real, que "
    "recomiende dónde posicionarse y registre la actividad de forma sencilla.",
    "Establecer un mecanismo de captura de datos reales que permita validar y, en el "
    "futuro, calibrar localmente el sistema.",
]:
    li(o)

H("1.3    Alcance y estructura del documento", level=2)
P("El capítulo 2 sitúa el trabajo en su contexto. El capítulo 3 describe las fuentes de "
  "datos. El capítulo 4 presenta el análisis exploratorio de la demanda, que fundamenta "
  "las decisiones de modelado. El capítulo 5 detalla la metodología y la comparativa de "
  "modelos. El capítulo 6 aborda la transferencia de Nueva York a Terrassa, elemento "
  "diferenciador del proyecto. El capítulo 7 presenta el producto desarrollado y su "
  "arquitectura. El capítulo 8 recoge las conclusiones y las líneas de trabajo futuro.")
P("Conviene delimitar el alcance desde el principio, porque condiciona la lectura de todo "
  "el documento. El trabajo comprende dos mitades que no están todavía unidas. La primera "
  "es un modelo de demanda entrenado y evaluado sobre datos reales de Nueva York, con una "
  "comparativa cuantitativa de modelos. La segunda es un prototipo de producto desplegado "
  "y en uso para Terrassa, cuya recomendación se calcula hoy a partir del perfil de "
  "movilidad local y no de la inferencia del modelo entrenado. La unión efectiva de ambas "
  "—la transferencia operativa— requiere un volumen de datos locales que aún se está "
  "acumulando, y se documenta como línea futura en el apartado 8.3.")

# ----------------------------- 2. Contexto -----------------------------
H("2    Contexto y estado del arte", level=1)
H("2.1    Predicción de demanda espacio-temporal", level=2)
P("La predicción de demanda de movilidad es un área activa de investigación. El problema "
  "consiste en estimar el número de servicios que se originarán en cada zona geográfica y "
  "franja temporal, a partir de patrones históricos y de variables de contexto como el "
  "clima, los festivos o los eventos. Se trata de un problema de regresión con una fuerte "
  "componente estacional (diaria y semanal) y espacial.")
P("El estado del arte abarca desde modelos clásicos de series temporales hasta enfoques "
  "de aprendizaje profundo. En el extremo profundo, Zhang, Zheng y Qi (2017) proponen con "
  "ST-ResNet una red residual convolucional que predice los flujos de entrada y salida de "
  "personas por región urbana, y que se ha convertido en una referencia del área; sobre el "
  "propio conjunto de Nueva York existen numerosos trabajos posteriores de predicción de "
  "demanda de taxi y de vehículos de alquiler con conductor.")
P("Sin embargo, la superioridad del aprendizaje profundo en este tipo de problemas dista "
  "de estar asentada. Elsayed et al. (2021) comparan ocho modelos profundos del estado del "
  "arte con un árbol de decisión potenciado por gradiente sobre nueve conjuntos de datos, "
  "y concluyen que este último los supera a todos cuando la entrada se transforma mediante "
  "ventanas temporales. En la misma línea, Grinsztajn, Oyallon y Varoquaux (2022) muestran "
  "que los modelos basados en árboles siguen siendo el estado del arte sobre datos "
  "tabulares de tamaño medio, y atribuyen la diferencia a dos sesgos inductivos: los "
  "árboles aprenden mejor funciones objetivo irregulares y se ven menos perjudicados por "
  "las variables poco informativas. Ambos resultados son directamente pertinentes aquí, "
  "porque el problema que se aborda, una vez construidas las variables de retardo, es "
  "tabular y de tamaño medio.")

H("2.2    El conjunto de datos de Nueva York y la ausencia de datos locales", level=2)
P("La Taxi and Limousine Commission de Nueva York (NYC TLC) publica de forma abierta los "
  "registros de viajes de taxi, con millones de servicios documentados por mes e "
  "identificados por zona de recogida. Esta abundancia contrasta con la situación local: "
  "no existe un conjunto público equivalente de viajes de taxi en Terrassa ni en Barcelona. "
  "Los portales de datos abiertos solo ofrecen paradas estáticas y agregados del sector, "
  "no viajes individuales. Esta carencia es precisamente el reto metodológico que "
  "estructura el proyecto.")

H("2.3    Transferencia de modelos entre contextos", level=2)
P("Cuando un modelo se entrena con datos de un contexto y se aplica a otro distinto, su "
  "rendimiento no está garantizado: un modelo entrenado con datos de Manhattan no predice "
  "directamente la demanda de una ciudad media como Terrassa. La estrategia adoptada "
  "distingue entre lo que se transfiere —la forma de los patrones temporales— y lo que "
  "debe recalibrarse —la escala y la geografía locales—, apoyándose en fuentes de "
  "movilidad locales para la recalibración.")
P("El problema tiene nombre propio en la literatura: la transferencia entre ciudades "
  "(cross-city transfer learning) se ha consolidado como respuesta a la escasez de datos "
  "en la ciudad de destino, extrayendo conocimiento de ciudades con datos abundantes para "
  "predecir en las que carecen de ellos. Es exactamente la situación de este trabajo, con "
  "la diferencia de que aquí la transferencia no se plantea sobre los pesos de una red "
  "neuronal sino sobre la forma agregada del patrón temporal: un enfoque más modesto, pero "
  "verificable con las fuentes disponibles.")

# ----------------------------- 3. Datos -----------------------------
H("3    Datos", level=1)
H("3.1    Datos de taxi de Nueva York (NYC TLC)", level=2)
P("Se utilizan los registros de Yellow Taxi de 2023 en formato Parquet. A partir de los "
  "viajes individuales se construye una tabla de demanda agregada por zona de recogida, "
  "fecha y hora. Un aspecto metodológico clave es el relleno de ceros: toda combinación de "
  "zona y hora sin viajes se representa explícitamente como demanda cero, no como dato "
  "ausente; de lo contrario el modelo no aprendería cuándo la demanda es nula. La rejilla "
  "resultante contiene 2.303.880 filas (zona × fecha × hora), procedentes de 38,3 millones "
  "de viajes repartidos en 263 zonas.")
P("La agregación se resuelve con DuckDB, lo que permite recorrer los doce ficheros "
  "mensuales —unos 620 MB en total— y construir la rejilla completa sin cargar los viajes "
  "individuales en memoria.")

H("3.2    Movilidad local: estudio de movilidad del MITMA", level=2)
P("Como aproximación a la demanda local se emplea el Estudio de la movilidad con Big Data "
  "del Ministerio de Transportes y Movilidad Sostenible, que ofrece matrices origen-destino "
  "por hora y distrito censal a partir de datos anonimizados de telefonía móvil, en "
  "cumplimiento de la normativa de protección de datos. Se extrae una muestra "
  "representativa (una semana por trimestre de 2023) para los siete distritos de Terrassa. "
  "Conviene subrayar que esta fuente mide movilidad general, no demanda de taxi: actúa "
  "como proxy, una limitación que se documenta de forma explícita.")

H("3.3    Variables externas", level=2)
P("El calendario de festivos se incorpora como variable del modelo, por su influencia "
  "conocida sobre la demanda de movilidad, y también condiciona la recomendación de la "
  "aplicación, que trata un festivo con el patrón de un domingo.")
P("Las condiciones meteorológicas se obtienen en tiempo real de la API de Open-Meteo, "
  "pero conviene precisar su papel: se muestran al conductor como información de "
  "contexto —un aviso cuando está lloviendo, situación en la que suele haber más "
  "servicios— y no entran como variable en el modelo. Incorporarlas exigiría el "
  "histórico meteorológico horario de Nueva York alineado con la rejilla de demanda, "
  "que queda como línea futura.")

H("3.4    Datos reales del taxista", level=2)
P("La validación final y el caso de uso se apoyan en los datos reales de carreras de una "
  "taxista de Terrassa (cooperativa Tele-Taxi Egara). Cada ticket aporta fecha, horas de "
  "inicio y fin, direcciones de origen y destino, distancia, importe y tipo de servicio. "
  "Estos datos se capturan mediante el reconocimiento automático de la fotografía del "
  "ticket, descrito en el capítulo 7.")

H("3.5    Protección de datos y consideraciones éticas", level=2)
P("El tratamiento de datos personales de este trabajo se limita a los registros de "
  "carreras aportados voluntariamente por una única conductora, y se realiza conforme al "
  "Reglamento (UE) 2016/679 (RGPD) y a la Ley Orgánica 3/2018.")
P("La base legal es el consentimiento explícito e informado de la interesada, recogido por "
  "escrito antes del inicio de la recogida (anexo A). La finalidad es exclusivamente "
  "académica: el desarrollo y la evaluación de este Trabajo de Fin de Máster. El "
  "consentimiento es revocable en cualquier momento, sin necesidad de justificación y con "
  "supresión de los datos ya recogidos.")
P("En cuanto a la minimización, el registro no recoge ningún dato identificativo de los "
  "clientes: ni nombre, ni teléfono, ni matrícula, ni forma de pago nominativa. Sí recoge, "
  "en cambio, direcciones de origen y destino de los servicios, que constituyen un dato "
  "personal indirecto en la medida en que podrían contribuir a identificar a un tercero. "
  "Por ese motivo las direcciones no se publican, no se incluyen en los anexos y no salen "
  "del entorno de trabajo del autor; los análisis que aparecen en la memoria se realizan "
  "siempre sobre agregados.")
P("El punto que requiere mayor cautela es el reconocimiento automático de tickets descrito "
  "en el apartado 7.4. La fotografía del ticket se envía a la API de Gemini (Google), que "
  "actúa por tanto como encargado del tratamiento y que implica una transferencia "
  "internacional de datos. La conductora fue informada expresamente de esta circunstancia "
  "antes de aceptar el uso de la herramienta. Los datos extraídos se almacenan en una hoja "
  "de cálculo de acceso restringido, y las credenciales de acceso se mantienen fuera del "
  "control de versiones del proyecto. Una versión de producción del sistema debería "
  "sustituir este componente por un reconocimiento óptico ejecutado en local, lo que "
  "eliminaría por completo la transferencia a un tercero; se recoge como línea futura.")
P("Finalmente, el conjunto de datos de Nueva York es de publicación abierta y ya se "
  "distribuye agregado y sin identificadores personales, y las matrices del MITMA se "
  "publican anonimizadas y agregadas por el propio Ministerio, de modo que ninguna de las "
  "dos fuentes plantea un tratamiento adicional.")

# ----------------------------- 4. EDA (NUEVO) -----------------------------
H("4    Análisis exploratorio de la demanda", level=1)
P("Antes de modelar conviene entender la estructura de los datos, porque son sus "
  "propiedades —y no una preferencia a priori— las que justifican las decisiones "
  "metodológicas del capítulo 5: qué variables construir, qué métrica usar y qué función "
  "objetivo resulta apropiada. Este capítulo recorre la rejilla de demanda de Nueva York "
  "descrita en el apartado 3.1.")

H("4.1    Dispersión: la demanda es mayoritariamente cero", level=2)
P("El primer hecho relevante es la dispersión de la matriz. De los 2.303.880 pares "
  "zona-hora del año, el 61,5 % registra cero recogidas. La mediana de la demanda es 0 y "
  "la media 16,6, lo que refleja una distribución fuertemente asimétrica: unas pocas zonas "
  "concentran volúmenes muy altos mientras la mayoría permanece inactiva buena parte del "
  "día.")
figura(doc, "fig07_distribucion_demanda.png",
       "Distribución de la demanda por zona-hora, recortada al percentil 99. El 61,5 % de "
       "las celdas de la rejilla registra cero recogidas.")
P("Esta observación tiene dos consecuencias directas sobre el modelado. La primera afecta "
  "a la métrica: el error porcentual absoluto medio (MAPE) exige dividir por el valor "
  "real, de modo que con una mayoría de ceros se vuelve indefinido o desproporcionado; se "
  "adopta en su lugar el WAPE, que pondera por el volumen total y es estable ante ceros. "
  "La segunda afecta a la función objetivo: se trata de un problema de conteo, no negativo "
  "y con exceso de ceros, para el que un objetivo de tipo Poisson resulta más adecuado que "
  "el error cuadrático habitual.")

H("4.2    El ritmo diario", level=2)
P("La señal temporal más fuerte es la hora del día. La curva presenta un valle profundo "
  "entre las tres y las cinco de la madrugada, un ascenso sostenido durante la mañana y un "
  "máximo claro en la franja vespertina, alrededor de las seis de la tarde.")
figura(doc, "fig01_demanda_por_hora.png",
       "Demanda media por hora del día. El valle nocturno y el pico vespertino son la "
       "señal temporal dominante.")
P("Que la hora sea la variable más informativa justifica su codificación cíclica mediante "
  "seno y coseno, que se describe en el apartado 5.2: sin ella, un modelo trataría las "
  "23:00 y las 00:00 como valores extremos y distantes, cuando en realidad son contiguas.")

H("4.3    El ritmo semanal", level=2)
P("El día de la semana introduce una segunda estacionalidad, de menor amplitud pero "
  "sistemática. La actividad crece de forma progresiva a lo largo de la semana laboral y "
  "alcanza su máximo el viernes y el sábado.")
figura(doc, "fig02_demanda_por_dia.png", "Demanda media por día de la semana.")
P("Más informativo que el nivel medio es el cambio de forma. Al separar los días "
  "laborables de los fines de semana, las dos curvas horarias no se diferencian por una "
  "simple traslación vertical: el fin de semana desplaza actividad desde la hora punta de "
  "la mañana hacia la madrugada, lo que refleja un uso de ocio frente a un uso de "
  "desplazamiento al trabajo. Este cambio de forma —y no solo de escala— es lo que "
  "justifica incorporar un indicador de fin de semana como variable del modelo.")
figura(doc, "fig06_laborable_vs_finde.png",
       "Curva horaria en días laborables frente a fines de semana. El fin de semana no "
       "desplaza la curva: le cambia la forma.")
P("La interacción conjunta de ambas estacionalidades se aprecia mejor en el mapa de calor "
  "de hora por día de la semana, donde se distinguen con nitidez la hora punta laborable y "
  "la actividad nocturna del viernes y el sábado.")
figura(doc, "fig03_heatmap_hora_dia.png",
       "Demanda media cruzando hora del día y día de la semana.")

H("4.4    La dimensión espacial", level=2)
P("La demanda se concentra de forma muy desigual en el territorio. Las quince zonas más "
  "activas acumulan una fracción desproporcionada del total anual, encabezadas por los "
  "distritos centrales de Manhattan y los aeropuertos.")
figura(doc, "fig04_top_zonas.png",
       "Quince zonas con mayor demanda acumulada en 2023.")
P("Ahora bien, el dato verdaderamente relevante para el producto no es qué zona acumula "
  "más demanda, sino que cada zona tiene su propio perfil horario. Los aeropuertos "
  "presentan picos ligados a las oleadas de llegadas; las zonas de oficinas se activan en "
  "las horas punta laborables; las zonas de ocio nocturno concentran su actividad de "
  "madrugada. Esta heterogeneidad espacio-temporal es exactamente la información que un "
  "sistema de recomendación debe explotar: no basta con saber cuándo hay demanda, hay que "
  "saber dónde a cada hora.")
figura(doc, "fig05_heatmap_zona_hora.png",
       "Demanda media por zona (quince principales) y hora del día. Cada zona tiene su "
       "propia hora punta.")

H("4.5    Estabilidad a lo largo del año", level=2)
P("La serie diaria agregada se mantiene razonablemente estable durante 2023, sin "
  "tendencia marcada, con una estacionalidad semanal visible y con caídas puntuales "
  "coincidentes con festivos y episodios meteorológicos adversos. La ausencia de una "
  "tendencia fuerte respalda el uso de un único año de datos y la validez de una partición "
  "temporal en la que los dos últimos meses actúan como conjunto de prueba.")
figura(doc, "fig08_serie_anual.png",
       "Demanda diaria total agregada de Nueva York durante 2023.")

H("4.6    Síntesis", level=2)
P("El análisis exploratorio deja cuatro conclusiones que condicionan el capítulo "
  "siguiente: la matriz es dispersa y obliga a elegir métrica y función objetivo con "
  "cuidado; la hora del día es la señal dominante y debe codificarse de forma cíclica; el "
  "día de la semana modifica la forma de la curva y no solo su nivel; y el comportamiento "
  "es fuertemente heterogéneo entre zonas, lo que exige un modelo capaz de aprender "
  "patrones distintos por zona en lugar de una curva única para toda la ciudad.")

# ----------------------------- 5. Metodología -----------------------------
H("5    Metodología y modelado", level=1)
H("5.1    Definición del problema", level=2)
P("El objetivo de predicción no es un viaje aislado, sino el número de recogidas esperadas "
  "en cada par (zona, franja horaria). Se adopta una resolución horaria y la zonificación "
  "nativa del conjunto de Nueva York, trasladable conceptualmente a los distritos de "
  "Terrassa.")

H("5.2    Ingeniería de variables", level=2)
P("A partir de la tabla de demanda se construyen variables de calendario (hora, día de la "
  "semana, mes, indicador de fin de semana y de festivo), la codificación cíclica de la "
  "hora justificada en el apartado 4.2 y, sobre todo, variables de retardo (lags): la "
  "demanda de la misma zona una hora antes, veinticuatro horas antes y una semana antes "
  "(168 horas), junto con medias móviles de veinticuatro horas y de una semana. Estas "
  "variables de retardo capturan la fuerte autocorrelación temporal de la demanda. El "
  "conjunto final consta de catorce variables.")

H("5.3    Horizonte de predicción", level=2)
P("Es necesario precisar el horizonte al que se evalúa el modelo, porque condiciona la "
  "interpretación de las métricas. Al incluir la demanda de la hora anterior entre las "
  "variables, el modelo se evalúa a un horizonte de una hora, disponiendo del valor real "
  "ya observado en el instante inmediatamente anterior. Es lo que en la literatura se "
  "denomina predicción a un paso.")
P("Este planteamiento es coherente con el caso de uso —el conductor decide dónde "
  "posicionarse en la próxima hora, no la próxima semana— y con la disponibilidad de datos "
  "en un sistema en explotación, donde el histórico reciente se conoce. Pero conviene "
  "señalar sus límites: a horizontes mayores la variable de retardo de una hora deja de "
  "estar disponible y debería sustituirse por la propia predicción del modelo, lo que "
  "acumula error. Una evaluación a veinticuatro horas prescindiendo de esa variable "
  "arrojaría métricas necesariamente peores y queda planteada como trabajo futuro. Las "
  "cifras que se presentan a continuación deben leerse, por tanto, como el rendimiento a "
  "una hora vista, no como una capacidad predictiva a largo plazo.")

H("5.4    Validación temporal y métricas", level=2)
P("La evaluación se realiza con una partición temporal —no aleatoria—: se entrena con los "
  "meses de enero a octubre y se valida con noviembre y diciembre. Mezclar las "
  "observaciones al azar permitiría al modelo «ver el futuro» y produciría métricas "
  "falsamente optimistas. Se reportan el error absoluto medio (MAE), la raíz del error "
  "cuadrático medio (RMSE) y el error porcentual ponderado (WAPE). Se descarta "
  "deliberadamente el MAPE porque, con numerosas celdas de demanda cero, su cálculo se "
  "vuelve inestable.")
P("La partición emplea un único corte temporal. Un esquema de validación cruzada de origen "
  "móvil, con varios cortes sucesivos, permitiría acompañar las métricas de un intervalo "
  "de confianza y descartar que los resultados dependan del bimestre concreto elegido. No "
  "se ha implementado por coste de cómputo y se recoge como limitación.")

H("5.5    Modelo de referencia (baseline)", level=2)
P("Como referencia se emplea un predictor ingenuo: la demanda de una zona y hora es igual "
  "a la de esa misma hora la semana anterior. Todo modelo debe superar este baseline para "
  "justificar su utilidad.")

H("5.6    Comparativa de modelos", level=2)
P("Se comparan tres familias: un modelo clásico de series temporales (Prophet), un modelo "
  "de gradient boosting (LightGBM, con objetivo de tipo Poisson, apropiado para conteos) y "
  "una red neuronal recurrente (LSTM). La tabla 1 recoge los resultados sobre el conjunto "
  "de prueba completo; la tabla 2 compara de forma equitativa los modelos sobre la muestra "
  "de las treinta zonas de mayor demanda, escala a la que es viable ajustar Prophet.")
tabla(doc, ["Modelo", "MAE", "RMSE", "WAPE"],
      [["Baseline (misma hora, semana anterior)", "4,98", "18,85", "28,5 %"],
       ["LightGBM (objetivo Poisson)", "2,87", "9,57", "16,5 %"]])
pie_tabla(doc, "Resultados sobre todas las zonas (conjunto de prueba, noviembre–diciembre).")
tabla(doc, ["Modelo", "MAE", "RMSE", "WAPE"],
      [["Baseline (muestra)", "31,21", "52,70", "25,2 %"],
       ["LightGBM (muestra)", "16,95", "26,58", "13,7 %"],
       ["Prophet (muestra)", "42,77", "63,23", "34,5 %"]])
pie_tabla(doc, "Comparación equitativa sobre la muestra de las 30 zonas de mayor demanda.")
P("Los hiperparámetros de LightGBM se fijaron a valores habituales para problemas de "
  "conteo de este tamaño, sin una búsqueda sistemática; la tabla 3 los recoge para "
  "garantizar la reproducibilidad del resultado.")
tabla(doc, ["Hiperparámetro", "Valor", "Motivo"],
      [["objective", "poisson", "Conteos no negativos con exceso de ceros"],
       ["n_estimators", "500", "Suficiente sin sobreajustar con la tasa elegida"],
       ["learning_rate", "0,05", "Tasa conservadora, compensada con más árboles"],
       ["num_leaves", "63", "Capacidad media; limita el sobreajuste por zona"],
       ["min_child_samples", "50", "Evita hojas sostenidas por muy pocas observaciones"],
       ["subsample", "0,8", "Submuestreo de filas para reducir varianza"],
       ["colsample_bytree", "0,8", "Submuestreo de variables por árbol"],
       ["random_state", "42", "Reproducibilidad"]])
pie_tabla(doc, "Hiperparámetros del modelo LightGBM de producción.")
P("La red recurrente se evalúa sobre una muestra de veinte zonas —las de mayor demanda—, "
  "tamaño al que resulta viable construir las secuencias deslizantes de 168 horas que "
  "consume. Para que la comparación sea equitativa, LightGBM se reentrena sobre esas "
  "mismas zonas y el baseline se recalcula sobre las mismas filas. La tabla 4 recoge el "
  "resultado.")
tabla(doc, ["Modelo", "MAE", "RMSE", "WAPE"],
      [["Baseline (muestra de 20 zonas)", "36,30", "60,35", "24,8 %"],
       ["LightGBM (muestra de 20 zonas)", "18,85", "28,95", "12,9 %"],
       ["LSTM (muestra de 20 zonas)", "23,07", "35,33", "15,7 %"]])
pie_tabla(doc, "Comparación sobre la muestra de las 20 zonas de mayor demanda, escala a la "
               "que es viable entrenar la red recurrente.")
P("Este experimento exige un entorno con Python 3.12: TensorFlow no publica "
  "distribuciones para la versión 3.14 empleada inicialmente en el desarrollo, mientras "
  "que el resto de dependencias del proyecto resuelve a versiones idénticas en ambas. Se "
  "comprobó que la migración no altera ninguna de las métricas anteriores.")

H("5.7    Discusión de resultados", level=2)
P("LightGBM es el ganador con claridad: reduce el WAPE del 28,5 % del baseline al 16,5 %, "
  "casi a la mitad el MAE y a la mitad el RMSE. La fuerte caída del RMSE indica que el "
  "modelo acierta especialmente en los picos de demanda, donde el baseline falla y donde "
  "reside el valor para el usuario.")
P("Un resultado igualmente informativo es que Prophet no supera siquiera al baseline en la "
  "muestra (34,5 % frente a 25,2 %). La razón es estructural y conviene explicitarla para "
  "no atribuir al modelo una debilidad que en realidad es de configuración: Prophet ajusta "
  "cada zona de forma aislada y, tal como se ha empleado aquí, no recibe ninguna variable "
  "exógena, mientras que LightGBM dispone de las variables de retardo y de la información "
  "cruzada entre zonas. La comparación no enfrenta, por tanto, dos modelos con la misma "
  "información de entrada; lo que demuestra es que, para este problema, la capacidad de "
  "explotar retardos y relaciones entre zonas pesa más que el modelado explícito de la "
  "estacionalidad. Ese hallazgo es precisamente lo que justifica la elección de LightGBM "
  "como modelo de producción.")
P("La red recurrente supera con holgura al baseline (15,7 % frente a 24,8 %) pero no "
  "alcanza a LightGBM (12,9 %). Conviene precisar que esa cifra debe leerse como un suelo "
  "y no como un techo: la red recibe las mismas variables por paso temporal para todas "
  "las zonas, sin ningún identificador de zona ni representación embebida que le permita "
  "distinguirlas, y sin normalizar las entradas. Una arquitectura que incorporase ambas "
  "cosas partiría en mejores condiciones. Aun así el resultado es informativo: a un coste "
  "de entrenamiento muy superior —minutos frente a segundos— la red no aporta ventaja "
  "sobre el gradient boosting en este problema, lo que refuerza la elección de LightGBM "
  "como modelo de producción.")
P("El análisis de importancia de variables confirma esta lectura y añade un matiz. La "
  "variable con mayor número de divisiones es la zona, seguida de la hora del día y del "
  "retardo semanal.")
figura(doc, "fig13_importancia_variables.png",
       "Importancia de variables de LightGBM, medida como número de divisiones del árbol "
       "en que interviene cada una.")
P("Conviene interpretar esta figura con cautela: la importancia por número de divisiones "
  "favorece de forma conocida a las variables categóricas de alta cardinalidad, y la zona "
  "toma 263 valores distintos, de modo que su primer puesto está en parte inducido por la "
  "propia métrica. Descontado ese efecto, la lectura es coherente con el análisis "
  "exploratorio del capítulo 4: la hora del día y el retardo de una semana son las dos "
  "señales temporales dominantes, seguidas de los retardos de una hora y de un día. Las "
  "variables de calendario de grano grueso —mes, día del mes y festivo— aportan poco, lo "
  "que resulta esperable en una serie sin tendencia anual marcada.")

# ----------------------------- 6. Transferencia -----------------------------
H("6    Transferencia de Nueva York a Terrassa", level=1)
H("6.1    Hipótesis", level=2)
P("La hipótesis de transferencia sostiene que la forma de la demanda —su ritmo a lo largo "
  "del día y de la semana— es un comportamiento de movilidad razonablemente común entre "
  "ciudades, mientras que la escala absoluta y la geografía son específicas de cada lugar. "
  "En consecuencia, el patrón aprendido en Nueva York puede transferirse a Terrassa, "
  "recalibrando la escala con fuentes locales.")

H("6.2    Perfil de movilidad de Terrassa", level=2)
P("A partir de las matrices del MITMA se construye un perfil local de movilidad: viajes "
  "por distrito, hora y día de la semana para los siete distritos de Terrassa. Este perfil "
  "aporta la dimensión espacial y temporal propia de la ciudad.")
figura(doc, "fig09_terrassa_distrito_hora.png",
       "Movilidad media de Terrassa por distrito y hora del día (fuente: MITMA).")
figura(doc, "fig10_terrassa_hora_dia.png",
       "Perfiles horario y semanal agregados de la movilidad de Terrassa.")

H("6.3    Comparación de patrones", level=2)
P("Comparando los perfiles temporales normalizados de ambos contextos, la forma horaria "
  "presenta una correlación muy alta (r = 0,88): el valle de madrugada, la actividad "
  "sostenida durante el día y el pico vespertino son esencialmente comunes.")
figura(doc, "fig11_forma_horaria_nyc_terrassa.png",
       "Forma horaria normalizada de ambos contextos. La correlación de 0,88 sostiene la "
       "hipótesis de transferencia del patrón temporal.")
P("La superposición revela además dos diferencias sistemáticas que la correlación por sí "
  "sola no muestra y que conviene señalar. La primera es que Terrassa arranca antes y de "
  "forma más abrupta: entre las seis y las ocho de la mañana la actividad local se dispara "
  "mientras la de Nueva York asciende con suavidad, un reflejo del peso del desplazamiento "
  "al trabajo en una ciudad media con fuerte movilidad de entrada y salida. La segunda es "
  "que Nueva York mantiene una cola nocturna notablemente más alta, coherente con un "
  "servicio de taxi en una ciudad de actividad continua frente a la movilidad general de "
  "una ciudad de tamaño medio. Ambas diferencias apuntan a los tramos horarios donde una "
  "recalibración local sería más necesaria.")
P("La forma semanal muestra una correlación también alta, aunque menor (r = 0,73), "
  "coherente con las diferencias estructurales entre un servicio de taxi —con mayor peso "
  "de la noche de fin de semana— y la movilidad general de una ciudad media.")
figura(doc, "fig12_forma_semanal_nyc_terrassa.png",
       "Forma semanal normalizada de ambos contextos.")
P("Estos resultados respaldan la estrategia adoptada: el patrón temporal se transfiere, la "
  "escala se recalibra.")

H("6.4    Limitaciones de la fuente local", level=2)
P("La principal limitación es que la fuente local mide movilidad general y no demanda de "
  "taxi, por lo que actúa como proxy. La calibración fina, zona a zona, requerirá un "
  "volumen suficiente de datos reales del taxista, que se acumulan de forma continua a "
  "través de la aplicación.")

H("6.5    Limitaciones de resolución espacial", level=2)
P("Existe una segunda limitación, de naturaleza distinta y con consecuencias directas "
  "sobre la calidad de la recomendación, que merece cuantificarse antes que enunciarse.")
P("El perfil local tiene resolución de distrito y Terrassa se divide en siete, mientras "
  "que la ciudad cuenta con catorce paradas de taxi. Varias paradas caen necesariamente "
  "dentro del mismo distrito y comparten, por construcción, un valor de demanda idéntico: "
  "cuatro de ellas se sitúan en el distrito 01. El sistema puede por tanto ordenar "
  "distritos, pero no discriminar entre paradas de un mismo distrito.")
P("Al descomponer la varianza del perfil de movilidad se obtiene que el distrito explica "
  "el 36,3 % de la variación, frente al 53,3 % que explica la combinación de hora y día "
  "de la semana. Dicho de otro modo, la componente temporal del perfil es más informativa "
  "que la espacial. A ello se añade que la señal espacial está en buena medida determinada "
  "por el tamaño de la población: la correlación entre los viajes totales de cada distrito "
  "y su número de habitantes es de 0,885, de manera que el ranking espacial reproduce en "
  "gran parte la distribución de población y no una intensidad de demanda de taxi por "
  "habitante.")
P("La consecuencia práctica es que la recomendación espacial actual es de grano grueso y "
  "está sesgada hacia los distritos más poblados. Superarla no requiere más datos de la "
  "misma fuente, sino una fuente de mayor resolución o una ponderación de cada parada por "
  "sus atractores de demanda —estaciones, hospitales, zonas de ocio—, línea que se recoge "
  "en el apartado 8.3.")

# ----------------------------- 7. Producto -----------------------------
H("7    Producto: la aplicación", level=1)
H("7.1    Definición del producto y del usuario", level=2)
P("El producto responde a una pregunta concreta del taxista autónomo: «¿dónde y cuándo me "
  "coloco para ganar más sin dar vueltas en vacío?». El usuario final no tiene "
  "conocimientos técnicos, lo que condiciona el diseño hacia una interfaz simple, pensada "
  "para un vistazo rápido y para su uso desde el teléfono móvil.")

H("7.2    Arquitectura", level=2)
P("El sistema se organiza en capas: adquisición de datos (NYC TLC, MITMA, Open-Meteo y "
  "registro del taxista), preprocesado, almacenamiento, modelado y, finalmente, la capa de "
  "presentación o inteligencia de negocio (BI), que es la única que ve el usuario. Esta "
  "separación garantiza que el dato crudo nunca se altera y que la complejidad técnica "
  "permanece oculta tras una interfaz sencilla.")
P("El almacenamiento sigue una organización por capas de refinamiento: los ficheros "
  "originales descargados se conservan intactos, una segunda capa guarda la tabla de "
  "demanda agregada y una tercera la tabla de variables lista para el entrenamiento. "
  "Cualquiera de las dos últimas puede regenerarse por completo a partir de la primera "
  "ejecutando el proceso documentado en el repositorio.")

H("7.3    Alcance real de la integración", level=2)
P("Este apartado precisa qué parte del sistema descrito está efectivamente conectada, "
  "para evitar una lectura más optimista de la que corresponde.")
P("El modelo de demanda del capítulo 5 está entrenado y evaluado sobre datos de Nueva "
  "York, pero no alimenta todavía la recomendación que muestra la aplicación. Lo que el "
  "modo Conductor calcula hoy es un índice de demanda derivado del perfil de movilidad "
  "local del MITMA, cruzado con la ubicación de las paradas: es decir, una consulta sobre "
  "el perfil local, no una inferencia del modelo entrenado.")
P("La razón es la expuesta en los apartados 6.4 y 6.5: unir ambas mitades exige recalibrar "
  "la escala y la geografía con datos locales de demanda de taxi, y el volumen acumulado "
  "por el sistema de captura es todavía insuficiente para hacerlo con garantías. Se ha "
  "preferido dejar la transferencia operativa como línea futura documentada antes que "
  "cerrar el circuito con una calibración no validada, que produciría recomendaciones de "
  "fiabilidad desconocida presentadas al usuario con apariencia de predicción.")
P("El trabajo entrega por tanto dos resultados verificables por separado —un modelo de "
  "demanda evaluado cuantitativamente y un producto desplegado y en uso— junto con la "
  "evidencia cuantitativa (capítulo 6) de que la unión entre ambos es plausible.")

H("7.4    Funcionalidades", level=2)
P("La aplicación, desarrollada con Streamlit, integra tres modos en una sola interfaz:")
for f in [
    "Conductor: recomienda la parada a la que dirigirse en cada momento y muestra un mapa "
    "interactivo de Terrassa con la demanda por zonas, expresada en niveles (alta, media, "
    "baja) en lugar de cifras, para no transmitir una precisión que el dato no tiene. "
    "Incorpora las catorce paradas de taxi reales de la ciudad, y contempla los festivos "
    "y la lluvia como factores de contexto.",
    "Registrar: permite fotografiar el ticket de una carrera; un modelo de visión extrae "
    "automáticamente los datos, que el usuario revisa antes de guardarlos.",
    "Análisis: muestra los patrones de demanda, la comparación de la transferencia y la "
    "rentabilidad real del conductor, leída en directo del registro de carreras.",
]:
    li(f)
P("El modo Análisis incorpora además tres bloques que explotan el registro real de "
  "carreras. El primero son las métricas de rentabilidad: además de los euros por "
  "kilómetro se calcula el euro por hora de turno, que es la magnitud que un conductor "
  "optimiza en la práctica —el euro por kilómetro premia las carreras largas y lentas—. "
  "El segundo es el tiempo en vacío, medido como el hueco entre el final de una carrera "
  "y el inicio de la siguiente, descartando los huecos superiores a noventa minutos, que "
  "corresponden a descansos o a fin de turno y no a circulación sin pasaje; se desglosa "
  "por hora del día y por zona de destino, lo que responde directamente al objetivo "
  "planteado en el apartado 1.2. El tercero se describe a continuación.")
P("Los niveles de demanda se asignan por terciles sobre los valores presentes en cada "
  "momento, y no mediante umbrales fijos. La razón es consecuencia directa de la "
  "limitación descrita en el apartado 6.5: con umbrales fijos sobre el máximo, ninguna "
  "parada alcanzaba nunca el nivel bajo, porque el único distrito de actividad reducida no "
  "contiene ninguna parada de taxi. El criterio por terciles se aplica sobre los valores "
  "distintos, de modo que dos paradas del mismo distrito reciben siempre la misma "
  "etiqueta.")

H("7.5    Evaluación del recomendador", level=2)
P("Un sistema que recomienda debe poder decir si acierta. La aplicación incorpora esa "
  "evaluación de forma continua, aprovechando que el propio registro de carreras "
  "proporciona la verdad de campo: para cada carrera realizada se reconstruye el ranking "
  "que el sistema habría mostrado ese día y a esa hora, y se comprueba si la parada donde "
  "la conductora recogió efectivamente figuraba entre las tres primeras.")
P("La métrica es la tasa de acierto en las k primeras posiciones, habitual en la "
  "evaluación de sistemas de recomendación, y se contrasta con la referencia del azar: "
  "con catorce paradas y k igual a tres, un sistema que recomendase aleatoriamente "
  "acertaría el 21 % de las veces. Superar ese umbral es la condición mínima para "
  "afirmar que la recomendación aporta información.")
P("Dos precisiones metodológicas. La primera es que el ranking usado en la evaluación se "
  "calcula con la misma función que alimenta la vista del conductor: si cada una "
  "calculase el suyo, la evaluación estaría midiendo un sistema distinto del que ve la "
  "usuaria. La segunda es que los tickets registran la dirección de recogida en texto "
  "libre y no el nombre de una parada, de modo que hace falta un emparejamiento "
  "aproximado; las carreras que no pueden asociarse con seguridad a ninguna parada se "
  "excluyen del cálculo y la proporción de carreras emparejadas se muestra junto a la "
  "métrica, para que el lector pueda juzgar su cobertura.")
P("En el momento de redactar esta memoria el volumen de carreras registradas es todavía "
  "insuficiente para que el resultado sea concluyente. La instrumentación, sin embargo, "
  "queda operativa y produce el dato de forma automática conforme el registro crece: es "
  "la vía por la que este trabajo podrá pasar de un sistema construido a un sistema "
  "evaluado.")

H("7.6    Captura de datos por fotografía", level=2)
P("Para minimizar la fricción del registro —principal riesgo para la continuidad de la "
  "recogida de datos— la aplicación incorpora un lector de tickets. La fotografía se "
  "procesa con un modelo de visión (Gemini), que devuelve los campos estructurados; el "
  "usuario los confirma o corrige, manteniendo a la persona en el bucle, y se almacenan en "
  "una hoja de cálculo en la nube (Google Sheets). De este modo, los datos registrados "
  "retroalimentan de inmediato las métricas de rentabilidad del propio usuario. Las "
  "implicaciones de protección de datos de este componente se analizan en el apartado 3.5.")

H("7.7    Despliegue", level=2)
P("La aplicación se despliega en Streamlit Community Cloud y es accesible desde el "
  "navegador del teléfono, donde puede añadirse a la pantalla de inicio como una "
  "aplicación. El usuario no necesita instalar nada: completa un servicio, fotografía el "
  "ticket y el dato queda guardado.")

# ----------------------------- 8. Conclusiones -----------------------------
H("8    Conclusiones y trabajo futuro", level=1)
H("8.1    Conclusiones", level=2)
P("El trabajo demuestra que es posible construir un sistema de apoyo a la decisión útil "
  "para un taxista autónomo a pesar de la ausencia de datos locales de viajes. La "
  "comparativa de modelos arroja un ganador claro y cuantificado —LightGBM reduce el WAPE "
  "del 28,5 % del baseline al 16,5 %, un 42 % menos de error—, la hipótesis de "
  "transferencia se valida con una correlación de 0,88 en la forma horaria, y el resultado "
  "se materializa en un producto real, desplegado y usable por una persona sin perfil "
  "técnico.")
P("Igual de relevante es el mecanismo de captura de datos: al reducir el registro de una "
  "carrera a fotografiar un ticket, el sistema genera de forma continua el conjunto de "
  "datos local que hoy no existe y que es la condición necesaria para cerrar la "
  "transferencia.")

H("8.2    Limitaciones", level=2)
P("Las limitaciones se han ido señalando en cada capítulo; conviene recogerlas juntas.")
for lim in [
    "La fuente de movilidad local mide movilidad general y no demanda de taxi: actúa como "
    "proxy (apartado 6.4).",
    "La resolución espacial es de distrito, con siete distritos para catorce paradas, y la "
    "señal espacial correlaciona a 0,885 con la población, de modo que la recomendación "
    "espacial es de grano grueso y está sesgada hacia los distritos más poblados "
    "(apartado 6.5).",
    "El modelo se evalúa a un horizonte de una hora, disponiendo del valor observado "
    "inmediatamente anterior; no se ha medido su rendimiento a horizontes mayores "
    "(apartado 5.3).",
    "La validación emplea un único corte temporal, sin validación cruzada de origen móvil "
    "ni intervalos de confianza (apartado 5.4).",
    "El LSTM se ha entrenado sin identificador de zona ni normalización de entradas, de "
    "modo que su resultado marca un suelo y no el techo de lo que una red recurrente "
    "puede dar en este problema (apartado 5.7).",
    "El modelo entrenado no alimenta todavía la recomendación del producto (apartado 7.3).",
    "El volumen de datos reales del taxista es aún reducido y está en proceso de "
    "acumulación, por lo que no ha sido posible una validación local del sistema.",
]:
    li(lim)
P("Conviene asimismo señalar que una eventual adopción masiva de la herramienta por muchos "
  "conductores podría saturar las zonas recomendadas, un efecto de conocimiento común que "
  "queda fuera del alcance de este trabajo pero que cualquier despliegue real debería "
  "considerar.")

H("8.3    Líneas futuras", level=2)
for lf in [
    "Cerrar la transferencia operativa: aplicar el patrón temporal aprendido en Nueva York "
    "a las paradas de Terrassa, recalibrado con el volumen local, de modo que la "
    "recomendación pase a apoyarse en el modelo entrenado.",
    "Elevar la resolución espacial ponderando cada parada por sus atractores de demanda "
    "—estaciones, hospitales, centros sanitarios y zonas de ocio— en lugar de repartir de "
    "forma uniforme el valor del distrito.",
    "Evaluar el modelo a veinticuatro horas vista, sin la variable de retardo de una hora, "
    "para caracterizar su rendimiento a horizontes largos.",
    "Mejorar la arquitectura de la red recurrente incorporando una representación "
    "embebida de la zona y la normalización de las variables de entrada, para determinar "
    "si con ello alcanza o supera al gradient boosting.",
    "Incorporar un esquema de validación cruzada de origen móvil que permita acompañar las "
    "métricas de intervalos de confianza.",
    "Sustituir el reconocimiento de tickets en la nube por un reconocimiento óptico local, "
    "eliminando la transferencia de datos a un tercero.",
    "Acumular carreras suficientes para que la tasa de acierto del apartado 7.5 sea "
    "estadísticamente concluyente, y contrastarla además con la estrategia que la "
    "conductora sigue hoy por intuición.",
    "Incorporar el histórico meteorológico horario como variable del modelo, hoy "
    "utilizado solo como información de contexto (apartado 3.3).",
    "Escalar el sistema de un autónomo a cooperativas o pequeñas flotas, y evolucionar la "
    "interfaz hacia una aplicación nativa.",
]:
    li(lf)

# ----------------------------- 9. Bibliografía -----------------------------
H("9    Bibliografía", level=1)

H("9.1    Fuentes de datos", level=2)
for b in [
    "New York City Taxi and Limousine Commission (2024). TLC Trip Record Data. Registros "
    "de viajes de Yellow Taxi. "
    "https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page",
    "Ministerio de Transportes y Movilidad Sostenible (2024). Estudio de la movilidad con "
    "Big Data: matrices origen-destino a partir de datos anonimizados de telefonía móvil. "
    "Portal de descarga: https://opendata-movilidad.mitma.es",
    "Open-Meteo (2024). Free Weather API. Datos meteorológicos horarios. "
    "https://open-meteo.com",
    "OpenStreetMap contributors (2024). Datos geográficos de las paradas de taxi de "
    "Terrassa, obtenidos con la API Overpass y geocodificados con Nominatim. "
    "https://www.openstreetmap.org y https://nominatim.org",
    "Ajuntament de Terrassa (2024). Servei de taxi. Relación de paradas del municipio. "
    "https://www.terrassa.cat/taxis [completar con el título y la URL exactos del "
    "documento descargado]",
    "Elaboración propia (2026). Registro de carreras reales de una taxista autónoma de "
    "Terrassa (cooperativa Tele-Taxi Egara), recogido con consentimiento informado "
    "mediante la aplicación desarrollada en este trabajo. Datos no publicados.",
]:
    P(b)

H("9.2    Herramientas y tecnologías", level=2)
for b in [
    "Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q. y Liu, T.-Y. (2017). "
    "LightGBM: A Highly Efficient Gradient Boosting Decision Tree. Advances in Neural "
    "Information Processing Systems, 30. "
    "https://proceedings.neurips.cc/paper/6907-lightgbm-a-highly-efficient-gradient-"
    "boosting-decision-tree.pdf",
    "Taylor, S. J. y Letham, B. (2018). Forecasting at Scale. The American Statistician, "
    "72(1), 37-45. https://doi.org/10.1080/00031305.2017.1380080",
    "Raasveldt, M. y Mühleisen, H. (2019). DuckDB: an Embeddable Analytical Database. "
    "Proceedings of the 2019 International Conference on Management of Data (SIGMOD 19), "
    "1981-1984. https://doi.org/10.1145/3299869.3320212",
    "Kotov, E., Vidal-Tortosa, E., Cantú-Ros, O. G., Burrieza-Galán, J., Herranz, R., "
    "Gullón Muñoz-Repiso, T. y Lovelace, R. (2026). spanishoddata: A package for accessing "
    "and working with Spanish Open Mobility Big Data. Environment and Planning B: Urban "
    "Analytics and City Science. https://doi.org/10.1177/23998083251415040",
    "Abadi, M. et al. (2015). TensorFlow: Large-Scale Machine Learning on Heterogeneous "
    "Systems. https://www.tensorflow.org",
    "Pedregosa, F. et al. (2011). Scikit-learn: Machine Learning in Python. Journal of "
    "Machine Learning Research, 12, 2825-2830. https://scikit-learn.org",
    "McKinney, W. (2010). Data Structures for Statistical Computing in Python. Proceedings "
    "of the 9th Python in Science Conference, 56-61. https://pandas.pydata.org",
    "Streamlit Inc. (2024). Streamlit: A faster way to build and share data apps. "
    "https://docs.streamlit.io",
    "Folium contributors (2024). Folium: Python Data, Leaflet.js Maps. "
    "https://python-visualization.github.io/folium y https://leafletjs.com",
    "Google (2025). Gemini API: modelos generativos multimodales. https://ai.google.dev",
]:
    P(b)

H("9.3    Referencias académicas", level=2)
for b in [
    "Zhang, J., Zheng, Y. y Qi, D. (2017). Deep Spatio-Temporal Residual Networks for "
    "Citywide Crowd Flows Prediction. Proceedings of the AAAI Conference on Artificial "
    "Intelligence, 31(1). https://ojs.aaai.org/index.php/AAAI/article/view/10735",
    "Elsayed, S., Thyssens, D., Rashed, A., Schmidt-Thieme, L. y Jomaa, H. S. (2021). Do "
    "We Really Need Deep Learning Models for Time Series Forecasting? arXiv:2101.02118. "
    "https://arxiv.org/abs/2101.02118",
    "Grinsztajn, L., Oyallon, E. y Varoquaux, G. (2022). Why do tree-based models still "
    "outperform deep learning on typical tabular data? Advances in Neural Information "
    "Processing Systems, 35. https://proceedings.neurips.cc/paper_files/paper/2022/file/"
    "0378c7692da36807bdec87ab043cdadc-Paper-Datasets_and_Benchmarks.pdf",
]:
    P(b)
P("[Ampliar con las referencias adicionales que se consulten sobre predicción de demanda "
  "de taxi y sobre transferencia de modelos entre ciudades.]")

# ----------------------------- 10. Anexos -----------------------------
salto(doc)
H("10    Anexos", level=1)

H("10.1    Anexo A — Consentimiento informado", level=2)
P("Se reproduce a continuación el modelo de consentimiento entregado a la participante. "
  "[Revisar con el tutor antes de la entrega y adjuntar el ejemplar firmado.]")
P("Título del trabajo: Sistema inteligente de predicción de demanda para taxistas "
  "autónomos. Responsable del tratamiento: Pau Gavilán, autor del Trabajo de Fin de "
  "Máster.")
for c in [
    "Finalidad. Los datos de las carreras que usted registre se utilizarán exclusivamente "
    "para el desarrollo y la evaluación de este Trabajo de Fin de Máster, con fines "
    "académicos y sin explotación comercial.",
    "Datos recogidos. Fecha, hora de inicio y fin, direcciones de origen y destino, "
    "distancia, importe y tipo de servicio de cada carrera. No se recoge ningún dato "
    "identificativo de los clientes.",
    "Tratamiento por terceros. La fotografía del ticket se procesa mediante la API de "
    "Gemini (Google), que actúa como encargado del tratamiento, lo que supone una "
    "transferencia internacional de datos. Los datos extraídos se almacenan en una hoja de "
    "cálculo de acceso restringido.",
    "Publicación. En la memoria y en cualquier difusión del trabajo solo aparecerán datos "
    "agregados. Las direcciones concretas no se publicarán en ningún caso.",
    "Conservación. Los datos se conservarán hasta la defensa del trabajo y su posterior "
    "evaluación, tras lo cual serán suprimidos.",
    "Derechos. Puede retirar su consentimiento en cualquier momento, sin justificación y "
    "sin consecuencia alguna, y ejercer los derechos de acceso, rectificación, supresión, "
    "limitación, portabilidad y oposición dirigiéndose al responsable del tratamiento.",
]:
    li(c)
P("Nombre y apellidos: ______________________________    DNI: ____________________")
P("Firma: ______________________________    Fecha: ____________________")

H("10.2    Anexo B — Plantilla de registro de carreras", level=2)
P("El registro se articula en una hoja de cálculo con tres pestañas: instrucciones de "
  "cumplimentación, registro de carreras y lista de zonas de referencia. La tabla 4 "
  "recoge los campos del registro.")
tabla(doc, ["Campo", "Tipo", "Obligatorio"],
      [["Fecha", "Fecha", "Sí"],
       ["Hora de recogida", "Hora", "Sí"],
       ["Hora de fin", "Hora", "No"],
       ["Zona de recogida", "Texto", "Sí"],
       ["Zona de destino", "Texto", "No"],
       ["Distancia (km)", "Numérico", "Sí"],
       ["Importe (€)", "Numérico", "Sí"],
       ["Origen del servicio", "Texto", "No"],
       ["Forma de pago", "Texto", "No"],
       ["Minutos en vacío antes", "Numérico", "No"],
       ["Notas", "Texto", "No"]])
pie_tabla(doc, "Campos de la plantilla de registro de carreras.")
P("La hoja de instrucciones incluye la regla de oro entregada a la participante: anotar lo "
  "sucedido sin modificarlo a posteriori, y corregir mediante una nota en lugar de borrar, "
  "para preservar el valor del dato original.")

H("10.3    Anexo C — Capturas de la aplicación", level=2)
P("Las capturas siguientes corresponden a la aplicación en funcionamiento, tomadas desde "
  "el navegador con el ancho de un teléfono, que es el formato de uso real.")
figura(doc, "captura conductor.png",
       "Modo Conductor: recomendación destacada, mapa de las catorce paradas por nivel de "
       "demanda y ranking. La parada recomendada aparece resaltada también en la lista.",
       ancho=Inches(4.0))
figura(doc, "captura registrar.png",
       "Modo Registrar: captura del ticket y revisión de los campos extraídos antes de "
       "guardarlos en el registro.",
       ancho=Inches(4.6))
figura(doc, "captura analisis.png",
       "Modo Análisis: rentabilidad real de la conductora, patrón de demanda por hora y "
       "comparación de la transferencia entre Nueva York y Terrassa.",
       ancho=Inches(4.0))

H("10.4    Anexo D — Estructura del repositorio", level=2)
P("El código del proyecto se organiza del siguiente modo:")
tabla(doc, ["Ruta", "Contenido"],
      [["app.py", "Aplicación Streamlit (punto de entrada del despliegue)"],
       ["pipeline/", "Fases 1 y 2: descarga y agregación, variables, baseline y modelos"],
       ["notebooks/", "Análisis exploratorio y comparación de patrones"],
       ["scripts/", "Utilidades: paradas de OpenStreetMap, geocodificación, lector de tickets"],
       ["data/external/", "Fuentes de terceros versionadas: perfil MITMA, distritos, paradas"],
       ["data/raw · processed · gold", "Capas de datos, regenerables desde la fase 1"],
       ["results/", "Tablas de resultados de la comparativa"],
       ["docs/figuras/", "Figuras de esta memoria y el script que las genera"]])
pie_tabla(doc, "Organización del repositorio del proyecto.")

doc.save(str(SALIDA))
print("Guardado:", SALIDA)
print("Párrafos:", len(doc.paragraphs), "| Tablas:", len(doc.tables))
