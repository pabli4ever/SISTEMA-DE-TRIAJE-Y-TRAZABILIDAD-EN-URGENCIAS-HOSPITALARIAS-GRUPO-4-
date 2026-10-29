from pathlib import Path

import pandas as pd
import requests


CARPETA_DATOS = Path("data")


def descargar_archivos(url_csv, url_json):
    # Crear la carpeta data si no existe.
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)

    respuesta_csv = requests.get(url_csv, timeout=30)
    respuesta_json = requests.get(url_json, timeout=30)
    respuesta_csv.raise_for_status()
    respuesta_json.raise_for_status()

    (CARPETA_DATOS / "admisiones_historico.csv").write_bytes(respuesta_csv.content)
    (CARPETA_DATOS / "partes_clinicos.json").write_bytes(respuesta_json.content)
    print("Archivos descargados correctamente.")


def cargar_csv():
    datos_csv = pd.read_csv(CARPETA_DATOS / "admisiones_historico.csv")
    return datos_csv


def cargar_json():
    datos_json = pd.read_json(CARPETA_DATOS / "partes_clinicos.json")
    return datos_json


def limpiar_datos(datos_csv, datos_json):
    # Quitamos duplicados.
    datos_csv = datos_csv.drop_duplicates(subset="id_episodio").copy()
    datos_json = datos_json.drop_duplicates(subset="id_episodio").copy()

    # Sustituimos los textos de ausencia por nulos.
    datos_csv = datos_csv.replace(
        ["N/D", "s/d", "ERROR", "None", "null", "NULL", ""], pd.NA
    )

    # Unificamos las fechas; sin zona horaria se asumen UTC.
    for columna in ["timestamp_llegada", "timestamp_alta"]:
        datos_csv[columna] = pd.to_datetime(
            datos_csv[columna], format="mixed",
            dayfirst=True, errors="coerce", utc=True
        )

    # Convertimos pulsaciones a números y quitamos valores incorrectos.
    pulsaciones = pd.to_numeric(datos_csv["frecuencia_cardiaca"], errors="coerce")
    datos_csv["frecuencia_cardiaca"] = pulsaciones.where(pulsaciones.between(1, 300))

    datos_csv["destino_alta"] = (
        datos_csv["destino_alta"].str.strip().str.lower()
        .str.replace(r"^alta_", "", regex=True)
    )
    return datos_csv, datos_json


def cruzar_datos(datos_csv, datos_json):
    # El SIP coincide en ambos archivos; conservamos el del CSV para no repetirlo.
    datos_json = datos_json.drop(columns="sip_paciente")

    # Añadimos el parte clínico a cada episodio del CSV.
    datos_unidos = pd.merge(datos_csv, datos_json, on="id_episodio", how="left")
    return datos_unidos


if __name__ == "__main__":
    # Dirección del servidor del instituto.
    url_base = "http://10.201.59.244:8080"

    # Ejecutar la descarga en el instituto.
    # descargar_archivos(
    #     url_base + "/archivo.csv",
    #     url_base + "/archivo.json"
    # )

    datos_csv = cargar_csv()
    datos_json = cargar_json()

    datos_csv, datos_json = limpiar_datos(datos_csv, datos_json)
    datos_unidos = cruzar_datos(datos_csv, datos_json)

    # Mostramos una única tabla con todas las filas, columnas y textos completos.
    print(datos_unidos.to_string(index=False))