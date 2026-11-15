"""Transformaciones básicas antes de guardar los episodios."""

from copy import deepcopy
import hashlib
import hmac
import math
import re

from config import settings


LONGITUD_HASH = 32  # Caracteres hexadecimales: 128 bits.
INTERVALO_EDAD = 10
CAMPOS_SIP = {"sip_paciente", "sip"}
AUSENCIAS = {"", "n/d", "s/d", "error", "pendiente", "none", "null", "nan"}


def obtener_clave():
    """Lee una clave de 32 bytes, expresada como 64 caracteres hexadecimales."""
    valor = settings.ANON_HMAC_KEY.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", valor):
        raise ValueError(
            "ANON_HMAC_KEY debe contener 64 caracteres hexadecimales. "
            "Configura esta clave en docker/.env antes de ejecutar el programa."
        )
    return bytes.fromhex(valor)


def anonimizar_sip(sip, clave=None):
    """Devuelve un HMAC truncado del SIP normalizado; las ausencias quedan nulas."""
    clave = obtener_clave() if clave is None else clave
    if sip is None:
        return None
    texto = str(sip).strip()
    if texto.lower() in AUSENCIAS:
        return None
    return hmac.new(
        clave, texto.upper().encode("utf-8"), hashlib.sha256
    ).hexdigest()[:LONGITUD_HASH]


def agrupar_edad(edad):
    """Agrupa edades enteras de 0 a 120; los valores inválidos quedan nulos."""
    if edad is None or isinstance(edad, bool):
        return None
    try:
        numero = float(edad)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numero) or not numero.is_integer() or not 0 <= numero <= 120:
        return None
    inicio = int(numero) // INTERVALO_EDAD * INTERVALO_EDAD
    return f"[{inicio}-{inicio + INTERVALO_EDAD - 1}]"


def anonimizar_documento(documento):
    """Recibe un documento ORIGINAL y devuelve una copia con sus datos protegidos."""
    if not isinstance(documento, dict):
        raise TypeError("Se esperaba un documento de episodio.")
    clave = obtener_clave()

    def transformar(valor):
        if isinstance(valor, dict):
            resultado = {}
            for campo, contenido in valor.items():
                if campo == "nombre":
                    continue
                if campo in CAMPOS_SIP:
                    resultado[campo] = anonimizar_sip(contenido, clave)
                elif campo == "edad":
                    resultado[campo] = agrupar_edad(contenido)
                else:
                    resultado[campo] = transformar(contenido)
            return resultado
        if isinstance(valor, list):
            return [transformar(contenido) for contenido in valor]
        return deepcopy(valor)

    return transformar(documento)
