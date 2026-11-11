"""Genera una guia offline desde README.md, usando solo la biblioteca estandar."""

from html import escape
from pathlib import Path


def generar() -> str:
    raiz = Path(__file__).resolve().parent
    texto = escape((raiz / "README.md").read_text(encoding="utf-8"))
    return (
        '<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>UNAJ - Starter MAF</title>\n"
        "<style>body{max-width:1000px;margin:2rem auto;padding:0 1rem;"
        "color:#182230;background:#fafafa}pre{white-space:pre-wrap;"
        "overflow-wrap:anywhere;line-height:1.6;font-size:15px;"
        "font-family:ui-monospace,Consolas,monospace}"
        "@media print{body{max-width:none;margin:0}pre{font-size:10px}}</style>\n"
        "</head>\n<body><main><pre>"
        f"{texto}</pre></main></body>\n</html>\n"
    )


if __name__ == "__main__":
    destino = Path(__file__).resolve().parent / "index.html"
    destino.write_text(generar(), encoding="utf-8")
    print("index.html actualizado desde README.md")
