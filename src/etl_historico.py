import pandas as pd
import requests

def cargar_datos(url_csv, url_json):
        #Descargamos los archivos
        respuesta_csv = requests.get(url_csv, timeout=30)
        respuesta_json = requests.get(url_json, timeout=30)

        #Comprobamos que funciona
        respuesa_csv.raise_for_status()
        respuesta_json.raise_for_status()

        #Guardamos los datos
        with open("historico.csv", "wb") as archivo:
                archivo.write(respuesta_csv.context)

        with open("historico.json", "wb") as archivo:
                archivo.write(respuesta_json.context)

        return datos_csv, datos_json

url_base ="http://10.201.59.244:8080"

datos_csv, datos_json =  cargar_datos(
        url_base + "/archivo.csv",
        url_base + "/archivo.json"
)
datos_csv.head()
datos_json.head()