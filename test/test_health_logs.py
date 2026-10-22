import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from logs import JsonFormatter, LogMiddleware, tratar_http_exception


def app_de_teste():
    app = FastAPI()
    app.add_middleware(LogMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=["http://site.teste"], allow_methods=["*"], allow_headers=["*"])
    app.add_exception_handler(StarletteHTTPException, tratar_http_exception)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    @app.get("/vaza")
    def vaza():
        raise HTTPException(500, "Erro: tabela secreta violou a policy de RLS")

    @app.get("/estoura")
    def estoura():
        raise RuntimeError("senha do banco: 1234")

    @app.get("/ia")
    def ia():
        raise HTTPException(503, "IA sobrecarregada, tente novamente")

    @app.get("/nao")
    def nao():
        raise HTTPException(404, "Não encontrado")

    return TestClient(app, raise_server_exceptions=False)


def test_500_manual_nao_vaza_o_detalhe():
    r = app_de_teste().get("/vaza")
    assert r.status_code == 500
    assert "secreta" not in r.text and "RLS" not in r.text
    assert r.json()["detail"] == f"Erro interno. Código {r.headers['x-request-id']}"


def test_excecao_nao_tratada_vira_500_generico():
    r = app_de_teste().get("/estoura")
    assert r.status_code == 500
    assert "1234" not in r.text and "senha" not in r.text


def test_500_continua_com_cors_para_o_navegador_ver_o_erro_real():
    r = app_de_teste().get("/estoura", headers={"Origin": "http://site.teste"})
    assert r.headers.get("access-control-allow-origin") == "http://site.teste"


def test_mensagens_amigaveis_de_outros_status_continuam():
    c = app_de_teste()
    assert c.get("/ia").json()["detail"] == "IA sobrecarregada, tente novamente"
    assert c.get("/nao").status_code == 404 and c.get("/nao").json()["detail"] == "Não encontrado"


def test_toda_resposta_tem_id_de_requisicao():
    r = app_de_teste().get("/ok")
    assert len(r.headers["x-request-id"]) == 8


def test_formato_json_do_log():
    rec = logging.LogRecord("taverna", logging.INFO, __file__, 1, "requisicao", None, None)
    rec.rid, rec.status = "abc12345", 200
    linha = json.loads(JsonFormatter().format(rec))
    assert linha["msg"] == "requisicao" and linha["rid"] == "abc12345" and linha["status"] == 200


def test_health_da_api_real():
    from main import app
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"