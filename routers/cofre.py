import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth import exigir_mestre, usuario_atual, hash_senha, confere_senha
from core import supabase
from servicos import normalizar_resposta

router = APIRouter(tags=["cofre"])

_erros = {}
MAX_ERROS, JANELA = 5, 600


class CofreReq(BaseModel):
    resposta: str
    dica: Optional[str] = None


class AbrirReq(BaseModel):
    character_id: str
    resposta: str


@router.post("/gallery/{handout_id}/cofre", dependencies=[Depends(exigir_mestre)])
def trancar_handout(handout_id: str, body: CofreReq):
    respostas = [normalizar_resposta(r) for r in body.resposta.split("|")]
    respostas = [r for r in respostas if r]
    if not respostas:
        raise HTTPException(400, "Informe ao menos uma resposta")
    r = supabase.table("gallery").update({
        "cofre_hashes": [hash_senha(x) for x in respostas],
        "cofre_dica": body.dica,
    }).eq("id", handout_id).eq("type", "handout").execute()
    if not r.data:
        raise HTTPException(404, "Documento não encontrado")
    supabase.table("handout_abertos").delete().eq("handout_id", handout_id).execute()
    return {"success": True, "respostas_aceitas": len(respostas)}


@router.delete("/gallery/{handout_id}/cofre", dependencies=[Depends(exigir_mestre)])
def destrancar_handout(handout_id: str):
    supabase.table("gallery").update({"cofre_hashes": None, "cofre_dica": None}).eq("id", handout_id).execute()
    return {"success": True}


@router.post("/gallery/{handout_id}/abrir")
def abrir_handout(handout_id: str, body: AbrirReq, user: dict = Depends(usuario_atual)):
    if user.get("role") != "mestre":
        dono = supabase.table("characters").select("user_id").eq("id", body.character_id).limit(1).execute().data
        if not dono or dono[0].get("user_id") != user.get("sub"):
            raise HTTPException(403, "Este personagem não é seu")

    achado = supabase.table("gallery").select("*").eq("id", handout_id).eq("type", "handout").limit(1).execute().data
    if not achado:
        raise HTTPException(404, "Documento não encontrado")
    h = achado[0]

    # só abre quem já recebeu o documento (ou ele foi revelado para todos)
    recebeu = h.get("revealed") or supabase.table("handout_recipients").select("handout_id") \
        .eq("handout_id", handout_id).eq("character_id", body.character_id).limit(1).execute().data
    if not recebeu:
        raise HTTPException(404, "Documento não encontrado")

    publico = {k: v for k, v in h.items() if k != "cofre_hashes"}
    hashes = h.get("cofre_hashes") or []
    if not hashes:
        return {"success": True, "data": publico}

    chave = (handout_id, body.character_id)
    agora = time.time()
    recentes = [t for t in _erros.get(chave, []) if agora - t < JANELA]
    if len(recentes) >= MAX_ERROS:
        raise HTTPException(429, "Muitas tentativas. Aguarde alguns minutos.")

    tentativa = normalizar_resposta(body.resposta)
    if not tentativa or not any(confere_senha(tentativa, x) for x in hashes):
        recentes.append(agora)
        _erros[chave] = recentes
        raise HTTPException(400, "Resposta incorreta")

    _erros.pop(chave, None)
    supabase.table("handout_abertos").upsert({"handout_id": handout_id, "character_id": body.character_id}).execute()
    return {"success": True, "data": publico}