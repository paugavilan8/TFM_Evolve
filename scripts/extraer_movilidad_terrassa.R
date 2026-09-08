# =====================================================================
# Extraccion de datos de movilidad de Terrassa (MITMA)
# Paquete: spanishoddata
# Genera: perfil_movilidad_terrassa.csv  y  terrassa_distritos.geojson
#
# COMO EJECUTAR (en RStudio, POR BLOQUES, no todo de golpe):
#   - Ejecuta el Bloque 1 y espera.
#   - Ejecuta SOLO la linea de descarga del Bloque 2 y espera a que termine
#     (si pregunta yes/no, escribe 'yes' y Enter; NO pegues mas lineas).
#   - Cuando 'od' este cargado, ejecuta el Bloque 3.
#   - El Bloque 4 (geojson para el mapa) es opcional.
# =====================================================================


# ---------------------------------------------------------------------
# INSTALACION (solo la primera vez; luego puedes saltarte esta parte)
# ---------------------------------------------------------------------
# install.packages(c("spanishoddata", "dplyr", "dbplyr", "sf"))


# ---------------------------------------------------------------------
# BLOQUE 1  -  Carga y preparacion
# ---------------------------------------------------------------------
library(spanishoddata)
library(dplyr)

# Carpeta donde se guardan los datos descargados (evita re-descargar).
spod_set_data_dir("~/spanish_od_data")

# Una semana por trimestre de 2023 (28 dias representativos)
fechas <- c("2023-02-13","2023-02-14","2023-02-15","2023-02-16","2023-02-17","2023-02-18","2023-02-19",
            "2023-05-15","2023-05-16","2023-05-17","2023-05-18","2023-05-19","2023-05-20","2023-05-21",
            "2023-09-11","2023-09-12","2023-09-13","2023-09-14","2023-09-15","2023-09-16","2023-09-17",
            "2023-11-13","2023-11-14","2023-11-15","2023-11-16","2023-11-17","2023-11-18","2023-11-19")

# Zonas a nivel de distrito y filtro por municipio de Terrassa (INE 08279)
zonas <- spod_get_zones("dist", ver = 2)
ids   <- zonas |> filter(grepl("08279", municipalities)) |> pull(id)


# ---------------------------------------------------------------------
# BLOQUE 2  -  Descarga (ejecuta SOLO esta linea y espera; ~4-5 GB)
# ---------------------------------------------------------------------
od <- spod_get(type = "od", zones = "dist", dates = fechas, max_download_size_gb = 10)


# ---------------------------------------------------------------------
# BLOQUE 3  -  Perfil local: distrito x hora x dia de la semana
# (el dia de la semana se calcula EN R, no en DuckDB)
# ---------------------------------------------------------------------
perfil_raw <- od |>
  filter(id_origin %in% ids) |>
  group_by(id_origin, date, hour) |>
  summarise(viajes = sum(n_trips, na.rm = TRUE), .groups = "drop") |>
  collect()

perfil_raw$dow <- as.integer(format(as.Date(perfil_raw$date), "%u"))  # 1=lunes ... 7=domingo

perfil <- perfil_raw |>
  group_by(id_origin, hour, dow) |>
  summarise(viajes = sum(viajes), .groups = "drop")

write.csv(perfil, "perfil_movilidad_terrassa.csv", row.names = FALSE)

# Comprobacion rapida
head(perfil)
nrow(perfil)


# ---------------------------------------------------------------------
# BLOQUE 4  -  (OPCIONAL) Geometrias de los distritos para el mapa
# st_transform(4326) convierte a lat/lon (WGS84), necesario para Folium/Leaflet
# ---------------------------------------------------------------------
library(sf)

terrassa_geo <- zonas |>
  filter(grepl("08279", municipalities)) |>
  st_transform(4326)

st_write(terrassa_geo, "terrassa_distritos.geojson",
         driver = "GeoJSON", delete_dsn = TRUE)
