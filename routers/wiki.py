from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core import supabase
from auth import exigir_mestre
import re

def limpar_links(texto, validos):
    v = {t.strip().lower() for t in validos}
    return re.sub(
        r"\[\[([^\]]+)\]\]",
        lambda m: m.group(0) if m.group(1).strip().lower() in v else m.group(1),
        texto,
    )

router = APIRouter(tags=["wiki"])


class WikiReq(BaseModel):
    campaign_id: str
    titulo: str
    categoria: str = "Lore"
    conteudo: str = ""
    notas_mestre: str = ""
    revelada: bool = False
    entidade_tipo: Optional[str] = None
    entidade_id: Optional[str] = None


class WikiEditReq(BaseModel):
    titulo: Optional[str] = None
    categoria: Optional[str] = None
    conteudo: Optional[str] = None
    notas_mestre: Optional[str] = None
    revelada: Optional[bool] = None
    entidade_tipo: Optional[str] = None
    entidade_id: Optional[str] = None

class GerarHistoriaIn(BaseModel):
    titulo: str
    tipo: str = ""
    contexto: Optional[str] = ""
    texto_atual: Optional[str] = ""
    titulos_existentes: List[str] = []


@router.post("/wiki", dependencies=[Depends(exigir_mestre)])
def criar_pagina_wiki(req: WikiReq):
    r = supabase.table("wiki_paginas").insert(req.dict()).execute()
    return {"data": r.data[0]}


@router.get("/wiki/{campaign_id}", dependencies=[Depends(exigir_mestre)])
def listar_wiki_mestre(campaign_id: str):
    r = supabase.table("wiki_paginas").select("*").eq("campaign_id", campaign_id).order("titulo").execute()
    return {"data": r.data}


@router.get("/wiki/{campaign_id}/jogador")
def listar_wiki_jogador(campaign_id: str):
    r = supabase.table("wiki_paginas").select("id, titulo, categoria, conteudo") \
        .eq("campaign_id", campaign_id).eq("revelada", True).order("titulo").execute()
    return {"data": r.data}


@router.patch("/wiki/{wiki_id}", dependencies=[Depends(exigir_mestre)])
def editar_pagina_wiki(wiki_id: str, req: WikiEditReq):
    campos = {k: v for k, v in req.dict().items() if v is not None}
    if not campos:
        raise HTTPException(400, "Nada pra atualizar")
    campos["updated_at"] = datetime.utcnow().isoformat()
    r = supabase.table("wiki_paginas").update(campos).eq("id", wiki_id).execute()
    if not r.data:
        raise HTTPException(404, "Página não encontrada")
    return {"data": r.data[0]}


@router.delete("/wiki/{wiki_id}", dependencies=[Depends(exigir_mestre)])
def deletar_pagina_wiki(wiki_id: str):
    supabase.table("wiki_paginas").delete().eq("id", wiki_id).execute()
    return {"ok": True}

@router.post("/wiki/gerar-historia", dependencies=MESTRE)
async def gerar_historia(req: GerarHistoriaIn):
    prompt = (
        f"Você ajuda um mestre de RPG de fantasia a escrever a página '{req.titulo}' "
        f"({req.tipo or 'entrada'}) de uma wiki de campanha. "
        f"Contexto do mestre: {req.contexto or 'nenhum'}. "
        + (f"Texto atual, para continuar e manter coerente: {req.texto_atual[:3000]}. " if req.texto_atual else "")
        + (f"Quando citar algo destas entradas, escreva [[Título]] exatamente assim: "
           f"{', '.join(req.titulos_existentes[:80])}. " if req.titulos_existentes else "")
        + "Escreva 2 a 4 parágrafos em português do Brasil. Responda só com o texto, sem título nem markdown."
    )
    texto = await chamar_ia(prompt)
    return {"success": True, "texto": limpar_links(texto.strip(), req.titulos_existentes)}