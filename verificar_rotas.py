from fastapi.routing import APIRoute
from main import app

ABERTAS_DE_PROPOSITO = {("POST", "/profiles/login")}

def test_rotas_de_escrita_tem_dependencia():
    abertas = sorted(
        (sorted(r.methods)[0], r.path)
        for r in app.routes
        if isinstance(r, APIRoute)
        and (r.methods - {"GET", "HEAD", "OPTIONS"})
        and not r.dependant.dependencies
    )
    inesperadas = [a for a in abertas if a not in ABERTAS_DE_PROPOSITO]
    assert not inesperadas, inesperadas