import os

from fastapi import APIRouter, Response

from core import supabase
from logs import logger

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "commit": (os.getenv("RENDER_GIT_COMMIT") or "")[:7] or None}


@router.get("/health/ready")
def ready(response: Response):
    try:
        supabase.table("profiles").select("id").limit(1).execute()
        return {"status": "ok", "banco": "ok"}
    except Exception as e:
        logger.error("health_banco_falhou", extra={"evento": "health_banco_falhou", "detalhe": str(e)[:200]})
        response.status_code = 503
        return {"status": "degradado", "banco": "falhou"}