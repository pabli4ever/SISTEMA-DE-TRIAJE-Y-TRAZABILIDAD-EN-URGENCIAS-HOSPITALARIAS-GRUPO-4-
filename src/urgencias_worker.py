import time
import requests
from config import settings
from anonimizacion import obtener_clave
from triage_redis import (
    procesar_novedades,
    procesar_altas,
    gestionar_boxes
)

# Importa las librerías necesarias y las funciones lógicas requeridas desde el módulo 'triage_redis'.

API_URL = settings.API_URL
POLLING_INTERVAL = 5  # Segundos

# Define la URL interna del contenedor de la API y el intervalo de sondeo (cada 5 segundos).

ultimos_eventos = []

def registrar_evento(mensaje):
    """Añade un evento al buffer local manteniendo un máximo de 5 registros."""
    global ultimos_eventos
    timestamp = time.strftime('%H:%M:%S')
    ultimos_eventos.insert(0, f"[{timestamp}] {mensaje}")
    if len(ultimos_eventos) > 5:
        ultimos_eventos.pop()

# Crea una lista global en memoria para almacenar un historial dinámico 
# con los últimos 5 eventos ocurridos, añadiendo una marca de tiempo.

def consultar_api():
    """Realiza la petición GET al endpoint de la API."""
    try:
        response = requests.get(API_URL, timeout=4)
        if response.status_code == 200:
            return response.json()
        else:
            registrar_evento(f"[-] Error en la API: Código {response.status_code}")
    except requests.exceptions.RequestException as e:
        registrar_evento(f"[-] Error de conexión con la API: {e}")
    return None

# Realiza una petición HTTP GET con un límite de tiempo de 4 segundos. 
# Si es exitosa (200), retorna el JSON decodificado; si falla, registra el error en el buffer de eventos.

def main():
    # Comprobar la clave antes de consumir eventos de la API.
    obtener_clave()
    registrar_evento("Iniciando Agente Ingestor de Urgencias...")
    while True:
        datos = consultar_api()
        if datos and datos.get("status") == "ok":
            
            # Bucle principal que arranca el agente, consulta periódicamente la API 
            # y ejecuta secuencialmente las operaciones de negocio si la respuesta es correcta.

            eventos_altas = procesar_altas(datos)
            for ev in eventos_altas:
                registrar_evento(ev)
            
            eventos_novedades = procesar_novedades(datos)
            for ev in eventos_novedades:
                registrar_evento(ev)
            
            eventos_boxes = gestionar_boxes()
            for ev in eventos_boxes:
                registrar_evento(ev)
        
        # Procesa altas (liberando boxes y borrando registros), luego procesa nuevos ingresos 
        # (calculando su EDF) y finalmente asigna los boxes libres, guardando los mensajes en el buffer.

        time.sleep(POLLING_INTERVAL)

# Pausa la ejecución durante los segundos configurados antes del siguiente ciclo.

if __name__ == "__main__":
    main()
# Punto de entrada estándar de Python para ejecutar la función principal 'main()'.
