import os
import pytest
from main import app
from auth import checar_campanha


os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_KEY", "a.b.c")
os.environ.setdefault("GEMINI_API_KEY", "chave-falsa")

@pytest.fixture(autouse=True)
def sem_checagem_de_campanha():
    app.dependency_overrides[checar_campanha] = lambda: None
    yield
    app.dependency_overrides.pop(checar_campanha, None)