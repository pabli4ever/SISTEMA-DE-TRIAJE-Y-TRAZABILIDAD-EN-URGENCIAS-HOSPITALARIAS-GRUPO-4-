from pymongo import MongoClient
from config import settings

def ejecutar_analytics():
    # Conexión centralizada usando config.py
    cliente = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    coleccion = cliente[settings.MONGO_DATABASE][settings.MONGO_COLLECTION]
    
    print(f"Conectado a MongoDB: {settings.MONGO_DATABASE}.{settings.MONGO_COLLECTION}\n")

   
    # Consulta_1: Tiempo medio de estancia (en minutos) por categoría patológica de triaje
    
    pipeline_estancia = [
        {
            "$match": {
                "timestamp_llegada": {"$type": "date"},
                "timestamp_alta": {"$type": "date"},
                "parte_clinico.triaje_manchester.categoria_patologia": {"$ne": None}
            }
        },
        {
            "$project": {
                "categoria": "$parte_clinico.triaje_manchester.categoria_patologia",
                "estancia_min": {
                    "$divide": [
                        {"$subtract": ["$timestamp_alta", "$timestamp_llegada"]},
                        60000  # Milisegundos a minutos
                    ]
                }
            }
        },
        {
            "$match": {"estancia_min": {"$gte": 0}}
        },
        {
            "$group": {
                "_id": "$categoria",
                "tiempo_medio_min": {"$avg": "$estancia_min"},
                "total_episodios": {"$sum": 1}
            }
        },
        {
            "$project": {
                "_id": 0,
                "categoria_patologia": "$_id",
                "tiempo_medio_min": {"$round": ["$tiempo_medio_min", 2]},
                "total_episodios": 1
            }
        },
        {
            "$sort": {"tiempo_medio_min": -1}
        }
    ]
    
    print("=== 1. TIEMPO MEDIO DE ESTANCIA POR CATEGORÍA PATOLÓGICA ===")
    resultados_estancia = list(coleccion.aggregate(pipeline_estancia))
    if not resultados_estancia:
        print("No hay datos suficientes para calcular estancias.")
    for r in resultados_estancia:
        print(f"• Patología: {r['categoria_patologia']:<20} | Tiempo Medio: {r['tiempo_medio_min']:>6} min | Episodios: {r['total_episodios']}")
    
    print("\n" + "="*70 + "\n")

    # Consulta_2. Distribución porcentual de destinos al alta según grupos de edad
    
    pipeline_destinos = [
        {
            "$match": {
                "parte_clinico.edad": {"$ne": None},
                "destino_alta": {"$in": ["domicilio", "ingreso_planta", "ingreso en planta"]}
            }
        },
        {
            "$project": {
                "grupo_edad": "$parte_clinico.edad",
                "destino": {
                    "$cond": [
                        {"$eq": ["$destino_alta", "domicilio"]},
                        "domicilio",
                        "ingreso_planta"
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": {"grupo_edad": "$grupo_edad", "destino": "$destino"},
                "cantidad": {"$sum": 1}
            }
        },
        {
            "$group": {
                "_id": "$_id.grupo_edad",
                "total_grupo": {"$sum": "$cantidad"},
                "desglose": {"$push": {"destino": "$_id.destino", "cantidad": "$cantidad"}}
            }
        },
        {
            "$sort": {"_id": 1}
        }
    ]
    
    print("=== 2. DISTRIBUCIÓN PORCENTUAL DE DESTINOS AL ALTA POR GRUPO DE EDAD ===")
    resultados_destinos = list(coleccion.aggregate(pipeline_destinos))
    if not resultados_destinos:
        print("No hay datos suficientes para calcular la distribución por edades.")
    for grupo in resultados_destinos:
        print(f"\nGrupo de Edad: {grupo['_id']} (Total episodios: {grupo['total_grupo']})")
        for item in grupo['desglose']:
            pct = round((item['cantidad'] / grupo['total_grupo']) * 100, 2)
            print(f"  - Destino: {item['item'] if 'item' in item else item['destino']:<15} | Cantidad: {item['cantidad']:<5} | Porcentaje: {pct:>6}%")

    cliente.close()

if __name__ == "__main__":
    ejecutar_analytics()