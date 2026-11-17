import os
from pathlib import Path
from dotenv import load_dotenv

# En local se lee docker/.env; en Docker estas variables llegan mediante env_file.
# Las variables que ya existan en el entorno tienen prioridad.
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ_PROYECTO / "docker" / ".env")

class Config:
    # =============================================
    # CONFIGURACIÓN DE MONGO DB
    # =============================================
    MONGO_IMAGE_VERSION: str = os.getenv("MONGO_IMAGE_VERSION", "mongo:6.0")
    MONGO_CONTAINER_NAME: str = os.getenv("MONGO_CONTAINER_NAME", "mongo")
    MONGO_PORT: int = int(os.getenv("MONGO_PORT", 27017))
    MONGO_DATA_PATH: str = os.getenv("MONGO_DATA_PATH", "./mongo_data")
    MONGO_URI: str = os.getenv("MONGO_URI","mongodb://root:secret@mongo:27017/admin?authSource=admin")
    MONGO_DATABASE: str = os.getenv("MONGO_DATABASE", "urgencias")
    MONGO_COLLECTION: str = os.getenv("MONGO_COLLECTION", "episodios_urgencias")

    # Autenticación de MongoDB
    MONGO_INITDB_ROOT_USERNAME: str = os.getenv("MONGO_INITDB_ROOT_USERNAME", "root")
    MONGO_INITDB_ROOT_PASSWORD: str = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "secret")
    MONGO_INITDB_DATABASE: str = os.getenv("MONGO_INITDB_DATABASE", "admin")

    # =============================================
    # CONFIGURACIÓN DE MONGO EXPRESS
    # =============================================
    MONGO_EXPRESS_IMAGE_VERSION: str = os.getenv("MONGO_EXPRESS_IMAGE_VERSION", "mongo-express:1.0.2")
    MONGO_EXPRESS_CONTAINER_NAME: str = os.getenv("MONGO_EXPRESS_CONTAINER_NAME", "mongo-express")
    MONGO_EXPRESS_PORT: int = int(os.getenv("MONGO_EXPRESS_PORT", 8081))

    # Autenticación Mongo Express
    ME_CONFIG_BASICAUTH_USERNAME: str = os.getenv("ME_CONFIG_BASICAUTH_USERNAME", "admin")
    ME_CONFIG_BASICAUTH_PASSWORD: str = os.getenv("ME_CONFIG_BASICAUTH_PASSWORD", "paso")

    # Conexión MongoDB para Express
    ME_CONFIG_MONGODB_ADMINUSERNAME: str = os.getenv("ME_CONFIG_MONGODB_ADMINUSERNAME", "root")
    ME_CONFIG_MONGODB_ADMINPASSWORD: str = os.getenv("ME_CONFIG_MONGODB_ADMINPASSWORD", "secret")
    ME_CONFIG_MONGODB_SERVER: str = os.getenv("ME_CONFIG_MONGODB_SERVER", "mongo")
    ME_CONFIG_MONGODB_PORT: int = int(os.getenv("ME_CONFIG_MONGODB_PORT", 27017))
    ME_CONFIG_MONGODB_ENABLE_ADMIN: bool = os.getenv("ME_CONFIG_MONGODB_ENABLE_ADMIN", "true").lower() in ("true", "1", "yes")

    # =============================================
    # RED E INFRAESTRUCTURA
    # =============================================
    DOCKER_NETWORK_NAME: str = os.getenv("DOCKER_NETWORK_NAME", "shared-network")

    # =============================================
    # SEGURIDAD Y CONFIGURACIONES ADICIONALES
    # =============================================
    MONGO_INITDB_REPLICA_SET: str | None = os.getenv("MONGO_INITDB_REPLICA_SET")
    MONGO_KEYFILE_PATH: str | None = os.getenv("MONGO_KEYFILE_PATH")

    # =============================================
    # CONFIGURACIÓN DE LA APLICACIÓN
    # =============================================
    API_URL: str = os.getenv("API_URL", "http://api_urgencias_carestream:28000/api/v1/urgencias/novedades")
    URL_INSTITUTO: str = os.getenv("URL_INSTITUTO", "http://10.201.59.244:8080")
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(RAIZ_PROYECTO / "data")))

    # Clave privada de 32 bytes en hexadecimal, sin un secreto público por defecto.
    ANON_HMAC_KEY: str = os.getenv("ANON_HMAC_KEY", "")

    # =============================================
    # HELPER: URI DE CONEXIÓN LISTA PARA USAR (PyMongo / Motor)
    # =============================================
    @classmethod
    def get_mongo_uri(cls, host: str = None) -> str:
        """
        Genera la cadena de conexión a MongoDB.
        Usa 'localhost' si ejecutas Python fuera de Docker, 
        o 'mongo' (ME_CONFIG_MONGODB_SERVER) si Python corre dentro de Docker.
        """
        target_host = host or cls.ME_CONFIG_MONGODB_SERVER
        return (
            f"mongodb://{cls.MONGO_INITDB_ROOT_USERNAME}:{cls.MONGO_INITDB_ROOT_PASSWORD}"
            f"@{target_host}:{cls.MONGO_PORT}/{cls.MONGO_INITDB_DATABASE}?authSource=admin"
        )

# Instancia lista para importar en cualquier parte del proyecto
settings = Config()
