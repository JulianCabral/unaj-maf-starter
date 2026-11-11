import json
import os
from pathlib import Path

BASE_URL = (
    "https://unaj-aigw-ih24ukgp4wvd6.eastus2-01.ai.gateway.azure.com"
    "/default/models/openai/v1"
)
MODELO = "unaj-text"


def cargar_clave(ruta: Path) -> str:
    clave = os.environ.get("UNAJ_API_KEY")
    if clave is None:
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ValueError(
                "No se pudo leer el JSON privado. Usá --credenciales o UNAJ_API_KEY."
            ) from None
        if not isinstance(datos, dict) or not isinstance(datos.get("texto"), dict):
            raise ValueError("El JSON debe contener un objeto texto.") from None
        texto = datos["texto"]
        if texto.get("base_url") != BASE_URL or texto.get("model") != MODELO:
            raise ValueError("Revisá base_url y model de texto con el docente.")
        clave = texto.get("api_key")
    if not isinstance(clave, str) or not clave.strip() or clave.startswith("<"):
        raise ValueError("Falta una clave de texto válida; pedila al docente.")
    return clave.strip()
