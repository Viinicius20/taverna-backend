from auth import MESTRE
from core import supabase
from fastapi import APIRouter
from fastapi import HTTPException
from ia import gerar_texto_com_gemini
from pydantic import BaseModel
from servicos import ajustar_reputacao
from utils import MAXIMO
import json

router = APIRouter()


class FactionRequest(BaseModel):
    campaign_id: str
    description: str
    system: str = "D&D 5e"


class UpdateFactionRequest(BaseModel):
    name: str = None
    type: str = None
    description: str = None
    goals: str = None
    reputation: str = None


class LocationRequest(BaseModel):
    campaign_id: str
    description: str
    system: str = "D&D 5e"


class UpdateLocationRequest(BaseModel):
    faction_id: str = None
    name: str = None


class AjusteReputacao(BaseModel):
    delta: int
    reason: str


class StagesReq(BaseModel):
    campaign_id: str
    npc_id: str
    stages: list[str]


class GerarStagesReq(BaseModel):
    npc_name: str
    secret: str


class AvancarSegredoReq(BaseModel):
    npc_name: str
    secret: str


@router.post("/factions/generate", dependencies=MESTRE)
async def gerar_faccao(req: FactionRequest):
    prompt = f"""
    Você é um mestre de RPG criando uma facção para o mundo de campanha.
    Sistema: {req.system}
    Descrição fornecida pelo mestre: {req.description}

    Retorne APENAS um JSON:
    {{
      "name": "Nome da Facção",
      "type": "guilda/ordem/reino/culto/outro",
      "description": "Descrição curta da facção, seus valores e estrutura",
      "goals": "Objetivos atuais da facção no mundo"
    }}
    """
    try:
        raw = gerar_texto_com_gemini(prompt)
        raw = raw.replace("```json", "").replace("```", "").strip()
        faction_data = json.loads(raw)

        result = supabase.table("factions").insert({
            "campaign_id": req.campaign_id,
            "name": faction_data.get("name"),
            "type": faction_data.get("type"),
            "description": faction_data.get("description"),
            "goals": faction_data.get("goals"),
            "reputation": "neutra",
            "is_homebrew": True
        }).execute()

        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar facção: {str(e)}")


@router.get("/factions/{campaign_id}", dependencies=MESTRE)
async def listar_faccoes(campaign_id: str):
    result = supabase.table("factions").select("*").eq("campaign_id", campaign_id).order("name").execute()
    return {"success": True, "data": result.data}


@router.patch("/factions/{faction_id}", dependencies=MESTRE)
async def atualizar_faccao(faction_id: str, req: UpdateFactionRequest):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    supabase.table("factions").update(updates).eq("id", faction_id).execute()
    return {"success": True}


@router.delete("/factions/{faction_id}", dependencies=MESTRE)
async def deletar_faccao(faction_id: str):
    supabase.table("factions").delete().eq("id", faction_id).execute()
    return {"success": True}


@router.post("/locations/generate", dependencies=MESTRE)
async def gerar_local(req: LocationRequest):
    prompt = f"""
    Você é um mestre de RPG criando um local para o mundo de campanha.
    Sistema: {req.system}
    Descrição fornecida: {req.description}

    Retorne APENAS um JSON:
    {{
      "name": "Nome do Local",
      "type": "cidade/vila/masmorra/floresta/ruína/outro",
      "description": "Descrição geral do local, atmosfera e aparência",
      "region_info": "Clima, geografia e cultura da região",
      "commerce": "O que é comum encontrar à venda ou negociar aqui",
      "monsters": "Criaturas ou perigos comuns na região",
      "quests": "2-3 ideias de missão ou situação que fazem sentido aqui",
      "language": "Idioma mais falado no local",
      "avg_level": "Faixa de nível recomendada para aventureiros (ex: 3-5)",
      "boss": "Uma possível ameaça principal ou chefe local, se fizer sentido (ou vazio se não)"
    }}
    """
    try:
        raw = gerar_texto_com_gemini(prompt)
        raw = raw.replace("```json", "").replace("```", "").strip()
        loc_data = json.loads(raw)

        result = supabase.table("locations").insert({
            "campaign_id": req.campaign_id,
            "name": loc_data.get("name"),
            "type": loc_data.get("type"),
            "description": loc_data.get("description"),
            "region_info": loc_data.get("region_info"),
            "commerce": loc_data.get("commerce"),
            "monsters": loc_data.get("monsters"),
            "quests": loc_data.get("quests"),
            "language": loc_data.get("language"),
            "avg_level": loc_data.get("avg_level"),
            "boss": loc_data.get("boss"),
            "is_homebrew": True
        }).execute()

        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar local: {str(e)}")


@router.get("/locations/{campaign_id}", dependencies=MESTRE)
async def listar_locais(campaign_id: str):
    result = supabase.table("locations").select("*").eq("campaign_id", campaign_id).order("name").execute()
    return {"success": True, "data": result.data}


@router.patch("/locations/{location_id}", dependencies=MESTRE)
async def atualizar_local(location_id: str, req: UpdateLocationRequest):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    supabase.table("locations").update(updates).eq("id", location_id).execute()
    return {"success": True}


@router.delete("/locations/{location_id}", dependencies=MESTRE)
async def deletar_local(location_id: str):
    supabase.table("locations").delete().eq("id", location_id).execute()
    return {"success": True}


@router.post("/reputation/{tipo}/{entidade_id}", dependencies=MESTRE)
def mudar_reputacao(tipo: str, entidade_id: str, body: AjusteReputacao):
    if tipo not in ("faction", "npc"):
        raise HTTPException(400, "Tipo inválido")
    if body.delta == 0 or abs(body.delta) > MAXIMO:
        raise HTTPException(400, f"Pontos devem ficar entre -{MAXIMO} e {MAXIMO} (e não zero)")
    motivo = body.reason.strip()
    if not motivo:
        raise HTTPException(400, "Informe o motivo")
    return {"success": True, "data": ajustar_reputacao(tipo, entidade_id, body.delta, motivo)}


@router.get("/reputation/{tipo}/{entidade_id}/log", dependencies=MESTRE)
def historico_reputacao(tipo: str, entidade_id: str):
    if tipo not in ("faction", "npc"):
        raise HTTPException(400, "Tipo inválido")
    res = supabase.table("reputation_log") \
        .select("id, delta, score_after, reason, source, created_at") \
        .eq("entity_type", tipo).eq("entity_id", entidade_id) \
        .order("created_at", desc=True).limit(30).execute()
    return {"success": True, "data": res.data or []}


@router.delete("/reputation/log/{log_id}", dependencies=MESTRE)
def deletar_log_reputacao(log_id: str):
    res = supabase.table("reputation_log").delete().eq("id", log_id).execute()
    if not res.data:
        raise HTTPException(404, "Registro não encontrado")
    return {"success": True}


@router.get("/secret-stages/{campaign_id}/{npc_id}", dependencies=MESTRE)
def get_secret_stages(campaign_id: str, npc_id: str):
    r = supabase.table("npc_secret_stages").select("*") \
        .eq("campaign_id", campaign_id).eq("npc_id", npc_id).execute()
    return {"data": r.data[0] if r.data else None}


@router.post("/secret-stages", dependencies=MESTRE)
def salvar_secret_stages(req: StagesReq):
    r = supabase.table("npc_secret_stages").upsert(
        {"campaign_id": req.campaign_id, "npc_id": req.npc_id, "stages": req.stages},
        on_conflict="campaign_id,npc_id"
    ).execute()
    return {"data": r.data[0]}


@router.post("/secret-stages/gerar", dependencies=MESTRE)
def gerar_secret_stages(req: GerarStagesReq):
    prompt = f"""
    Segredo do NPC {req.npc_name}: "{req.secret}"

    Crie 3 estágios graduais de revelação desse segredo, do mais vago ao mais próximo da verdade,
    SEM entregar a verdade completa:
    1) uma pista sutil e ambígua;
    2) uma suspeita mais concreta;
    3) uma descoberta parcial (quase tudo, faltando o essencial).

    Cada estágio deve ter 1-2 frases, escritas como algo que os jogadores perceberiam.
    Responda com exatamente 3 linhas, uma por estágio, sem numeração, sem markdown, sem aspas.
    """
    texto = gerar_texto_com_gemini(prompt).strip().replace("```json", "").replace("```", "").strip()

    linhas = None
    try:
        parsed = json.loads(texto)
        if isinstance(parsed, list):
            linhas = [str(x).strip() for x in parsed]
    except Exception:
        pass

    if not linhas:
        linhas = [
            l.strip().strip('[]",\'-•* ').lstrip("0123456789.) ").strip()
            for l in texto.split("\n")
            if l.strip() and l.strip() not in ("[", "]")
        ]

    if len(linhas) < 3:
        raise HTTPException(500, "A IA não retornou os 3 estágios.")
    return {"data": linhas[:3]}


@router.post("/secret-stages/{stage_id}/avancar", dependencies=MESTRE)
def avancar_secret_stage(stage_id: str, req: AvancarSegredoReq):
    row = supabase.table("npc_secret_stages").select("*").eq("id", stage_id).single().execute().data
    if not row:
        raise HTTPException(404, "Segredo não encontrado")
    nivel = row["nivel_revelado"]
    if nivel >= 4:
        raise HTTPException(400, "Segredo já totalmente revelado")
    novo = nivel + 1
    rotulos = {1: "👁️ Pista", 2: "❓ Suspeita", 3: "💡 Descoberta parcial", 4: "🔓 Verdade"}
    texto = req.secret if novo == 4 else row["stages"][novo - 1]
    supabase.table("npc_secret_stages").update({"nivel_revelado": novo}).eq("id", stage_id).execute()
    return {"nivel_revelado": novo, "message": f"{rotulos[novo]} sobre {req.npc_name}: {texto}"}

