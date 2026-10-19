import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from main import app
from auth import exigir_mestre, criar_token


client = TestClient(app, raise_server_exceptions=False)

DO_MESTRE = [
    ("GET", "/world-log/x"), ("DELETE", "/world-log/x"),
    ("POST", "/world-events"), ("GET", "/world-events/x"), ("PATCH", "/world-events/x"),
    ("DELETE", "/world-events/x"), ("POST", "/world-events/x/sugerir"),
    ("POST", "/presagios"), ("PATCH", "/presagios/x/cumprir"), ("DELETE", "/presagios/x"),
    ("GET", "/world-changelog/x"), ("GET", "/world-changelog/x/nao-lido-mestre"),
    ("POST", "/world-changelog/x/marcar-lido-mestre"),
    ("POST", "/flags"), ("GET", "/flags/x"), ("PATCH", "/flags/x"), ("DELETE", "/flags/x"),
    ("POST", "/prophecies"), ("GET", "/prophecies/x"), ("PATCH", "/prophecies/x"), ("DELETE", "/prophecies/x"),
    ("POST", "/consequencias/gerar"), ("POST", "/consequencias/sugerir"), ("POST", "/consequencias"),
    ("GET", "/consequencias/x"), ("GET", "/consequencias/prontas/x"),
    ("POST", "/consequencias/x/revelar"), ("DELETE", "/consequencias/x"),     ("POST", "/factions/generate"), ("GET", "/factions/x"), ("PATCH", "/factions/x"), ("DELETE", "/factions/x"),
    ("POST", "/locations/generate"), ("GET", "/locations/x"), ("PATCH", "/locations/x"), ("DELETE", "/locations/x"),
    ("POST", "/reputation/npc/x"), ("GET", "/reputation/npc/x/log"), ("DELETE", "/reputation/log/x"),
    ("GET", "/secret-stages/x/y"), ("POST", "/secret-stages"), ("POST", "/secret-stages/gerar"),
    ("POST", "/secret-stages/x/avancar"),
    ("POST", "/arquivo-mestre"), ("GET", "/arquivo-mestre/x"), ("DELETE", "/arquivo-mestre/x"),
    ("POST", "/economia/eventos"), ("PATCH", "/economia/eventos/x/encerrar"),
    ("GET", "/economia/eventos-campanha/x"), ("DELETE", "/economia/eventos/x"),
    ("GET", "/viagem/locais/x"), ("POST", "/viagem/iniciar"), ("POST", "/viagem/x/avancar"),
    ("GET", "/viagem/campanha/x"), ("GET", "/viagem/x"), ("DELETE", "/viagem/x"),
    ("POST", "/gazeta/gerar"), ("GET", "/gazeta/x"), ("PATCH", "/gazeta/x"),
    ("POST", "/gazeta/x/publicar"), ("DELETE", "/gazeta/x"),
    ("GET", "/downtime/pendentes/x"), ("POST", "/downtime/x/resolver"),
    ("GET", "/misterios"), ("POST", "/misterios"), ("PUT", "/misterios/x/pistas"), ("DELETE", "/misterios/x"),
    ("GET", "/notas-sessao"), ("POST", "/notas-sessao"), ("PATCH", "/notas-sessao/x"),
    ("DELETE", "/notas-sessao/x"), ("POST", "/notas-sessao/encerrar-sessao"),
    ("POST", "/gallery/x/cofre"), ("DELETE", "/gallery/x/cofre"),
    ("POST", "/calendario/00000000-0000-0000-0000-000000000001/avancar"),
    ("PUT", "/calendario/00000000-0000-0000-0000-000000000001/data"),
    ("PUT", "/calendario/00000000-0000-0000-0000-000000000001/meses"),
    ("GET", "/calendario/00000000-0000-0000-0000-000000000001/historico"),
    ("PUT", "/world-events/x/prazo"),
    ("POST", "/calendario/00000000-0000-0000-0000-000000000001/resetar"),
    ("DELETE", "/calendario/00000000-0000-0000-0000-000000000001/historico"),
    ("DELETE", "/calendario/00000000-0000-0000-0000-000000000001/historico/x"),
    ("POST", "/calendario/00000000-0000-0000-0000-000000000001/voltar"),
    ("GET", "/npc-notas/00000000-0000-0000-0000-000000000001"),
    ("PUT", "/npc-notas/00000000-0000-0000-0000-000000000001/x"),
    ("POST", "/npc-notas/00000000-0000-0000-0000-000000000001/migrar"),
]

PUBLICAS = [
    ("GET", "/world-changelog/{campaign_id}/nao-lido/{personagem_id}"),
    ("POST", "/world-changelog/{changelog_id}/marcar-lido"),
    ("GET", "/wiki/{campaign_id}/jogador"),
    ("GET", "/diario/{character_id}"),
    ("GET", "/tv/{campaign_id}"),     ("GET", "/gazeta/{campaign_id}/publicada"),
    ("POST", "/downtime/solicitar"),
    ("GET", "/downtime/resolvidos-nao-vistos/{character_id}"),
    ("POST", "/downtime/{req_id}/marcar-visto"),
    ("GET", "/ficha-publica/{character_id}"),
    ("GET", "/calendario/{campaign_id}"),
]

DO_DONO = [
    ("GET", "/characters/x"), ("PUT", "/characters/x"), ("PATCH", "/characters/x"),
    ("DELETE", "/characters/x"), ("POST", "/characters/x/avatar"), ("GET", "/secret-messages/x"),
    ("GET", "/diario/x"), ("PUT", "/diario/x/nota"),
    ("GET", "/gallery/handouts-para/x"), ("GET", "/downtime/resolvidos-nao-vistos/x"),
    ("POST", "/create-character"), ("POST", "/level-up"), ("POST", "/upload-pdf"),
    ("POST", "/aplicar-asi"), ("POST", "/personagem/conhecimento"),
    ("GET", "/spells"), ("POST", "/push/subscribe"),
    ("PATCH", "/secret-messages/x/lida"), ("POST", "/notify/item"),
    ("POST", "/gallery/x/abrir"),
]


@pytest.mark.parametrize("metodo,caminho", DO_DONO)
def test_exige_login(metodo, caminho):
    r = client.request(metodo, caminho)
    assert r.status_code == 401, f"{metodo} {caminho} respondeu {r.status_code}"

@pytest.mark.parametrize("metodo,caminho", DO_MESTRE)
def test_sem_token_responde_401(metodo, caminho):
    r = client.request(metodo, caminho)
    assert r.status_code == 401, f"{metodo} {caminho} respondeu {r.status_code}"


@pytest.mark.parametrize("metodo,caminho", DO_MESTRE)
def test_jogador_responde_403(metodo, caminho):
    token = criar_token({"id": "teste", "role": "jogador"})
    r = client.request(metodo, caminho, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, f"{metodo} {caminho} respondeu {r.status_code}"


@pytest.mark.parametrize("metodo,caminho", PUBLICAS)
def test_rotas_do_jogador_continuam_abertas(metodo, caminho):
    rota = next(r for r in app.routes
                if isinstance(r, APIRoute) and r.path == caminho and metodo in r.methods)
    assert not any(d.call is exigir_mestre for d in rota.dependant.dependencies)