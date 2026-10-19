import os
from dotenv import load_dotenv
from supabase import create_client, Client

from slowapi import Limiter
from slowapi.util import get_remote_address

load_dotenv()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
CAMPANHA_ID = "00000000-0000-0000-0000-000000000001"
limiter = Limiter(key_func=get_remote_address)