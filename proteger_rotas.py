import re
import shutil

ROTAS_MESTRE = """
POST /npcs
DELETE /npcs/{npc_id}
POST /upload-pdf-npc
POST /loot/generate
PATCH /magic-items/{item_id}/revelar
POST /magic-items/homebrew
DELETE /magic-items/{item_id}
POST /sessions
DELETE /sessions/{session_id}
POST /sessions/encerrar
POST /session-state/{campaign_id}/countdown
POST /rules/search
POST /encounter/generate
POST /secret-messages
POST /bestiary/generate
DELETE /bestiary/{monster_id}
PATCH /bestiary/{id}/descoberto
POST /gallery/upload
PATCH /gallery/{image_id}/reveal
PATCH /gallery/{image_id}/hide
DELETE /gallery/{image_id}
POST /gallery/gerar-handout
POST /gallery/{handout_id}/enviar
POST /map-tokens
PATCH /map-tokens/{token_id}/position
PATCH /map-tokens/{token_id}/label
PATCH /map-tokens/{token_id}/rotation
PATCH /map-tokens/{token_id}/scale
DELETE /map-tokens/{token_id}
POST /campaigns
DELETE /world-log/{log_id}
POST /factions/generate
PATCH /factions/{faction_id}
DELETE /factions/{faction_id}
POST /gerar-consequencia
POST /consequencias/sugerir
POST /consequencias/gerar
POST /consequencias
POST /consequencias/{cid}/revelar
DELETE /consequencias/{cid}
POST /npcs/memoria
POST /npcs/memoria/remover
POST /npcs/sugerir-acao
POST /locations/generate
PATCH /locations/{location_id}
DELETE /locations/{location_id}
POST /world-events
DELETE /world-events/{event_id}
POST /world-events/{event_id}/sugerir
PATCH /world-events/{event_id}
POST /presagios
PATCH /presagios/{id}/cumprir
DELETE /presagios/{id}
POST /reputation/{tipo}/{entidade_id}
DELETE /reputation/log/{log_id}
POST /world-changelog/{changelog_id}/marcar-lido-mestre
POST /flags
PATCH /flags/{flag_id}
DELETE /flags/{flag_id}
POST /arquivo-mestre
DELETE /arquivo-mestre/{item_id}
POST /prophecies
PATCH /prophecies/{prophecy_id}
DELETE /prophecies/{prophecy_id}
POST /economia/eventos
PATCH /economia/eventos/{evento_id}/encerrar
DELETE /economia/eventos/{evento_id}
POST /viagem/iniciar
POST /viagem/{viagem_id}/avancar
DELETE /viagem/{viagem_id}
POST /secret-stages
POST /secret-stages/gerar
POST /secret-stages/{stage_id}/avancar
POST /gazeta/gerar
PATCH /gazeta/{gazeta_id}
POST /gazeta/{gazeta_id}/publicar
DELETE /gazeta/{gazeta_id}
POST /downtime/{req_id}/resolver
"""

alvo = set()
for linha in ROTAS_MESTRE.strip().splitlines():
    metodo, caminho = linha.split(None, 1)
    alvo.add((metodo.lower(), caminho.strip()))

padrao = re.compile(r'^@app\.(get|post|put|patch|delete)\((["\'])(.+?)\2\)(\s*)$')

shutil.copy("main.py", "main.py.bak")
with open("main.py", encoding="utf-8", newline="") as f:
    linhas = f.read().split("\n")

achadas = set()
for i, linha in enumerate(linhas):
    m = padrao.match(linha)
    if m and (m.group(1), m.group(3)) in alvo:
        linhas[i] = f"@app.{m.group(1)}({m.group(2)}{m.group(3)}{m.group(2)}, dependencies=MESTRE){m.group(4)}"
        achadas.add((m.group(1), m.group(3)))

with open("main.py", "w", encoding="utf-8", newline="") as f:
    f.write("\n".join(linhas))

print(f"Protegidas: {len(achadas)}")
for metodo, caminho in sorted(alvo - achadas):
    print(f"NÃO ENCONTRADA: {metodo.upper()} {caminho}")