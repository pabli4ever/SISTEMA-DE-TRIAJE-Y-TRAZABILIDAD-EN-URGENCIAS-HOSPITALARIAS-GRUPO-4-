from pathlib import Path
import json

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
    datos_csv = pd.read_csv(
        CARPETA_DATOS / "admisiones_historico.csv",
        encoding="utf-8-sig",
        na_values=[
            "N/D", "s/d", "ERROR", "PENDIENTE",
            "None", "null", "NULL", ""
        ]
    )

    return datos_csv


def cargar_json():
    with open(
        CARPETA_DATOS / "partes_clinicos.json",
        "r",
        encoding="utf-8"
    ) as archivo:
        datos = json.load(archivo)

    return datos


def limpiar_datos(datos_csv, datos_json):

    # Limpiar espacios en los textos del CSV.
    for columna in datos_csv.select_dtypes(include="object").columns:
        datos_csv[columna] = datos_csv[columna].map(
            lambda valor: valor.strip()
            if isinstance(valor, str)
            else valor
        )

    # Sustituir textos de ausencia por valores nulos.
    datos_csv.replace(
        ["N/D", "s/d", "ERROR", "PENDIENTE",
         "None", "null", "NULL", ""],
        pd.NA,
        inplace=True
    )

    # Eliminar episodios duplicados del CSV.
    datos_csv = datos_csv.drop_duplicates(
        subset="id_episodio"
    ).copy()

    # Unificar las fechas.
    for columna in ["timestamp_llegada", "timestamp_alta"]:
        datos_csv[columna] = pd.to_datetime(
            datos_csv[columna],
            format="mixed",
            dayfirst=True,
            errors="coerce",
            utc=True
        )

    # Convertir las pulsaciones a números.
    datos_csv["frecuencia_cardiaca"] = pd.to_numeric(
        datos_csv["frecuencia_cardiaca"],
        errors="coerce"
    )

    # Marcar como nulas las frecuencias fuera del rango permitido.
    datos_csv["frecuencia_cardiaca"] = (
        datos_csv["frecuencia_cardiaca"].where(
            datos_csv["frecuencia_cardiaca"].between(1, 300)
        )
    )

    # Normalizar los destinos del alta.
    datos_csv["destino_alta"] = (
        datos_csv["destino_alta"]
        .astype("string")
        .str.strip()
        .str.lower()
        .str.replace(r"^alta_", "", regex=True)
    )

    # Devolver el CSV limpio y el JSON original.
    return datos_csv, datos_json

def cruzar_datos(datos_csv, datos_json):

    # Convertir el CSV en una lista de diccionarios.
    registros_csv = json.loads(
        datos_csv.to_json(orient="records", date_format="iso")
    )

    # Crear un diccionario para localizar los informes clínicos.
    partes_por_id = {
        str(parte["id_episodio"]): parte
        for parte in datos_json
    }

    datos_unidos = []

    # Recorrer los episodios del CSV.
    for registro in registros_csv:

        identificador = str(registro["id_episodio"])

        # Buscar su informe clínico.
        parte = partes_por_id.get(identificador)

        if parte:
            parte = parte.copy()
            parte.pop("id_episodio", None)
            parte.pop("sip_paciente", None)

            registro["parte_clinico"] = parte

        datos_unidos.append(registro)

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

    datos_csv, datos_json = limpiar_datos(
        datos_csv,
        datos_json
    )

    # Cruzar ambos DataFrames.
    datos_unidos = cruzar_datos(
        datos_csv,
        datos_json
    )

    # Exportar los datos a JSON.
    nombre_archivo = CARPETA_DATOS / "estado_urgencias.json"

    with open(nombre_archivo, "w", encoding="utf-8") as archivo:
        json.dump(datos_unidos, archivo, ensure_ascii=False, indent=4)

    print(
        f"\n[+] Archivo JSON guardado correctamente: "
        f"{nombre_archivo}"
    )