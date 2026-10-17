import os


os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_KEY", "a.b.c")
os.environ.setdefault("GEMINI_API_KEY", "chave-falsa")