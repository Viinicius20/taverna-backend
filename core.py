import os
import re
from dotenv import load_dotenv
from supabase import create_client, Client
from contextvars import ContextVar

from slowapi import Limiter
from slowapi.util import get_remote_address

load_dotenv()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
CAMPANHA_PADRAO = "00000000-0000-0000-0000-000000000001"
CAMPANHA_ID = CAMPANHA_PADRAO
limiter = Limiter(key_func=get_remote_address)

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_campanha_ctx: ContextVar[str] = ContextVar("campanha_id", default=CAMPANHA_PADRAO)

def campanha_atual() -> str:
    return _campanha_ctx.get()