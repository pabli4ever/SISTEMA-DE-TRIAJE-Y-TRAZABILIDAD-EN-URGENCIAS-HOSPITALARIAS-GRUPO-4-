import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

app = FastAPI(
    title="Servicio de Urgencias - API de Admisiones y Triaje (CareStream)",
    description="API que emite en tiempo real admisiones clínicas completas y notificaciones de alta hospitalaria.",
    version="2.0.0"
)

# ==============================================================================
# CONFIGURACIÓN Y CONSTANTES CLÍNICAS
# ==============================================================================
CATEGORIAS_PATOLOGIA = [
    "Cardiovascular", "Traumatologia", "Pediatria", "Respiratorio", "Digestivo", "Neurologia", "Nefrourologia", "Infeccioso", "Psiquiatria"
]

NIVELES_MANCHESTER = {
    1: {"color": "rojo", "espera": 0},
    2: {"color": "naranja", "espera": 10},
    3: {"color": "amarillo", "espera": 60},
    4: {"color": "verde", "espera": 120},
    5: {"color": "azul", "espera": 240}
}

DESTINOS_ALTA = ["domicilio", "ingreso_planta", "observacion", "ingreso_pediatria", "traslado_uci"]

NOMBRES_EJEMPLO = [
    "Ana García Pérez", "Carlos Ruiz Martínez", "Lucía Morales Fernández", "Javier Soto López", "Beatriz Gil Sánchez", "David Cano Rodríguez",
    "Elena Romero Gómez", "Marcos Soler Navarro", "Sofía Blanco Serrano", "Hugo Navarro Díaz", "Carmen Vega Martín", "Pablo Iglesias Muñoz",
    "Alejandro Torres Ramos", "Marta Castro Domínguez", "Álvaro Delgado Ortiz", "Paula Ortiz Molina", "Manuel Marín Rubio", "Laura Medina Sanz",
    "Daniel Cortés Castillo", "Sara Garrido Lozano", "Adrián Santos Guerrero", "Irene Peña Cano", "Gonzalo Prieto Calvo", "Clara Vidal Gallego",
    "Jorge Herrera Crespo", "Raquel Flores Benítez", "Rubén Aguilar Parra", "Natalia Méndez León", "Diego Cabrera Ibáñez", "Alba Campos Rivas",
    "Mario Reyes Cruz", "Patricia Fuentes Carrasco", "Víctor Pastor Montero", "Marina Nieto Herrero", "Iván Santiago Giménez", "Silvia Hidalgo Vidal",
    "Sergio Moya Pardo", "Andrea Pascual Mora", "Fernando Bravo Esteban", "Nuria Roldán Gil", "Gabriel Santana Márquez", "Miriam Ferrer Soto",
]

# ==============================================================================
# MODELOS PYDANTIC (Esquema enriquecido idéntico al histórico)
# ==============================================================================
class ConstantesVitales(BaseModel):
    temperatura_c: float
    frecuencia_cardiaca: int
    tension_arterial: str
    saturacion_o2: Optional[int] = None
    glucemia_mg_dl: Optional[int] = None

class DatosTriaje(BaseModel):
    nivel_manchester: int
    color: str
    categoria_patologia: str
    tiempo_max_espera_min: int
    constantes: ConstantesVitales
    antecedentes: List[str]
    alergias: Optional[List[str]] = None
    notas_triaje: str
    # Módulos polimórficos según especialidad
    modulo_cardiologia: Optional[Dict[str, Any]] = None
    modulo_traumatologia: Optional[Dict[str, Any]] = None
    modulo_pediatria: Optional[Dict[str, Any]] = None

class DatosAdmision(BaseModel):
    sip_paciente: str
    nombre: str
    edad: int
    motivo_consulta: str
    timestamp_llegada: float
    fecha_hora_texto: str

class NuevoIngreso(BaseModel):
    id_episodio: str
    datos_admision: DatosAdmision
    datos_triaje: DatosTriaje

class PacienteAlta(BaseModel):
    id_episodio: str
    sip_paciente: str
    timestamp_alta: float
    fecha_hora_alta: str
    destino_alta: str

class RespuestaNovedades(BaseModel):
    status: str
    timestamp_consulta: float
    total_nuevos: int
    total_altas: int
    nuevos_ingresos: List[NuevoIngreso]
    pacientes_alta: List[PacienteAlta]

# ==============================================================================
# ESTADO DEL SIMULADOR EN MEMORIA
# ==============================================================================
contador_episodios = 70000

# Colas intermedias de eventos pendientes de consumir en el siguiente poll
buffer_nuevos_ingresos: List[NuevoIngreso] = []
buffer_altas: List[PacienteAlta] = []

# Censo de pacientes actualmente dentro del hospital
pacientes_activos: Dict[str, Dict[str, Any]] = {}

ultima_llegada_tiempo = time.time()
ultima_alta_tiempo = time.time()

# ==============================================================================
# FUNCIONES GENERADORAS
# ==============================================================================
def generar_paciente_sintetico(nivel_forzado: Optional[int] = None, motivo_forzado: Optional[str] = None) -> NuevoIngreso:
    global contador_episodios
    contador_episodios += 1
    
    ahora = time.time()
    dt_str = datetime.fromtimestamp(ahora).strftime("%Y-%m-%d %H:%M:%S")
    id_ep = f"EP-2026-{contador_episodios:05d}"
    sip = f"SIP-{random.randint(100000, 999999)}"
    
    patologia = random.choice(CATEGORIAS_PATOLOGIA)
    edad = random.randint(0, 14) if patologia == "Pediatria" else random.randint(16, 92)
    
    if nivel_forzado is not None:
        nivel = nivel_forzado
    else:
        nivel = random.choices([1, 2, 3, 4, 5], weights=[0.05, 0.20, 0.40, 0.25, 0.10])[0]

    # Constantes vitales dentro de rangos normales/asistenciales
    sis = random.randint(105, 160)
    dia = random.randint(60, 95)
    constantes = ConstantesVitales(
        temperatura_c=round(random.uniform(36.0, 39.4), 1),
        frecuencia_cardiaca=random.randint(58, 125),
        tension_arterial=f"{sis}/{dia}",
        saturacion_o2=random.randint(91, 100) if random.random() > 0.05 else None,
        glucemia_mg_dl=random.randint(70, 220) if random.random() > 0.25 else None
    )

    motivo = motivo_forzado if motivo_forzado else f"Urgencia aguda por {patologia.lower()}"

    triaje = DatosTriaje(
        nivel_manchester=nivel,
        color=NIVELES_MANCHESTER[nivel]["color"],
        categoria_patologia=patologia,
        tiempo_max_espera_min=NIVELES_MANCHESTER[nivel]["espera"],
        constantes=constantes,
        antecedentes=random.sample(["hipertension", "diabetes", "dislipemia", "asma", "fumador"], k=random.randint(0, 2)),
        alergias=random.choice([[], ["penicilina"], None, ["AINEs"], ["sulfamidas"]]),
        notas_triaje=f"Paciente valorado en triaje con nivel de prioridad {NIVELES_MANCHESTER[nivel]['color'].upper()}."
    )

    # Polimorfismo clínico idéntico al dataset histórico
    if patologia == "Cardiovascular":
        triaje.modulo_cardiologia = {
            "ecg_realizado": True,
            "ritmo": random.choice(["sinusal", "fibrilacion_auricular", "taquicardia"]),
            "troponinas_ng_ml": round(random.uniform(0.01, 2.30), 2),
            "dolor_irradiado": random.choice([True, False])
        }
    elif patologia == "Traumatologia":
        triaje.modulo_traumatologia = {
            "zona_afectada": random.choice(["tobillo_der", "muneca_izq", "rodilla", "hombro"]),
            "deformidad_evidente": random.choice([True, False]),
            "requiere_rx": True,
            "inmovilizacion_previa": random.choice([True, False])
        }
    elif patologia == "Pediatria":
        triaje.modulo_pediatria = {
            "peso_kg": round(random.uniform(3.5, 36.0), 1),
            "alimentacion_tolerada": random.choice([True, False]),
            "convulsion_febril_previa": False,
            "vacunacion_al_dia": True
        }

    admision = DatosAdmision(
        sip_paciente=sip,
        nombre=random.choice(NOMBRES_EJEMPLO),
        edad=edad,
        motivo_consulta=motivo,
        timestamp_llegada=ahora,
        fecha_hora_texto=dt_str
    )

    return NuevoIngreso(
        id_episodio=id_ep,
        datos_admision=admision,
        datos_triaje=triaje
    )

def ciclo_simulacion_automatica():
    """Genera admisiones cada 10-15s y altas cada 20-30s."""
    global ultima_llegada_tiempo, ultima_alta_tiempo
    ahora = time.time()

    # 1. Simulación de nuevas admisiones
    intervalo_llegada = random.uniform(10.0, 15.0)
    if (ahora - ultima_llegada_tiempo) >= intervalo_llegada:
        nuevo = generar_paciente_sintetico()
        buffer_nuevos_ingresos.append(nuevo)
        # Registramos en el censo interno de pacientes activos
        pacientes_activos[nuevo.id_episodio] = {
            "id_episodio": nuevo.id_episodio,
            "sip_paciente": nuevo.datos_admision.sip_paciente,
            "timestamp_llegada": nuevo.datos_admision.timestamp_llegada
        }
        ultima_llegada_tiempo = ahora

    # 2. Simulación de altas de pacientes que ya llevan tiempo
    intervalo_alta = random.uniform(20.0, 30.0)
    if (ahora - ultima_alta_tiempo) >= intervalo_alta and len(pacientes_activos) > 2:
        # Elegir un paciente activo al azar para darle el alta médica
        candidatos = list(pacientes_activos.keys())
        id_a_dar_alta = random.choice(candidatos)
        paciente_info = pacientes_activos.pop(id_a_dar_alta)

        alta_evento = PacienteAlta(
            id_episodio=paciente_info["id_episodio"],
            sip_paciente=paciente_info["sip_paciente"],
            timestamp_alta=ahora,
            fecha_hora_alta=datetime.fromtimestamp(ahora).strftime("%Y-%m-%d %H:%M:%S"),
            destino_alta=random.choice(DESTINOS_ALTA)
        )
        buffer_altas.append(alta_evento)
        ultima_alta_tiempo = ahora

# ==============================================================================
# ENDPOINTS DE LA API
# ==============================================================================

@app.get("/api/v1/urgencias/novedades", response_model=RespuestaNovedades, tags=["Servicio Urgencias"])
def obtener_novedades():
    """
    Endpoint principal consultado por los alumnos mediante polling cada 5 segundos.
    Devuelve los nuevos ingresos y las altas ocurridas desde la última llamada y vacía los buffers.
    """
    ciclo_simulacion_automatica()

    global buffer_nuevos_ingresos, buffer_altas
    nuevos_a_entregar = list(buffer_nuevos_ingresos)
    altas_a_entregar = list(buffer_altas)

    # Vaciar los buffers una vez entregados
    buffer_nuevos_ingresos.clear()
    buffer_altas.clear()

    return RespuestaNovedades(
        status="ok",
        timestamp_consulta=time.time(),
        total_nuevos=len(nuevos_a_entregar),
        total_altas=len(altas_a_entregar),
        nuevos_ingresos=nuevos_a_entregar,
        pacientes_alta=altas_a_entregar
    )

@app.post("/api/v1/profesor/inyectar-emergencia", tags=["Panel Docente"])
def inyectar_emergencia_profesor(
    nivel: int = Query(1, ge=1, le=5, description="Nivel Manchester a forzar (1 es Rojo/Crítico)"),
    motivo: str = Query("Parada cardiorrespiratoria presenciada", description="Motivo clínico de consulta")
):
    """
    Permite al profesor inyectar inmediatamente una emergencia crítica durante la demo.
    """
    paciente_critico = generar_paciente_sintetico(nivel_forzado=nivel, motivo_forzado=motivo)
    buffer_nuevos_ingresos.append(paciente_critico)
    pacientes_activos[paciente_critico.id_episodio] = {
        "id_episodio": paciente_critico.id_episodio,
        "sip_paciente": paciente_critico.datos_admision.sip_paciente,
        "timestamp_llegada": paciente_critico.datos_admision.timestamp_llegada
    }
    return {
        "resultado": "Emergencia inyectada con éxito",
        "id_episodio": paciente_critico.id_episodio,
        "nivel": nivel,
        "color": NIVELES_MANCHESTER[nivel]["color"],
        "motivo": motivo
    }

@app.post("/api/v1/profesor/forzar-alta", tags=["Panel Docente"])
def forzar_alta_profesor(id_episodio: Optional[str] = None):
    """
    Permite al profesor forzar el alta de un paciente específico o del más antiguo para comprobar
    si el equipo vacía el box y persiste correctamente en MongoDB.
    """
    global pacientes_activos, buffer_altas
    if not pacientes_activos:
        return {"error": "No hay pacientes activos en urgencias para dar de alta."}

    if id_episodio and id_episodio in pacientes_activos:
        elegido = id_episodio
    else:
        # Tomar el más antiguo ingresado
        elegido = list(pacientes_activos.keys())[0]

    info = pacientes_activos.pop(elegido)
    ahora = time.time()
    alta_manual = PacienteAlta(
        id_episodio=info["id_episodio"],
        sip_paciente=info["sip_paciente"],
        timestamp_alta=ahora,
        fecha_hora_alta=datetime.fromtimestamp(ahora).strftime("%Y-%m-%d %H:%M:%S"),
        destino_alta="domicilio"
    )
    buffer_altas.append(alta_manual)
    return {"resultado": "Alta forzada generada", "episodio": elegido}

@app.get("/api/v1/simulador/estado", tags=["Monitorización"])
def ver_censo_actual():
    """Muestra el total de pacientes activos y el estado de los buffers."""
    return {
        "pacientes_activos_total": len(pacientes_activos),
        "buffer_nuevos_pendientes": len(buffer_nuevos_ingresos),
        "buffer_altas_pendientes": len(buffer_altas),
        "ids_activos": list(pacientes_activos.keys())
    }

@app.post("/api/v1/simulador/reset", tags=["Monitorización"])
def resetear_simulador():
    """Limpia el estado en memoria para evaluar al siguiente grupo desde cero."""
    global buffer_nuevos_ingresos, buffer_altas, pacientes_activos
    buffer_nuevos_ingresos.clear()
    buffer_altas.clear()
    pacientes_activos.clear()
    return {"mensaje": "Simulador reiniciado correctamente para la siguiente evaluación."}