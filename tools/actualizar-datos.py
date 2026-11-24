#!/usr/bin/env python3
"""Actualizar los números vivos de index.html desde fuentes públicas.

Las cifras del portafolio (commits de Block Ethos, tamaño del índice RAG)
quedan viejas en cuanto los repos avanzan. Este script las relee de la
fuente en cada publicación y reescribe SOLO los dígitos en index.html:
ni texto, ni estructura, ni estilos.

Uso (desde la raíz del repo)::

    python3 tools/actualizar-datos.py           # actualiza index.html
    python3 tools/actualizar-datos.py --check   # solo informa; sale 1 si hay cambios pendientes
    python3 tools/actualizar-datos.py --html RUTA   # otro archivo HTML de destino

Paso previo a cada publicación (ver README.md).

Solo biblioteca estándar de Python 3. La página NO carga este script:
corre en build-time, antes de publicar, y GitHub Pages sigue sirviendo
un único index.html sin dependencias externas.

Fuentes (sin autenticación; la API pública de GitHub permite 60
peticiones/hora sin token, y este script hace 2):
- API pública de GitHub: /repos/{repo}/contributors (commits por autor
  y total en la rama por defecto).
- JSON crudo de otro repo: raw.githubusercontent.com/{repo}/{rama}/{ruta}.

Si la variable de entorno GITHUB_TOKEN existe, se envía como Bearer
para subir el límite de la API; nunca se imprime ni se guarda.

Genérico por diseño: para reutilizar el patrón en otro repo basta con
editar FUENTES y DATOS (abajo) — los fetchers y el motor de reemplazo
no tocan nada específico del portafolio.

Regla de seguridad: si alguna fuente falla (red, API, JSON), el script
aborta SIN escribir nada; index.html nunca queda a medio actualizar.
Cada destino debe coincidir exactamente una vez: cero o varias
coincidencias también abortan sin escribir.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HTML_POR_DEFECTO = RAIZ / "index.html"
AGENTE = "portfolio-actualizar-datos/1.0 (+https://github.com/mieresantonio/portfolio)"

# ---------------------------------------------------------------------------
# Configuración: fuentes
# ---------------------------------------------------------------------------
# Cada fuente declara un "tipo" (uno de los fetchers de abajo) y sus
# parámetros. El fetcher devuelve un dict de valores; cada dato toma uno
# de esos valores por su "campo".

FUENTES = {
    "block-ethos": {
        "tipo": "github_contribuyentes",
        "repo": "mieresantonio/mieresantonio-ProyectoFinal-grupo3-ALI",
        "autor": "mieresantonio",
        # Nota: el repo ORIGINAL del proyecto de grupo (fork de
        # 4GeeksAcademy/...), no el standalone block-ethos, que es un
        # repo nuevo con su propio historial.
    },
    "rag": {
        "tipo": "github_json_crudo",
        "repo": "mieresantonio/rag-demo-asistente-documentos",
        "rama": "main",
        "ruta": "data/meta.json",
    },
}

# ---------------------------------------------------------------------------
# Configuración: datos
# ---------------------------------------------------------------------------
# Cada dato: clave legible, fuente, campo dentro de lo que devuelve la
# fuente, y uno o más destinos. Cada destino es una expresión regular
# con UN grupo nombrado (?P<valor>\\d+) que marca exactamente los dígitos
# a reemplazar; el resto del patrón es contexto que no se toca.

DATOS = [
    {
        "clave": "rag-documentos",
        "fuente": "rag",
        "campo": "documentos",
        "destinos": [
            r"(?P<valor>\d+) documentos, \d+ fragmentos indexados",
        ],
    },
    {
        "clave": "rag-fragmentos",
        "fuente": "rag",
        "campo": "fragmentos",
        "destinos": [
            r"\d+ documentos, (?P<valor>\d+) fragmentos indexados",
        ],
    },
]


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def pedir_json(url: str) -> object:
    """GET con User-Agent propio; devuelve el JSON parseado."""
    peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        peticion.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{url} -> HTTP {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"{url} -> {e.reason}") from e


def pedir_json_paginado(url: str) -> list:
    """GET que sigue los enlaces 'next' de la cabecera Link (API GitHub)."""
    items: list = []
    siguiente: str | None = url
    while siguiente:
        peticion = urllib.request.Request(siguiente, headers={"User-Agent": AGENTE})
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            peticion.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(peticion, timeout=30) as respuesta:
                pagina = json.loads(respuesta.read().decode("utf-8"))
                if not isinstance(pagina, list):
                    raise RuntimeError(f"{siguiente} -> respuesta inesperada: {pagina!r}"[:200])
                items.extend(pagina)
                siguiente = _siguiente_link(respuesta.headers.get("Link", ""))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{siguiente} -> HTTP {e.code} {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"{siguiente} -> {e.reason}") from e
    return items


def _siguiente_link(cabecera_link: str) -> str | None:
    for parte in cabecera_link.split(","):
        trozos = parte.strip().split(";")
        if len(trozos) == 2 and 'rel="next"' in trozos[1]:
            return trozos[0].strip()[1:-1]  # quita < >
    return None


# ---------------------------------------------------------------------------
# Fetchers (uno por "tipo" de fuente; devuelven dicts de valores)
# ---------------------------------------------------------------------------

def fetch_github_contribuyentes(fuente: dict) -> dict:
    """Commits en la rama por defecto: total y los del autor indicado."""
    repo, autor = fuente["repo"], fuente["autor"]
    url = f"https://api.github.com/repos/{repo}/contributors?per_page=100"
    contribuyentes = pedir_json_paginado(url)
    total = sum(c.get("contributions", 0) for c in contribuyentes)
    mios = None
    for c in contribuyentes:
        if c.get("login", "").lower() == autor.lower():
            mios = c["contributions"]
    if mios is None:
        raise RuntimeError(f"autor {autor!r} no aparece entre los contribuyentes de {repo}")
    return {"autor": mios, "total": total}


def fetch_github_json_crudo(fuente: dict) -> dict:
    """Un JSON cualquiera de un repo público, tal cual."""
    url = (
        f"https://raw.githubusercontent.com/{fuente['repo']}/"
        f"{fuente['rama']}/{fuente['ruta']}"
    )
    datos = pedir_json(url)
    if not isinstance(datos, dict):
        raise RuntimeError(f"{url} -> se esperaba un objeto JSON, llegó {type(datos).__name__}")
    return datos


FETCHERS = {
    "github_contribuyentes": fetch_github_contribuyentes,
    "github_json_crudo": fetch_github_json_crudo,
}


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

def resolver_fuentes() -> dict:
    """Consulta cada fuente una sola vez; devuelve {nombre: {campo: valor}}."""
    valores = {}
    for nombre, fuente in FUENTES.items():
        fetcher = FETCHERS.get(fuente["tipo"])
        if fetcher is None:
            raise RuntimeError(f"fuente {nombre!r}: tipo desconocido {fuente['tipo']!r}")
        valores[nombre] = fetcher(fuente)
    return valores


def aplicar(texto: str, valores: dict) -> tuple[str, list[str]]:
    """Aplica todos los datos; devuelve (texto nuevo, líneas de informe).

    Si un destino no coincide exactamente una vez, o un campo no existe,
    levanta RuntimeError y el llamador no escribe nada.
    """
    informe = []
    for dato in DATOS:
        fuente = valores[dato["fuente"]]
        if dato["campo"] not in fuente:
            raise RuntimeError(
                f"dato {dato['clave']!r}: campo {dato['campo']!r} no existe en la fuente "
                f"{dato['fuente']!r} (campos: {sorted(fuente)})"
            )
        nuevo = str(fuente[dato["campo"]])
        for patron in dato["destinos"]:
            regex = re.compile(patron)
            coincidencias = list(regex.finditer(texto))
            if len(coincidencias) != 1:
                raise RuntimeError(
                    f"dato {dato['clave']!r}: el patrón {patron!r} coincide "
                    f"{len(coincidencias)} veces (se esperaba 1)"
                )
            m = coincidencias[0]
            viejo = m.group("valor")
            if viejo == nuevo:
                informe.append(f"  {dato['clave']}: {viejo} (ya actualizado)")
            else:
                texto = texto[: m.start("valor")] + nuevo + texto[m.end("valor"):]
                informe.append(f"  {dato['clave']}: {viejo} -> {nuevo}")
    return texto, informe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Actualiza los números vivos de index.html desde fuentes públicas."
    )
    parser.add_argument("--check", action="store_true",
                        help="solo informa de los cambios pendientes, sin escribir")
    parser.add_argument("--html", type=Path, default=HTML_POR_DEFECTO,
                        help=f"archivo HTML de destino (defecto: {HTML_POR_DEFECTO})")
    args = parser.parse_args(argv)

    try:
        valores = resolver_fuentes()
        original = args.html.read_text(encoding="utf-8")
        nuevo_texto, informe = aplicar(original, valores)
    except (RuntimeError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(f"Fuente block-ethos: {valores['block-ethos']['autor']} de "
          f"{valores['block-ethos']['total']} commits "
          f"({FUENTES['block-ethos']['repo']})")
    print(f"Fuente rag: {valores['rag'].get('documentos')} documentos, "
          f"{valores['rag'].get('fragmentos')} fragmentos "
          f"({FUENTES['rag']['repo']})")
    print("\n".join(informe))

    if nuevo_texto == original:
        print("Sin cambios: index.html ya lleva las cifras de la fuente.")
        return 0
    if args.check:
        print("--check: hay cambios pendientes (no se escribió nada).")
        return 1
    args.html.write_text(nuevo_texto, encoding="utf-8")
    print(f"Actualizado: {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
