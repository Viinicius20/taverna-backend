import os
import re
import base64
import json
from dotenv import load_dotenv
from supabase import create_client, Client
from contextvars import ContextVar

from slowapi import Limiter
from slowapi.util import get_remote_address

load_dotenv()

def _papel_da_chave(chave: str) -> str:
    try:
        parte = chave.split(".")[1]
        parte += "=" * (-len(parte) % 4)
        return json.loads(base64.urlsafe_b64decode(parte)).get("role", "?")
    except Exception:
        return "desconhecido"


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_CHAVE = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_CHAVE:
    raise RuntimeError("Defina SUPABASE_URL e SUPABASE_SERVICE_KEY")
_origem = "SUPABASE_SERVICE_KEY" if os.getenv("SUPABASE_SERVICE_KEY") else "SUPABASE_KEY"
print(f"[core] chave vinda de {_origem}, papel: {_papel_da_chave(SUPABASE_CHAVE)}", flush=True)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_CHAVE)
CAMPANHA_PADRAO = "00000000-0000-0000-0000-000000000001"
CAMPANHA_ID = CAMPANHA_PADRAO
limiter = Limiter(key_func=get_remote_address)

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_campanha_ctx: ContextVar[str] = ContextVar("campanha_id", default=CAMPANHA_PADRAO)

def campanha_atual() -> str:
    return _campanha_ctx.get()