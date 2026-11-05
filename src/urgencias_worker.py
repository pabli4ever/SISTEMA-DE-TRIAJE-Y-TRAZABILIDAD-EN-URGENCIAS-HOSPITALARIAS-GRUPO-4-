import time
import requests
from triage_redis import (
    procesar_novedades,
    procesar_altas,
    gestionar_boxes,
    obtener_estado_cola,
    obtener_info_episodio,
    comprobar_box_ocupado,
    obtener_datos_box
)

# Importa las librerías necesarias y todas las funciones lógicas definidas en el módulo 'triage_redis'.

API_URL = "http://api_urgencias_carestream:28000/api/v1/urgencias/novedades"
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

def mostrar_monitorizacion():
    """Limpia la pantalla y dibuja un panel de control estático y preciso."""
    print("\033c", end="")  # Limpia la terminal
    
    # Envía un comando de escape ANSI por consola para limpiar toda la pantalla en cada ciclo.

    print("="*80)
    print(f"       🏥 PANEL DE CONTROL OPERATIVO - URGENCIAS HOSPITALARIAS")
    print(f"       Última actualización: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # Imprime la cabecera formateada con la fecha y hora actual del sistema.

    cola_longitud, siguientes = obtener_estado_cola(limite=7)
    print(f"📦 Cola de Espera (Pendientes totales: {cola_longitud})")
    
    # Consulta la longitud total de pacientes en espera y obtiene hasta los primeros 7 más prioritarios.

    if siguientes:
        print("   ↳ Siguientes prioridades (EDF más crítico arriba):")
        print(f"     {'Nº':<3} | {'Episodio':<15} | {'Triaje':<10} | {'Paciente':<22} | {'Score (EDF)':<12}")
        print("     " + "-"*72)
        for idx, (ep_id, sc) in enumerate(siguientes, 1):
            info = obtener_info_episodio(ep_id)
            nombre = info.get("nombre", "Desconocido")[:20]
            color = info.get("color", "N/A")
            print(f"     {idx:<3} | {ep_id:<15} | {color:<10} | {nombre:<22} | {int(sc):<12}")
    else:
        print("   ↳ Cola de espera vacía.")

    # Si hay pacientes en la cola, dibuja una tabla perfectamente tabulada con columnas de ancho fijo 
    # mostrando la posición, ID, color de triaje, nombre y score EDF de cada uno.

    print("\n" + "-"*80)
    print("🏥 Estado de los Boxes (1 al 5):")
    print("-"*80)
    for box_id in range(1, 6):
        ocupado = comprobar_box_ocupado(box_id)
        
        if ocupado:
            datos_box = obtener_datos_box(box_id)
            ep_id = datos_box.get("id_episodio", "N/A")
            info = obtener_info_episodio(ep_id)
            nombre = info.get("nombre", "Paciente")
            color = info.get("color", "N/A")
            print(f"   [ Box {box_id} ] 🔴 OCUPADO  --> {ep_id} | {nombre} [Triaje: {color}]")
        else:
            print(f"   [ Box {box_id} ] 🟢 LIBRE")

    # Recorre los 5 boxes consultando su ocupación. Si están ocupados, cruza los datos 
    # para mostrar qué paciente y qué triaje hay dentro; si no, indica que están libres (🟢).

    print("\n" + "-"*80)
    print("📋 Registro de Actividad Reciente:")
    print("-"*80)
    if ultimos_eventos:
        for evento in ultimos_eventos:
            print(f"   {evento}")
    else:
        print("   Sin actividad reciente.")
    print("="*80)

    # Imprime la sección inferior con los últimos eventos registrados en el buffer local.

def main():
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

        mostrar_monitorizacion()
        time.sleep(POLLING_INTERVAL)

# Dibuja el panel actualizado en la terminal y pausa la ejecución durante los segundos configurados antes del siguiente ciclo.

if __name__ == "__main__":
    main()
# Punto de entrada estándar de Python para ejecutar la función principal 'main()'.