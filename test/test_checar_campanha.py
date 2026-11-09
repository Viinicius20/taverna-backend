import pytest
from starlette.requests import Request

import auth
from core import _campanha_ctx


def _req(path="/characters", method="GET"):
    return Request({"type": "http", "method": method, "path": path, "headers": []})


class _Tabela:
    def __init__(self, dados):
        self.dados = dados

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def execute(self):
        return type("R", (), {"data": self.dados})()


def _banco(membros, donos):
    class _Sb:
        def table(self, nome):
            return _Tabela(membros if nome == "campaign_members" else donos)
    return _Sb()


def _bearer(uid="u1"):
    return "Bearer " + auth.criar_token({"id": uid, "role": "jogador"})


@pytest.fixture(autouse=True)
def limpa():
    auth._cache_membro.clear()
    token = _campanha_ctx.set("camp-1")
    yield
    _campanha_ctx.reset(token)


def test_membro_passa(monkeypatch):
    monkeypatch.setattr(auth, "supabase", _banco([{"user_id": "u1"}], []))
    auth.checar_campanha(_req(), _bearer())


def test_dono_passa(monkeypatch):
    monkeypatch.setattr(auth, "supabase", _banco([], [{"id": "camp-1"}]))
    auth.checar_campanha(_req(), _bearer())


def test_estranho_recebe_403(monkeypatch):
    monkeypatch.setattr(auth, "supabase", _banco([], []))
    with pytest.raises(auth.HTTPException) as e:
        auth.checar_campanha(_req(), _bearer())
    assert e.value.status_code == 403


def test_banco_fora_recebe_503(monkeypatch):
    class _Quebrado:
        def table(self, nome):
            raise RuntimeError("fora do ar")
    monkeypatch.setattr(auth, "supabase", _Quebrado())
    with pytest.raises(auth.HTTPException) as e:
        auth.checar_campanha(_req(), _bearer())
    assert e.value.status_code == 503


def test_rota_aberta_ignora_campanha(monkeypatch):
    monkeypatch.setattr(auth, "supabase", _banco([], []))
    auth.checar_campanha(_req("/profiles/login", "POST"), _bearer())


def test_sem_token_segue_para_a_rota(monkeypatch):
    monkeypatch.setattr(auth, "supabase", _banco([], []))
    auth.checar_campanha(_req(), None)