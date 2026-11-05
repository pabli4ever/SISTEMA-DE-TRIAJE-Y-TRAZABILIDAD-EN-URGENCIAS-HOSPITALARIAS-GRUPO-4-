FROM python:3.11-slim

# Evitar que Python almacene en búfer stdout/stderr (para ver logs en tiempo real)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instalar dependencias aprovechando la caché de capas de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente
COPY main.py .

# Exponer el puerto de Uvicorn
EXPOSE 28000

# IMPORTANTE: --workers 1 porque el estado del simulador reside en memoria global
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "28000", "--workers", "1"]