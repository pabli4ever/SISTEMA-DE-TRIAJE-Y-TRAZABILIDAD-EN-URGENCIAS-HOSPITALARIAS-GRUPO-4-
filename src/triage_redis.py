import redis
import time

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
                "patologia": datos_triaje.get("categoria_patologia")
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

def obtener_estado_cola(limite=7):
    """Devuelve la longitud de la cola y los siguientes pacientes priorizados."""
    longitud = redis_client.zcard(COL_ESPERA)
    siguientes = redis_client.zrange(COL_ESPERA, 0, limite - 1, withscores=True)
    return longitud, siguientes
    # Consulta el número total de elementos en la cola (ZCARD) y extrae un rango limitado (ZRANGE) con sus scores.

def obtener_info_episodio(id_episodio):
    """Recupera los datos del hash de un episodio."""
    return redis_client.hgetall(f"episodio:{id_episodio}")
    # Devuelve el diccionario completo almacenado en el Hash del episodio indicado.

def comprobar_box_ocupado(box_id):
    """Verifica si un box está ocupado."""
    return redis_client.get(f"box:{box_id}:ocupado")
    # Retorna el estado de la bandera de ocupación de un box específico.

def obtener_datos_box(box_id):
    """Obtiene la información del box actual."""
    return redis_client.hgetall(f"box:{box_id}")
    # Devuelve el contenido del Hash asociado al box.