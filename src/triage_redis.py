import redis
import time
import json

from datetime import datetime, timezone
from pymongo import MongoClient
from anonimizacion import anonimizar_documento
from config import settings


# Importa la librería cliente de Redis para Python y el módulo nativo de tiempo (time).

redis_client = redis.Redis(host='redis-server', port=6379, decode_responses=True)
COL_ESPERA = "urgencias:cola_espera"

# Crea la instancia de conexión con el contenedor 'redis-server' en el puerto 6379. 
# decode_responses=True hace que los datos devueltos sean strings de Python en lugar de bytes.
# Se define la constante COL_ESPERA con el nombre de la clave del Sorted Set en Redis.

def procesar_novedades(data):
    """Procesa los nuevos ingresos y calcula el score Earliest Deadline First."""
    nuevos_ingresos = data.get("nuevos_ingresos", [])
    eventos_locales = []
    
    # Define la función que recibe el diccionario de la API, extrae la lista de ingresos 
    # y prepara una lista vacía para acumular los mensajes de eventos que ocurran.

    if not nuevos_ingresos:
        return eventos_locales
    # Si la lista de nuevos ingresos está vacía, la función termina de inmediato devolviendo la lista vacía.

    for paciente in nuevos_ingresos:
        id_episodio = paciente.get("id_episodio")
        datos_admision = paciente.get("datos_admision", {})
        datos_triaje = paciente.get("datos_triaje", {})
        
        # Recorre uno a uno los pacientes nuevos y extrae sus subdiccionarios: 
        # ID de episodio, datos de admisión y datos de triaje.

        timestamp_llegada = datos_admision.get("timestamp_llegada")
        tiempo_max_espera_min = datos_triaje.get("tiempo_max_espera_min", 60)
        
        # Extrae la hora exacta de llegada (timestamp) y el tiempo máximo de espera permitido en minutos (por defecto 60).

        if timestamp_llegada:
            score = timestamp_llegada + (tiempo_max_espera_min * 60)
            
            # Algoritmo EDF (Earliest Deadline First): Convierte los minutos a segundos y los suma 
            # al timestamp de llegada para calcular el límite exacto en el que debe ser atendido.

            redis_client.zadd(COL_ESPERA, {id_episodio: score})
            
            # Inserta o actualiza el episodio en el Sorted Set de Redis usando el score calculado. 
            # Redis ordenará automáticamente la cola poniendo primero al que tenga el score menor (mayor urgencia).

            redis_client.hset(f"episodio:{id_episodio}", mapping={
                "nombre": datos_admision.get("nombre"),
                "sip": datos_admision.get("sip_paciente"),
                "motivo": datos_admision.get("motivo_consulta"),
                "color": datos_triaje.get("color"),
                "patologia": datos_triaje.get("categoria_patologia"),
                "documento": json.dumps(paciente, ensure_ascii=False)  
            })
            
            # Crea un Hash en Redis para este episodio (ej. "episodio:EP-1234") guardando 
            # sus datos clínicos detallados (nombre, SIP, motivo, color de triaje y patología).

            eventos_locales.append(f"[+] Ingreso: {id_episodio} ({datos_admision.get('nombre')}) [Triaje: {datos_triaje.get('color')}]")
            
    return eventos_locales
    # Añade un mensaje descriptivo a la lista de eventos locales y finalmente la devuelve.

def procesar_altas(data):
    """Procesa los pacientes dados de alta: libera boxes y limpia Redis."""
    pacientes_alta = data.get("pacientes_alta", [])
    eventos_locales = []

    if not pacientes_alta:
        return eventos_locales

    for alta in pacientes_alta:
        id_episodio = alta.get("id_episodio")

        # Recorre la lista de altas médicas enviadas por la API extrayendo el ID del episodio que finaliza.

        # Recuperamos los datos completos del paciente desde Redis
        datos_redis = redis_client.hgetall(f"episodio:{id_episodio}")

        if not datos_redis or "documento" not in datos_redis:
            eventos_locales.append(f"[!] No se encontraron los datos de {id_episodio}")
            continue

        documento = json.loads(datos_redis["documento"])

        # Añadimos los datos del alta al documento
        documento.update(alta)

        # NUEVO: Guardamos el episodio en MongoDB
        try:
            cargar_datos_mongo(documento)
            eventos_locales.append(f"[+] Episodio guardado en MongoDB: {id_episodio}")

        except Exception as e:
            eventos_locales.append(f"[!] Error al guardar en MongoDB: {e}")
            continue

        # NUEVO: Eliminamos el episodio de la cola si todavía estuviera esperando
        redis_client.zrem(COL_ESPERA, id_episodio)

        for box_id in range(1, 6):
            box_key = f"box:{box_id}"
            datos_box = redis_client.hgetall(box_key)

            if datos_box.get("id_episodio") == id_episodio:
                redis_client.delete(f"{box_key}:ocupado")
                redis_client.delete(box_key)
                eventos_locales.append(f"[-] Box {box_id} liberado por alta de {id_episodio}")
                break

        # Revisa los 5 boxes clínicos (1 al 5) para encontrar cuál estaba ocupado por ese paciente. 
        # Al encontrarlo, borra la clave de ocupación y el hash del box, registrando el evento.

        redis_client.delete(f"episodio:{id_episodio}")
        eventos_locales.append(f"[x] Cierre y borrado de Redis: {id_episodio}")

    return eventos_locales
    # Elimina definitivamente el Hash con la ficha clínica del paciente en Redis y retorna los eventos.

def gestionar_boxes():
    """Asigna pacientes desde la cola de espera hacia los boxes libres."""
    eventos_locales = []
    for box_id in range(1, 6):
        box_key = f"box:{box_id}"
        
        # Itera por los 5 boxes del hospital para comprobar cuáles están libres.

        if not redis_client.exists(f"{box_key}:ocupado"):
            siguiente = redis_client.zpopmin(COL_ESPERA, count=1)
            
            # Si el box no tiene la marca de ocupado, extrae de forma atómica (ZPOPMIN) 
            # al paciente con menor score (mayor prioridad) del Sorted Set de la cola de espera.

            if siguiente:
                id_episodio, score = siguiente[0]
                
                redis_client.hset(box_key, mapping={
                    "id_episodio": id_episodio,
                    "hora_entrada": time.time()
                })
                redis_client.set(f"{box_key}:ocupado", "1")
                
                eventos_locales.append(f"[>] Box {box_id} asignado a {id_episodio}")
                
    return eventos_locales
    # Si había pacientes esperando, guarda el episodio y la hora de entrada en el Hash del box, 
    # activa el indicador de ocupado y registra el evento.

def construir_esquema_historico(documento):
    """
    Toma el documento de Redis/API y lo estructura con el mismo esquema anidado
    del histórico (parte_clinico, triaje_manchester, constantes, etc.),
    eliminando valores nulos y excluyendo fechas de texto.
    """
    # 1. Extraer datos de admisión y triaje de forma segura
    datos_admision = documento.get("datos_admision") or {}
    datos_triaje = documento.get("datos_triaje") or {}

    constantes = (datos_triaje.get("constantes") or {}).copy()
    for campo in ("frecuencia_cardiaca", "tension_arterial"):
        if constantes.get(campo) is None and documento.get(campo) is not None:
            constantes[campo] = documento[campo]

    timestamp_llegada = datos_admision.get("timestamp_llegada")
    if timestamp_llegada is None:
        timestamp_llegada = documento.get("timestamp_llegada")

    # 2. Construir el subdocumento parte_clinico anidado
    parte_clinico = {
        "_id_parte": documento.get("_id_parte") or f"CLIN-{documento.get('id_episodio', '')}",
        "edad": datos_admision.get("edad"),
        "triaje_manchester": {
            "nivel": datos_triaje.get("nivel_manchester") or datos_triaje.get("nivel"),
            "color": datos_triaje.get("color"),
            "categoria_patologia": datos_triaje.get("categoria_patologia"),
            "tiempo_max_espera_min": datos_triaje.get("tiempo_max_espera_min")
        },
        "constantes": constantes,
        "antecedentes": datos_triaje.get("antecedentes", datos_admision.get("antecedentes", [])),
        "alergias": datos_triaje.get("alergias", datos_admision.get("alergias", [])),
        "notas_triaje": datos_triaje.get("notas_triaje")
    }

    # La API envía los módulos dentro del triaje; admitir también los de la raíz.
    for origen in (datos_triaje, documento):
        for k, v in origen.items():
            if k.startswith("modulo_"):
                parte_clinico[k] = v

    # 3. Construir el documento raíz principal alineado al histórico
    documento_estructurado = {
        "id_episodio": documento.get("id_episodio"),
        "sip_paciente": documento.get("sip_paciente") or datos_admision.get("sip_paciente"),
        "timestamp_llegada": timestamp_llegada,
        "timestamp_alta": documento.get("timestamp_alta"),
        "motivo_consulta": datos_admision.get("motivo_consulta") or documento.get("motivo_consulta"),
        "destino_alta": documento.get("destino_alta"),
        "parte_clinico": parte_clinico
    }

    # 4. Función auxiliar recursiva para limpiar valores None y subdiccionarios vacíos
    def limpiar_nulos(d):
        if isinstance(d, dict):
            limpio = {k: limpiar_nulos(v) for k, v in d.items()}
            return {
                k: v
                for k, v in limpio.items()
                if v is not None and v != {} and v != []
            }
        elif isinstance(d, list):
            limpio = [limpiar_nulos(item) for item in d]
            return [item for item in limpio if item is not None and item != {} and item != []]
        return d

    return limpiar_nulos(documento_estructurado)


def cargar_datos_mongo(documento):
    """Guarda el episodio protegido con el esquema histórico y fechas BSON en UTC."""
    # Se protege el documento completo, incluido el SIP recibido en el alta.
    # El esquema histórico elimina después los nulos generados al transformar.
    documento_estructurado = construir_esquema_historico(anonimizar_documento(documento))

    for campo in ("timestamp_llegada", "timestamp_alta"):
        ts = documento_estructurado.get(campo)
        if isinstance(ts, (int, float)) and not isinstance(ts, bool):
            try:
                documento_estructurado[campo] = datetime.fromtimestamp(ts, tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                pass

    cliente = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)

    try:
        coleccion = cliente[settings.MONGO_DATABASE][settings.MONGO_COLLECTION]

        coleccion.replace_one(
            {"id_episodio": documento_estructurado["id_episodio"]},
            documento_estructurado,
            upsert=True
        )

        print(f"Episodio {documento_estructurado['id_episodio']} guardado en MongoDB.")

    finally:
        cliente.close()
