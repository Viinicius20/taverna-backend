from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core import supabase

router = APIRouter(tags=["wiki"])


class WikiReq(BaseModel):
    campaign_id: str
    titulo: str
    categoria: str = "Lore"
    conteudo: str = ""
    notas_mestre: str = ""
    revelada: bool = False


class WikiEditReq(BaseModel):
    titulo: Optional[str] = None
    categoria: Optional[str] = None
    conteudo: Optional[str] = None
    notas_mestre: Optional[str] = None
    revelada: Optional[bool] = None


@router.post("/wiki")
def criar_pagina_wiki(req: WikiReq):
    r = supabase.table("wiki_paginas").insert(req.dict()).execute()
    return {"data": r.data[0]}


@router.get("/wiki/{campaign_id}")
def listar_wiki_mestre(campaign_id: str):
    r = supabase.table("wiki_paginas").select("*").eq("campaign_id", campaign_id).order("titulo").execute()
    return {"data": r.data}


@router.get("/wiki/{campaign_id}/jogador")
def listar_wiki_jogador(campaign_id: str):
    # nunca seleciona notas_mestre
    r = supabase.table("wiki_paginas").select("id, titulo, categoria, conteudo") \
        .eq("campaign_id", campaign_id).eq("revelada", True).order("titulo").execute()
    return {"data": r.data}


@router.patch("/wiki/{wiki_id}")
def editar_pagina_wiki(wiki_id: str, req: WikiEditReq):
    campos = {k: v for k, v in req.dict().items() if v is not None}
    if not campos:
        raise HTTPException(400, "Nada pra atualizar")
    campos["updated_at"] = datetime.utcnow().isoformat()
    r = supabase.table("wiki_paginas").update(campos).eq("id", wiki_id).execute()
    if not r.data:
        raise HTTPException(404, "Página não encontrada")
    return {"data": r.data[0]}


@router.delete("/wiki/{wiki_id}")
def deletar_pagina_wiki(wiki_id: str):
    supabase.table("wiki_paginas").delete().eq("id", wiki_id).execute()
    return {"ok": True}