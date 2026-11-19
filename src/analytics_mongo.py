import json
import pandas as pd
from pymongo import MongoClient  # Importa el cliente oficial de Python para conectar con bases de datos MongoDB
from config import settings      # Importa el archivo de configuración centralizado del proyecto (config.py) para rescatar los parámetros de conexión sin exponer credenciales.

# Define la función principal que agrupa toda la lógica de análisis estadístico mediante Pandas.
def ejecutar_analytics():
    # Conexión centralizada usando config.py
    cliente = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)   # Crea la instancia del cliente MongoDB usando la URI de configuración, con un tiempo límite de espera de 5 segundos
    coleccion = cliente[settings.MONGO_DATABASE][settings.MONGO_COLLECTION]    # Selecciona de forma dinámica la base de datos y la colección objetivo episodios_urgencias
    
    print(f"Conectado a MongoDB: {settings.MONGO_DATABASE}.{settings.MONGO_COLLECTION}\n")  # Imprime un mensaje por consola informando que la conexión se ha establecido correctamente

    # Extraer todos los documentos de MongoDB a un DataFrame de Pandas
    documentos = list(coleccion.find({}))
    cliente.close()

    if not documentos:
        print("No se encontraron documentos en la colección.")
        return

    df = pd.json_normalize(documentos)

    # Asegurar conversión de fechas de llegada y alta
    df["timestamp_llegada"] = pd.to_datetime(df["timestamp_llegada"], errors="coerce")
    df["timestamp_alta"] = pd.to_datetime(df["timestamp_alta"], errors="coerce")

   
    # =========================================================================
    # CONSULTA_1: Tiempo medio de estancia (en minutos) por categoría patológica de triaje
    # =========================================================================
    campo_categoria = "parte_clinico.triaje_manchester.categoria_patologia"
    
    if campo_categoria in df.columns:
        # Filtrar registros válidos y calcular la estancia en minutos
        df_estancia = df.dropna(subset=["timestamp_llegada", "timestamp_alta", campo_categoria]).copy()
        df_estancia["estancia_min"] = (df_estancia["timestamp_alta"] - df_estancia["timestamp_llegada"]).dt.total_seconds() / 60
        
        # Descartar estancias negativas
        df_estancia_validas = df_estancia[df_estancia["estancia_min"] >= 0]
        
        # Agrupar por categoría y calcular media y conteo
        q1 = (
            df_estancia_validas.groupby(campo_categoria)["estancia_min"]
            .agg(
                tiempo_medio_min="mean",
                total_episodios="count"
            )
            .round(2)
            .reset_index()
            .sort_values(by="tiempo_medio_min", ascending=False)
        )
        
        print("=== 1. TIEMPO MEDIO DE ESTANCIA POR CATEGORÍA PATOLÓGICA ===")
        if q1.empty:
            print("No hay datos suficientes para calcular estancias.")
        else:
            for _, r in q1.iterrows():
                print(f"• Patología: {r[campo_categoria]:<20} | Tiempo Medio: {r['tiempo_medio_min']:>6} min | Episodios: {int(r['total_episodios'])}")
    else:
        print("=== 1. TIEMPO MEDIO DE ESTANCIA POR CATEGORÍA PATOLÓGICA ===")
        print("El campo de categoría patológica no está presente en los datos.")
    
    print("\n" + "="*70 + "\n")

    # =========================================================================
    # Consulta_2. Distribución porcentual de destinos al alta según grupos de edad 
    # (Homogeneizado con la lógica del ETL: strip -> lower -> replace("^alta_", ""))
    # =========================================================================
    campo_edad = "parte_clinico.edad"
    
    if "destino_alta" in df.columns and campo_edad in df.columns:
        df_altas = df.dropna(subset=[campo_edad, "destino_alta"]).copy()
        
        # Replicar limpieza exacta del ETL: .str.strip().str.lower().str.replace(r"^alta_", "", regex=True)[cite: 3]
        df_altas["destino_limpio"] = (
            df_altas["destino_alta"]
            .astype(str)
            .str.strip()
            .str.lower()
            .str.replace(r"^alta_", "", regex=True)
        )
        
        # Homogeneizar a categorías estándar
        def clasificar_destino(dest):
            if dest in ["domicilio", "alta", "altadomicilio"]:
                return "domicilio"
            elif dest in ["ingreso_planta", "ingreso en planta", "ingresoplanta"]:
                return "ingreso_planta"
            elif dest in ["ingreso_pediatria", "ingresopediatria"]:
                return "ingreso_pediatria"
            elif dest in ["traslado_uci", "trasladouci", "uci"]:
                return "traslado_uci"
            elif dest in ["observacion", "observaciones"]:
                return "observacion"
            return dest

        df_altas["destino_std"] = df_altas["destino_limpio"].apply(clasificar_destino)
        
        # Calcular proporciones cruzadas con crosstab
        crosstab_destinos = pd.crosstab(
            df_altas[campo_edad],
            df_altas["destino_std"]
        )
        
        print("=== 2. DISTRIBUCIÓN PORCENTUAL DE DESTINOS AL ALTA POR GRUPO DE EDAD ===")
        for grupo_edad, row in crosstab_destinos.iterrows():
            total_grupo = row.sum()
            print(f"\nGrupo de Edad: {grupo_edad} (Total episodios: {total_grupo})")
            for destino, cantidad in row.items():
                if cantidad > 0:
                    pct = round((cantidad / total_grupo) * 100, 2)
                    print(f"  - Destino: {destino:<18} | Cantidad: {int(cantidad):<5} | Porcentaje: {pct:>6}%")
    else:
        print("=== 2. DISTRIBUCIÓN PORCENTUAL DE DESTINOS AL ALTA POR GRUPO DE EDAD ===")
        print("Faltan campos de destino de alta o grupos de edad en los datos.")

if __name__ == "__main__":
    ejecutar_analytics()