from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import exigir_mestre
from core import supabase

router = APIRouter(tags=["bestiario-fotos"], dependencies=[Depends(exigir_mestre)])


class ArteIn(BaseModel):
    url: str = ""


@router.patch("/bestiary/{criatura_id}/arte")
def definir_arte(criatura_id: str, req: ArteIn):
    url = req.url.strip()
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Endereço de imagem inválido.")
    try:
        supabase.table("bestiary").update({"art_url": url or None}).eq("id", criatura_id).execute()
    except Exception as e:
        print(f"ERRO ARTE BESTIARIO: {e}")
        raise HTTPException(500, "Erro ao salvar a foto.")
    return {"success": True}