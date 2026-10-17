from fastapi import APIRouter, HTTPException
from core import supabase

router = APIRouter(tags=["publica"])

CAMPOS_PRIVADOS = {"notas_privadas", "objetivo_atual", "ideais", "vinculos", "defeitos", "medos"}

@router.get("/ficha-publica/{character_id}")
def ficha_publica(character_id: str):
    r = supabase.table("characters").select("*").eq("id", character_id).limit(1).execute().data
    if not r:
        raise HTTPException(404, "Ficha não encontrada")
    linha = {k: v for k, v in r[0].items() if k != "user_id"}
    linha["data"] = {k: v for k, v in (r[0].get("data") or {}).items() if k not in CAMPOS_PRIVADOS}
    return {"success": True, "data": linha}