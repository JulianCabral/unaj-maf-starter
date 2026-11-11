import asyncio
import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI

from agente import crear_agente, ejecutar, main
from api_practica import APIPractica
from configuracion import BASE_URL, MODELO, cargar_clave
from herramientas import Herramientas, validar_base_url
from generar_guia import generar


class ConfiguracionTests(unittest.TestCase):
    def test_json_privado_y_variable_sin_leer_archivo(self):
        with tempfile.TemporaryDirectory() as carpeta, patch.dict(os.environ, {}, clear=True):
            ruta = Path(carpeta) / "privado.json"
            ruta.write_text(json.dumps({"texto": {
                "base_url": BASE_URL, "model": MODELO, "api_key": "clave-de-prueba"
            }}), encoding="utf-8")
            self.assertEqual(cargar_clave(ruta), "clave-de-prueba")
            ruta.write_text("no es json", encoding="utf-8")
            with self.assertRaises(ValueError):
                cargar_clave(ruta)
            os.environ["UNAJ_API_KEY"] = "variable-de-prueba"
            self.assertEqual(cargar_clave(ruta), "variable-de-prueba")

    def test_plantilla_no_es_una_credencial(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "clave de texto"):
                cargar_clave(Path("credenciales-unaj.example.json"))

    def test_url_no_puede_incluir_credenciales_ni_destino_http_remoto(self):
        for url in (
            "http://example.org", "https://usuario:secreto@example.org",
            "https://example.org/ruta", "https://example.org?token=secreto",
            "file:///etc/passwd",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validar_base_url(url)

    def test_guia_html_no_se_desincroniza(self):
        self.assertEqual(Path("index.html").read_text(encoding="utf-8"), generar())


class HerramientasTests(unittest.IsolatedAsyncioTestCase):
    async def test_validacion_y_presupuesto_antes_de_http(self):
        solicitudes = []

        def responder(request):
            solicitudes.append(request)
            return httpx.Response(200, json={
                "codigo": "INF101", "nombre": "Ejemplo", "cupos": 12
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http:
            herramientas = Herramientas(http, "http://127.0.0.1:8000")
            self.assertEqual(
                (await herramientas.consultar_materia("../../secretos"))["error"],
                "codigo_invalido",
            )
            self.assertTrue((await herramientas.consultar_materia("INF101"))["ok"])
            self.assertEqual(
                (await herramientas.consultar_materia("INF101"))["error"],
                "limite_de_herramientas",
            )
        self.assertEqual(len(solicitudes), 1)

    async def test_errores_http_y_respuestas_no_confiables(self):
        casos = [
            (httpx.Response(404), "materia_no_encontrada"),
            (httpx.Response(401, text="no exponer cuerpo privado"), "api_http_error"),
            (httpx.Response(500), "api_http_error"),
            (httpx.Response(302, headers={"Location": "http://otro/"}), "api_http_error"),
            (httpx.Response(200, text="no-json"), "respuesta_invalida"),
            (httpx.Response(200, content=b"x" * 4097), "respuesta_demasiado_grande"),
            (httpx.Response(200, json={
                "codigo": "INF101", "nombre": "Ejemplo", "cupos": "12"
            }), "respuesta_invalida"),
            (httpx.Response(200, json={
                "codigo": "MAT101", "nombre": "Ejemplo", "cupos": 1
            }), "respuesta_invalida"),
        ]
        for respuesta, esperado in casos:
            with self.subTest(esperado=esperado):
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda request: respuesta)
                ) as http:
                    resultado = await Herramientas(http, "https://api.example").consultar_materia("INF101")
                    self.assertEqual(resultado, {"ok": False, "error": esperado})

    async def test_timeout_y_desconexion(self):
        for excepcion, esperado in (
            (httpx.ReadTimeout("detalle privado"), "api_timeout"),
            (httpx.ConnectError("detalle privado"), "api_no_disponible"),
        ):
            def fallar(request):
                raise excepcion

            async with httpx.AsyncClient(transport=httpx.MockTransport(fallar)) as http:
                resultado = await Herramientas(http, "https://api.example").consultar_materia("INF101")
                self.assertEqual(resultado, {"ok": False, "error": esperado})

    async def test_dos_invocaciones_concurrentes_respetan_presupuesto(self):
        contador = 0

        async def responder(request):
            nonlocal contador
            contador += 1
            await asyncio.sleep(0)
            return httpx.Response(200, json={
                "codigo": "INF101", "nombre": "Ejemplo", "cupos": 12
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http:
            herramientas = Herramientas(http, "https://api.example")
            resultados = await asyncio.gather(*(
                herramientas.consultar_materia("INF101") for _ in range(3)
            ))
        self.assertEqual(contador, 2)
        self.assertEqual(sum(r["ok"] for r in resultados), 2)


class IntegracionTests(unittest.IsolatedAsyncioTestCase):
    async def test_modelo_insistente_no_produce_bucle_ilimitado(self):
        llamadas_modelo = 0
        llamadas_api = 0

        def responder_api(request):
            nonlocal llamadas_api
            llamadas_api += 1
            return httpx.Response(200, json={
                "codigo": "INF101", "nombre": "Ejemplo", "cupos": 12
            })

        def modelo_insistente(request):
            nonlocal llamadas_modelo
            llamadas_modelo += 1
            self.assertLessEqual(llamadas_modelo, 4)
            cuerpo = json.loads(request.content)
            if cuerpo.get("tools") and cuerpo.get("tool_choice") != "none":
                nombre = cuerpo["tools"][0]["function"]["name"]
                mensaje = {"role": "assistant", "content": None, "tool_calls": [{
                    "id": f"call_{llamadas_modelo}", "type": "function",
                    "function": {"name": nombre, "arguments": '{"codigo":"INF101"}'},
                }]}
                fin = "tool_calls"
            else:
                mensaje = {"role": "assistant", "content": "Fin por limite."}
                fin = "stop"
            return httpx.Response(200, json={
                "id": "chatcmpl-limite", "object": "chat.completion", "created": 0,
                "model": MODELO, "choices": [{
                    "index": 0, "message": mensaje, "finish_reason": fin
                }],
            })

        async with (
            httpx.AsyncClient(transport=httpx.MockTransport(responder_api)) as api,
            httpx.AsyncClient(transport=httpx.MockTransport(modelo_insistente)) as modelo,
            AsyncOpenAI(
                api_key="clave-ficticia", base_url="https://modelo.example/v1",
                max_retries=0, http_client=modelo,
            ) as sdk,
        ):
            async with asyncio.timeout(2):
                await crear_agente(sdk, Herramientas(api, "https://api.example")).run("Insisti")
        self.assertEqual(llamadas_api, 2)
        self.assertLessEqual(llamadas_modelo, 4)

    async def test_cli_no_reintenta_401_ni_expone_error_del_proveedor(self):
        contador = 0

        def denegar(request):
            nonlocal contador
            contador += 1
            return httpx.Response(401, json={"error": {
                "message": "detalle-privado-no-publicar", "type": "authentication_error"
            }})

        async with httpx.AsyncClient(transport=httpx.MockTransport(denegar)) as modelo:
            def sdk_de_prueba(**kwargs):
                kwargs["http_client"] = modelo
                return AsyncOpenAI(**kwargs)

            with (
                patch.dict(os.environ, {"UNAJ_API_KEY": "clave-ficticia"}, clear=True),
                patch("agente.AsyncOpenAI", side_effect=sdk_de_prueba),
                patch("sys.argv", ["agente.py", "Hola"]),
                contextlib.redirect_stderr(io.StringIO()) as salida,
            ):
                codigo = await asyncio.to_thread(main)
        self.assertEqual(codigo, 1)
        self.assertEqual(contador, 1)
        self.assertIn("Error del modelo", salida.getvalue())
        self.assertNotIn("detalle-privado", salida.getvalue())
        self.assertNotIn("clave-ficticia", salida.getvalue())

    async def test_maf_chat_completions_herramienta_y_api_local(self):
        servidor = ThreadingHTTPServer(("127.0.0.1", 0), APIPractica)
        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        solicitudes = []

        def modelo_falso(request):
            self.assertEqual(request.url.path, "/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer clave-ficticia")
            cuerpo = json.loads(request.content)
            solicitudes.append(cuerpo)
            self.assertEqual(cuerpo["model"], MODELO)
            self.assertEqual(cuerpo["max_completion_tokens"], 300)
            self.assertNotIn("clave-ficticia", request.content.decode())
            self.assertNotIn("token-api-ficticio", request.content.decode())
            if len(solicitudes) == 1:
                nombre = cuerpo["tools"][0]["function"]["name"]
                mensaje = {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"name": nombre, "arguments": '{"codigo":"INF101"}'},
                }]}
                fin = "tool_calls"
            else:
                resultados = [m for m in cuerpo["messages"] if m["role"] == "tool"]
                self.assertEqual(len(resultados), 1)
                self.assertIn('"cupos": 12', resultados[0]["content"])
                mensaje = {"role": "assistant", "content": "Hay 12 cupos ficticios."}
                fin = "stop"
            return httpx.Response(200, json={
                "id": "chatcmpl-prueba", "object": "chat.completion", "created": 0,
                "model": MODELO, "choices": [{
                    "index": 0, "message": mensaje, "finish_reason": fin
                }],
            })

        try:
            async with (
                httpx.AsyncClient(trust_env=False, headers={
                    "Authorization": "Bearer token-api-ficticio"
                }) as api,
                httpx.AsyncClient(transport=httpx.MockTransport(modelo_falso)) as transporte,
                AsyncOpenAI(
                    api_key="clave-ficticia", base_url="https://modelo.example/v1",
                    max_retries=0, http_client=transporte,
                ) as sdk,
            ):
                herramientas = Herramientas(api, f"http://127.0.0.1:{servidor.server_port}")
                respuesta = await crear_agente(sdk, herramientas).run("Cupos de INF101")
                self.assertEqual(respuesta.text, "Hay 12 cupos ficticios.")
                self.assertEqual(herramientas.llamadas, 1)
                self.assertEqual(len(solicitudes), 2)
                no_existe = await herramientas.consultar_materia("ZZZ999")
                self.assertEqual(no_existe["error"], "materia_no_encontrada")
        finally:
            await asyncio.to_thread(servidor.shutdown)
            servidor.server_close()
            hilo.join()

    async def test_entrada_invalida_no_lee_claves_ni_invoca_modelo(self):
        for pregunta in ("", " " * 3, "a" * 2001):
            with self.subTest(pregunta=pregunta[:10]), self.assertRaises(ValueError):
                await ejecutar(pregunta, Path("archivo-que-no-existe.json"))

    async def test_cli_falla_sin_credenciales_sin_imprimir_secretos(self):
        with (
            patch.dict(os.environ, {"UNAJ_API_KEY": "<placeholder>"}, clear=True),
            patch("sys.argv", ["agente.py", "Hola"]),
            contextlib.redirect_stderr(io.StringIO()) as salida,
        ):
            # main() inicia su propio event loop.
            codigo = await asyncio.to_thread(main)
        self.assertEqual(codigo, 1)
        self.assertNotIn("<placeholder>", salida.getvalue())


if __name__ == "__main__":
    unittest.main()
