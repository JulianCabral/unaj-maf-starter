"""API de solo lectura y datos ficticios. No es un servicio de la UNAJ."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MATERIAS = {
    "INF101": {"codigo": "INF101", "nombre": "Programacion de ejemplo", "cupos": 12},
    "MAT101": {"codigo": "MAT101", "nombre": "Matematica de ejemplo", "cupos": 0},
}


class APIPractica(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        materia = MATERIAS.get(self.path.removeprefix("/materias/"))
        if not self.path.startswith("/materias/") or materia is None:
            self.responder(404, {"error": "materia_no_encontrada"})
            return
        self.responder(200, materia)

    def responder(self, estado: int, datos: dict) -> None:
        contenido = json.dumps(datos).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(contenido)))
        self.end_headers()
        self.wfile.write(contenido)

    def log_message(self, format: str, *args: object) -> None:
        # No registrar URLs ni cabeceras enviadas por clientes.
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", type=int, default=8000)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.puerto), APIPractica) as servidor:
        print(f"API ficticia: http://127.0.0.1:{servidor.server_port}/materias/INF101")
        print("Solo lectura, sin autenticacion. Ctrl+C para terminar.", flush=True)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
