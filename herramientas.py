import json
import logging
import re
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("unaj.herramientas")


class Materia(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    codigo: str = Field(pattern=r"^[A-Z]{3}[0-9]{3}$")
    nombre: str = Field(min_length=1, max_length=120)
    cupos: int = Field(ge=0, le=10000)


class ErrorAPI(Exception):
    pass


def validar_base_url(base_url: str) -> str:
    partes = urlsplit(base_url)
    local = partes.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        not partes.hostname
        or partes.username is not None
        or partes.password is not None
        or partes.query
        or partes.fragment
        or partes.path not in {"", "/"}
        or (partes.scheme != "https" and not (partes.scheme == "http" and local))
    ):
        raise ValueError("PRACTICA_API_URL debe ser un origen HTTPS o HTTP local.")
    # La URL viene del operador, nunca de argumentos generados por el modelo.
    return base_url.rstrip("/")


class Herramientas:
    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self.http = http
        self.base_url = validar_base_url(base_url)
        self.llamadas = 0

    async def consultar_materia(self, codigo: str) -> dict:
        """Consulta cupos ficticios por codigo, por ejemplo INF101 o MAT101."""
        self.llamadas += 1
        error = None
        if self.llamadas > 2:
            error = "limite_de_herramientas"
        elif not isinstance(codigo, str) or re.fullmatch(r"[A-Z]{3}[0-9]{3}", codigo) is None:
            error = "codigo_invalido"
        else:
            try:
                materia = await self._consultar(codigo)
            except ErrorAPI as exc:
                error = str(exc)
            else:
                logger.info("herramienta=consultar_materia intento=%d estado=ok", self.llamadas)
                return {"ok": True, "materia": materia.model_dump()}
        logger.warning(
            "herramienta=consultar_materia intento=%d estado=%s", self.llamadas, error
        )
        return {"ok": False, "error": error}

    async def _consultar(self, codigo: str) -> Materia:
        try:
            async with self.http.stream(
                "GET",
                f"{self.base_url}/materias/{codigo}",
                timeout=3.0,
                follow_redirects=False,
            ) as respuesta:
                if respuesta.status_code == 404:
                    raise ErrorAPI("materia_no_encontrada")
                if respuesta.status_code != 200:
                    raise ErrorAPI("api_http_error")
                contenido = bytearray()
                async for bloque in respuesta.aiter_bytes():
                    contenido.extend(bloque)
                    if len(contenido) > 4096:
                        raise ErrorAPI("respuesta_demasiado_grande")
            materia = Materia.model_validate(json.loads(contenido))
            if materia.codigo != codigo:
                raise ErrorAPI("respuesta_invalida")
            return materia
        except httpx.TimeoutException:
            raise ErrorAPI("api_timeout") from None
        except httpx.RequestError:
            raise ErrorAPI("api_no_disponible") from None
        except ValueError:
            raise ErrorAPI("respuesta_invalida") from None
