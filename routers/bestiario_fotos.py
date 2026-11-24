from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import exigir_mestre
from core import supabase
from fastapi import UploadFile, File, HTTPException, Depends
import uuid

router = APIRouter(tags=["bestiario-fotos"], dependencies=[Depends(exigir_mestre)])

BUCKET = "bestiario"
MAX_BYTES = 5 * 1024 * 1024


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

def _tipo_real(dados: bytes):
    """Descobre o formato pelo conteúdo, sem confiar no nome ou no content-type enviado."""
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if dados[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


@router.post("/bestiario/{monstro_id}/foto", dependencies=[Depends(exigir_mestre)])
async def enviar_foto_criatura(monstro_id: str, arquivo: UploadFile = File(...)):
    dados = await arquivo.read(MAX_BYTES + 1)
    if len(dados) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="A imagem passa de 5 MB.")
    tipo = _tipo_real(dados)
    if not tipo:
        raise HTTPException(status_code=400, detail="Use uma imagem PNG, JPG ou WebP.")
    ext, mime = tipo

    existe = supabase.table("bestiary").select("id").eq("id", monstro_id).execute().data
    if not existe:
        raise HTTPException(status_code=404, detail="Criatura não encontrada.")

    caminho = f"{monstro_id}/{uuid.uuid4().hex}.{ext}"
    supabase.storage.from_(BUCKET).upload(caminho, dados, {"content-type": mime})
    url = supabase.storage.from_(BUCKET).get_public_url(caminho)

    supabase.table("bestiary").update({"art_url": url}).eq("id", monstro_id).execute()
    return {"success": True, "art_url": url}