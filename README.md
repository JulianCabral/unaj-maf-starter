# UNAJ · Starter de agentes con MAF

Base educativa en Python para que construyas **tu propio agente y su harness** con
Microsoft Agent Framework (MAF). No es un trabajo práctico resuelto ni un sistema
académico real. No requiere cuenta de Azure, tarjeta ni Azure CLI.

El ejemplo consulta cupos **inventados**, mediante una herramienta HTTP de backend:

```text
Consulta → agente MAF → herramienta consultar_materia(codigo)
                            ↓
                  GET a una API controlada
                            ↓
                     datos validados → respuesta
```

El modelo propone una llamada; **tu código decide qué se puede ejecutar**.
Un prompt que diga “no hagas X” no reemplaza permisos, validación ni límites.

## 1. Qué incluye y qué te toca construir

| Provisto y ejecutable | Pendiente para tu proyecto |
|---|---|
| Agente MAF de una consulta, sin memoria persistente | Objetivo, instrucciones y herramientas de tu dominio |
| API local de solo lectura con dos materias ficticias | Integración con tu API y datos autorizados |
| Código validado y URL configurada fuera del prompt | Identidad del usuario y autorización por recurso |
| Dos intentos de herramienta por ejecución | Política de permisos y aprobación de operaciones sensibles |
| Timeouts, errores explícitos y trazas mínimas sin cuerpos ni claves | Trazas correlacionadas, evaluación y pruebas de tu harness |

La API local **no autentica usuarios** y escucha solo en `127.0.0.1`. No la expongas
a Internet. No hay inscripciones, escrituras, interfaz web, despliegue ni ejemplo
de voz en este starter. La sección de voz del JSON privado no se usa.

## 2. Instalación

Requisitos: **Python 3.11 o posterior** (verificado localmente con Python 3.13),
Git e Internet para instalar paquetes. Las pruebas posteriores no usan servicios
pagos. Desde PowerShell:

```powershell
git clone https://github.com/JulianCabral/unaj-maf-starter.git
cd unaj-maf-starter
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No hace falta activar el entorno ni cambiar la política de ejecución de PowerShell.
En Linux/macOS, reemplazá `.\.venv\Scripts\python.exe` por `.venv/bin/python`.

Las versiones directas están fijadas en `requirements.txt`: MAF OpenAI 1.18.1,
MAF Core 1.25.0, HTTPX 0.28.1, OpenAI 3.49.0 y Pydantic 2.14.3.
No es un lock completo de dependencias transitivas.
MAF evoluciona: no mezcles sin revisar ejemplos de otras versiones.

## 3. Primero probá la API, sin claves ni modelo

En una terminal, desde la carpeta del proyecto:

```powershell
.\.venv\Scripts\python.exe api_practica.py
```

En otra terminal, desde esa misma carpeta:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/materias/INF101
Invoke-RestMethod http://127.0.0.1:8000/materias/MAT101
```

`INF101` devuelve `{"codigo":"INF101","nombre":"Programacion de ejemplo","cupos":12}`;
`MAT101` tiene cero cupos. Un código inexistente devuelve HTTP 404. Son datos
ficticios, no información de estudiantes ni de la universidad. Detené la API con
Ctrl+C al terminar.

## 4. Credenciales privadas

El docente entrega **`credenciales-unaj.json` por un canal privado**, fuera del
repositorio. Guardalo en la carpeta del proyecto (está ignorado por Git), o usá:

```powershell
.\.venv\Scripts\python.exe agente.py "Cupos de INF101" --credenciales "C:\carpeta-privada\credenciales-unaj.json"
```

`credenciales-unaj.example.json` es **solo una plantilla con placeholders**, no
una clave funcional. La estructura incluye `texto` y `voz` por compatibilidad con
el material del curso; este código solo lee `texto`.

Alternativa: definir `UNAJ_API_KEY` en el entorno del proceso. Tiene prioridad
sobre el JSON; nunca escribas su valor real en un comando que vayas a publicar.
No se cargan archivos `.env` automáticamente. No habilites logs HTTP de depuración.

Configuración pública de texto:

| Campo | Valor |
|---|---|
| URL base | `https://unaj-aigw-ih24ukgp4wvd6.eastus2-01.ai.gateway.azure.com/default/models/openai/v1` |
| Alias enviado como `model` | `unaj-text` |
| Modelo de backend | GPT-4.1-mini |
| Autenticación | `Authorization: Bearer <clave gateway>` |
| Operación | `POST /chat/completions` |

`agente.py` usa `OpenAIChatCompletionClient`, **no `OpenAIChatClient`**, que en la
versión fijada usa Responses API. No suponemos que el gateway soporte Responses.
El SDK OpenAI conserva la clave en el backend e incorpora la cabecera Bearer.

No subas claves, JSON privados, audios ni datos personales a Git, prompts,
capturas o entregas. `.gitignore` no protege un archivo ya versionado.
Si se filtra una clave, avisá al docente para revocarla: borrar el archivo no basta.
Las claves compartidas **no identifican confiablemente a cada alumno**.

## 5. Ejecutá el agente

Con la API de la sección 3 todavía en ejecución y tu clave privada configurada:

```powershell
.\.venv\Scripts\python.exe agente.py "Consultá los cupos ficticios de INF101."
.\.venv\Scripts\python.exe agente.py "¿Quedan cupos en MAT101?"
```

Estas consultas **sí consumen el servicio de texto**. La selección de herramienta
depende del modelo; no es una ruta determinista. No afirmes que ocurrió una acción
solo porque el texto del modelo lo dice. Usá trazas y pruebas para comprobarla.

El código esencial está en `crear_agente()`:

```python
cliente = OpenAIChatCompletionClient(
    model=MODELO,
    async_client=sdk,
    function_invocation_configuration={
        "max_iterations": 3,
        "max_function_calls": 2,
        "include_detailed_errors": False,
        "allow_concurrent_invocation": False,
    },
)
agente = Agent(
    client=cliente,
    instructions="Tus instrucciones de dominio...",
    tools=[herramientas.consultar_materia],
    default_options={"max_tokens": 300},
)
respuesta = await agente.run(pregunta)
```

MAF genera el esquema de la función Python, interpreta las llamadas del modelo y
le devuelve sus resultados. No hace falta darle una herramienta HTTP genérica.
El programa completo también cierra clientes HTTP y configura el SDK sin reintentos.

## 6. Qué hace el harness mínimo

El **harness** es el código que rodea al modelo y controla la ejecución. Acá está
repartido entre `agente.py`, `configuracion.py` y `herramientas.py`, para poder leerlo
sin una arquitectura grande:

| Control real | Alcance |
|---|---|
| Entrada no vacía, hasta 2000 caracteres | Antes de leer claves o llamar al modelo |
| Código con patrón `AAA999` | Antes del HTTP; no admite URLs ni rutas arbitrarias |
| URL del operador, una ruta GET fija | HTTPS remoto o HTTP local; sin credenciales en URL ni redirecciones |
| Presupuesto de dos intentos de herramienta | Incluye códigos inválidos y errores; se reinicia por ejecución |
| Bucle MAF acotado a tres iteraciones | No es una cuota monetaria; MAF puede hacer una consulta final sin herramientas |
| Tres segundos por operación HTTP de la API | Lectura, conexión, escritura y espera del pool |
| Veinte segundos por operación HTTP del modelo; 45 segundos totales | Timeout local; cancelar no garantiza cancelar el cómputo remoto ni su costo |
| 300 tokens de salida por respuesta del modelo | MAF traduce `max_tokens` a `max_completion_tokens` en HTTP |
| Respuesta de API hasta 4096 bytes y esquema estricto | No se reenvía un cuerpo HTTP arbitrario al modelo |
| Errores estables, por ejemplo `api_timeout` o `materia_no_encontrada` | `ok: false` visible al modelo; nunca simula datos correctos |
| Trazas de herramienta con intento y estado | No guardan prompts, cabeceras, claves ni respuestas completas |

Los timeouts HTTP son por operación, no un presupuesto global de la red. Un
servidor lento se corta además por el timeout total de la ejecución del agente.
Los mensajes técnicos crudos del proveedor no se imprimen: pueden contener datos
de la solicitud. Los errores inesperados de programación no se ocultan.

**No incluye autorización por usuario, aislamiento multiusuario, aprobación de
escrituras, auditoría durable ni un sandbox.** La validación reduce riesgos, pero
no resuelve por sí sola la inyección de instrucciones. La URL configurada debe
ser confiable; en producción agregá una lista de destinos permitidos y controles
de salida de red, no aceptes `PRACTICA_API_URL` de un usuario o del modelo.

## 7. Cómo conectar tu propia API

1. Elegí una operación pequeña de solo lectura, con permiso para usar sus datos.
2. Escribí una función de backend con argumentos de dominio, como
   `consultar_pedido(numero)`, no `hacer_http(url, metodo, headers)`.
3. Configurá un origen confiable fuera del prompt, validá argumentos y respuesta,
   y convertí errores a códigos explícitos. No devuelvas cuerpos de error privados.
4. Autenticá el backend ante la API y verificá además qué usuario puede acceder a
   cada recurso. Una clave del curso no reemplaza esa identidad.
5. Registrá solo esa función en `tools` y agregá pruebas con respuestas simuladas.

Para una API **con el mismo contrato** `GET /materias/{codigo}`, podés cambiar
`PRACTICA_API_URL` en el entorno:

```powershell
$env:PRACTICA_API_URL = "https://api-de-practica.example"
```

Ese dominio es ilustrativo, no un servicio real. Para otro contrato, adaptá
`_consultar()` y el esquema `Materia`. `PRACTICA_API_TOKEN`, si existe, se añade
como Bearer **solo al cliente de tu API**, nunca al cliente del modelo ni a sus
mensajes. La API local no lo necesita ni lo valida.

No reutilices la clave del gateway como token de tu API. No copies credenciales
al docstring de herramientas, instrucciones ni resultados. No aceptes cabeceras
o tokens propuestos por el modelo.

## 8. Consignas para construir tu propio harness

No están resueltas en el starter. Entregá código, pruebas y una explicación breve
de tus decisiones, **sin credenciales ni datos privados**.

| Consigna | Evidencia esperada |
|---|---|
| Definir agente y contrato de dos herramientas propias | Objetivo, entradas, salidas y casos en que no debe responder |
| Agregar identidad y autorización en backend | Un usuario autorizado accede; otro no, aunque el modelo lo pida |
| Agregar aprobación para una operación de escritura simulada | Rechazo, aprobación y argumentos modificados invalidados |
| Diseñar presupuestos de pasos, tokens y tiempo | Un modelo insistente termina; los fallos también consumen presupuesto |
| Mejorar trazas con un ID de ejecución | Reconstruir qué se invocó sin registrar secretos ni datos personales |
| Crear una evaluación de al menos cinco consultas | Caso normal, dato ausente, API caída, sin permiso e inyección en datos |

Antes de programar escrituras reales, usá dobles de prueba. Definí idempotencia,
confirmación humana y qué ocurre si la API ejecuta una acción pero se pierde su
respuesta. No hagas reintentos automáticos de acciones sin resolver ese caso.

## 9. Pruebas sin secretos ni cargos

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las pruebas usan **MAF y el SDK OpenAI reales**, un transporte de modelo simulado
y una API HTTP en loopback con puerto efímero. Comprueban el ciclo de herramienta
de extremo a extremo, el contrato Chat Completions/Bearer, validación, presupuesto,
404, fallos HTTP, timeout, desconexión y respuestas inválidas.

No leen el JSON real ni hacen inferencia pagada. La prueba del modelo simulado
**no verifica conectividad, disponibilidad, calidad ni tool calling contra el
gateway real**. Esa comprobación queda para una ejecución manual autorizada con
la clave privada. No uses las pruebas como prueba de funcionamiento de Azure.

## 10. Presupuesto del curso y errores frecuentes

**Texto tiene un único límite COMPARTIDO del curso de USD 100 estimados al mes por
AI Gateway, no por alumno.** Es un control estimado post-respuesta:
concurrencia, precios y datos de uso pueden causar sobrepaso.
**NO es un techo exacto de factura.**

**Voz MAI Speech está fuera de ese límite por decisión del docente y no tiene un
tope monetario configurado.** No prometemos control monetario de voz.
Los cargos de gateway y telemetría tampoco están incluidos en el límite de texto.
No ejecutes pruebas de carga ni bucles pagos sin autorización.

| Síntoma | Acción |
|---|---|
| Falta clave o JSON inválido | Pedí el archivo privado al docente; la plantilla no sirve para autenticar |
| HTTP 401 del modelo | Revisá la clave de texto vigente, no la de voz |
| HTTP 403 con `cost quota` | Avisá al docente: se agotó la cuota compartida; no insistas |
| Otro HTTP 403 | Revisá permisos o políticas con el docente |
| HTTP 429 | Esperá; no agregues reintentos en bucle |
| Modelo o ruta no encontrados | Revisá `unaj-text`, URL completa y Chat Completions |
| `api_no_disponible` | Iniciá la API local y revisá puerto/origen configurado |
| `codigo_invalido` / `materia_no_encontrada` | Usá INF101 o MAT101 para el ejemplo |
| `limite_de_herramientas` o timeout total | Revisá la consulta y las trazas; no elimines límites para “arreglarlo” |

Para pedir ayuda, compartí el comando **sin claves**, la versión de Python y el
error saneado. El CLI oculta detalles crudos del proveedor por seguridad; si
necesitás diagnosticar el estado HTTP, hacelo en un entorno privado con el docente.

## 11. Guía HTML offline y archivos

Abrí `index.html` con tu navegador, sin servidor ni conexión. Es una copia legible
del mismo README, sin scripts, CDN ni contenido externo. **README.md es la fuente**:
después de editarlo, regenerá y versioná el HTML:

```powershell
.\.venv\Scripts\python.exe generar_guia.py
```

| Archivo | Propósito |
|---|---|
| `agente.py` | Cliente de texto, agente MAF y límites de ejecución |
| `herramientas.py` | Herramienta HTTP acotada, validación y errores |
| `api_practica.py` | Servidor local ficticio, solo lectura |
| `configuracion.py` | Lectura de la clave privada sin imprimirla |
| `credenciales-unaj.example.json` | Plantilla sin secretos |
| `tests/test_starter.py` | Pruebas offline con dobles del modelo |
| `generar_guia.py`, `index.html` | Generador y guía offline |

## Referencias oficiales

- MAF OpenAI: https://github.com/microsoft/agent-framework/tree/main/python/packages/openai
- Ejemplos MAF: https://github.com/microsoft/agent-framework/tree/main/python/samples
- Paquete y versiones: https://pypi.org/project/agent-framework-openai/
- SDK OpenAI Python: https://github.com/openai/openai-python
- Límites estimados de AI Gateway: https://ai.gateway.azure.com/docs/finops

Las referencias a `main` pueden cambiar. Para reproducir este starter usá las
versiones de `requirements.txt`, no imports copiados de ejemplos de otra versión.
