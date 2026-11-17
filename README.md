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

## Protección de los datos guardados

El histórico y las altas se guardan con el SIP transformado mediante HMAC-SHA256
(32 caracteres hexadecimales), sin el campo `nombre` y con la edad agrupada por
décadas, por ejemplo `[60-69]`. También se transforman los campos anidados.
Las altas usan el esquema anidado del histórico (`parte_clinico`, `constantes`
y `triaje_manchester`), conservan los antecedentes, alergias y módulos del triaje,
y eliminan campos nulos y estructuras vacías. Los timestamps se guardan como
fechas BSON en UTC.

La clave privada se configura como `ANON_HMAC_KEY` en `docker/.env`. Para generar
una clave al preparar una instalación nueva:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copia el resultado como valor de `ANON_HMAC_KEY`. Conserva la misma clave para el
histórico y el worker; no la regeneres en cada ejecución ni la publiques en Git.
Si falta, el programa se detiene antes de guardar. Después de cambiar el `.env`,
recrea el servicio Python desde la carpeta `docker`:

```bash
docker compose up -d --no-deps --force-recreate python-server
```

Para generar solo el JSON del histórico, desde la raíz del proyecto:

```bash
python src/etl_historico.py --solo-json
```

Cada salida transforma una copia de los documentos originales. Las funciones de
guardado deben recibir esos originales, no documentos ya transformados. Los datos
que ya existan en MongoDB no cambian automáticamente: el histórico se actualiza
al volver a ejecutar el ETL. Redis, los archivos de entrada y los textos clínicos
libres quedan fuera de estas tres transformaciones; no se garantiza anonimato completo.

Para repetir las comprobaciones desde la raíz, con las dependencias instaladas:

```bash
python -m unittest discover -s tests -v
```

Las pruebas usan una clave de ejemplo y simulan las escrituras en MongoDB y Redis;
no cambian la clave del `.env` ni la base de datos real.

---

## 🧹 Limpieza del Entorno

Para detener el sistema y eliminar todos los contenedores y volúmenes generados:

```bash
docker compose down -v
```
