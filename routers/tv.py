from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from core import supabase

from servicos import ocultar_cofre
from core import supabase, CAMPANHA_ID
from servicos import ocultar_cofre, calendario_atual

router = APIRouter(tags=["tv"])


class CombatStateReq(BaseModel):
    combatentes: list = []
    turno_atual: int = 0
    combate_ativo: bool = False


@router.put("/combat/{campaign_id}")
def salvar_combate(campaign_id: str, req: CombatStateReq):
    supabase.table("combat_state").upsert({
        "campaign_id": campaign_id,
        "combatentes": req.combatentes,
        "turno_atual": req.turno_atual,
        "combate_ativo": req.combate_ativo,
        "updated_at": datetime.utcnow().isoformat(),
    }, on_conflict="campaign_id").execute()
    return {"ok": True}


@router.get("/tv/{campaign_id}")
def dados_tv(campaign_id: str):
    imgs = supabase.table("gallery").select("id, name, url") \
        .eq("revealed", True).or_("type.is.null,type.neq.handout") \
        .limit(1).execute().data or []

    hands = supabase.table("gallery").select("id, name, url, text_content, cofre_hashes") \
                .eq("campaign_id", campaign_id).eq("type", "handout").eq("revealed", True) \
                .order("created_at", desc=True).limit(1).execute().data or []
    hands = ocultar_cofre(hands, set())

    combate = {"ativo": False, "turno": 0, "combatentes": []}
    cs = supabase.table("combat_state").select("*").eq("campaign_id", campaign_id).limit(1).execute().data
    if cs:
        lista = []
        for x in (cs[0]["combatentes"] or []):
            hp_max = x.get("hpMax") or 0
            hp_atual = x.get("hpAtual") or 0
            pct = max(0, min(100, round(hp_atual / hp_max * 100))) if hp_max else 0
            item = {
                "id": x.get("id"),
                "nome": x.get("nome"),
                "tipo": x.get("tipo"),
                "iniciativa": x.get("iniciativa"),
                "avatar_url": x.get("avatar_url"),
                "condicoes": x.get("condicoes") or [],
                "hp_pct": pct,
            }
            if x.get("tipo") == "jogador":
                item["hp_atual"] = hp_atual
                item["hp_max"] = hp_max
            lista.append(item)
        combate = {"ativo": bool(cs[0]["combate_ativo"]), "turno": cs[0]["turno_atual"] or 0, "combatentes": lista}

        try:
            texto_data = calendario_atual(campaign_id)["texto"] if campaign_id == CAMPANHA_ID else None
        except Exception:
            texto_data = None

    return {"success": True, "data": {
        "imagem": imgs[0] if imgs else None,
        "handout": hands[0] if hands else None,
        "combate": combate,
        "calendario": texto_data,
    }}