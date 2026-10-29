# SISTEMA-DE-TRIAJE-Y-TRAZABILIDAD-EN-URGENCIAS-HOSPITALARIAS-GRUPO-4-

# 🏥 Sistema de Gestión de Urgencias Hospitalarias en Tiempo Real

Sistema de monitorización y gestión de flujo de urgencias en tiempo real basado en **Python**, **Redis** (con estructuras de *Sorted Sets* y *Hashes*) y una **API de simulación hospitalaria**, todo orquestado mediante contenedores en una red interna de Docker.

---

## 🏗️ Arquitectura del Sistema

El sistema se compone de los siguientes servicios interconectados dentro de una red de Docker dedicada (`shared-network`):

1. **API Simulador (`api_urgencias`)**: Contenedor que simula la llegada de nuevos ingresos y altas médicas en el puerto `28000`.
2. **Base de Datos (`redis-server`)**: Servidor Redis en memoria (puerto `6379`) encargado de gestionar:
   * Una cola de espera priorizada mediante el algoritmo **EDF (*Earliest Deadline First*)** utilizando *Sorted Sets* (`urgencias:cola_espera`).
   * Los detalles clínicos y demográficos de los pacientes mediante *Hashes* (`episodio:ID`).
   * El estado operativo de los 5 boxes clínicos (`box:1` a `box:5`).
3. **Agente Python (`python-server` / Worker)**: Script modular que realiza *polling* continuo a la API, procesa las prioridades, gestiona la asignación de boxes y muestra una consola interactiva en tiempo real.

---


## 🛠️ Pasos de Despliegue

### 1. Crear la red Docker compartida
Para asegurar la comunicación interna entre los distintos servicios (API, Redis y Python Worker), crea una red de tipo puente (*bridge*):

```bash
docker network create shared-network
```

---

### 2. Levantar los Servicios Principales
Todos los servicios están orquestados centralizadamente en el directorio `/docker`.

1. **Navegar al directorio de Docker:**
   ```bash
   cd docker
   ```

2. **Arrancar los contenedores en segundo plano:**
   ```bash
   docker compose up -d
   ```

---

### 3. Iniciar el Agente de Ingesta (`urgencias_worker.py`)
Una vez levantados los servicios, debes acceder al contenedor del servidor Python para lanzar el script que procesa los datos en tiempo real.

1. **Acceder al espacio de trabajo del servidor Python (`:app` -> `/src`):**
   ```bash
   docker exec -it python-server sh
   ```

2. **Ejecutar el script de ingesta de datos:**
   ```bash
   python urgencias_worker.py
   ```

---

### 4. Configurar el Servicio de Pruebas (`api-urgencias`)
Para comodidad durante la fase de desarrollo, la API simuladora de urgencias está incluida en el propio repositorio.

```bash
cd api_urgencias
docker compose up -d
```

---

## 🧹 Limpieza del Entorno

Para detener el sistema y eliminar todos los contenedores y volúmenes generados:

```bash
docker compose down -v
```