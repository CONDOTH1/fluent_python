"""
Example written following Fluent Python, 2nd Edition

The init and form functions are hacks to load and serve the static HTML form.
The recommended best practice is to have a proxy/load-balancer in front of the
ASGI server (Fast API) to handle all static assets, and also use a CDN
(Content Delivery Network) when possible. One such prox/load-balancer is
Traefik (https://doc.traefik.io/traefik/), an "edge router" that "receives
requests on behalf of your system and finds out which components are
responsible for handling them"
"""

from pathlib import Path
from unicodedata import name

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from charindex import InvertedIndex

STATIC_PATH = Path(__file__).parent.absolute() / "static"

app = FastAPI(
    title="Mojifinder Web",
    description="Search fo Unicode characters by name.",
)


class CharName(BaseModel):
    char: str
    name: str


def init(app):
    app.state.index = InvertedIndex()
    app.state.form = (STATIC_PATH / "form.html").read_text()


init(app)


@app.get("/search", response_model=list[CharName])
async def search(q: str):
    chars = sorted(app.state.index.search(q))
    return ({"char": c, "name": name(c)} for c in chars)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def form():
    return app.state.form
