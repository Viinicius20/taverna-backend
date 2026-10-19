from fastapi.testclient import TestClient
from main import app

def test_relacoes_exigem_mestre():
    c = TestClient(app)
    assert c.get("/relacoes/x/grafo").status_code == 401
    assert c.post("/relacoes/x", json={}).status_code == 401
    assert c.delete("/relacoes/x/y").status_code == 401