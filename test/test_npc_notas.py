from routers.npc_notas import separar_chave

ID = "5d9617de-3121-43d0-bc65-24127e2f3286"


def test_separa_chave_simples():
    assert separar_chave(f"{ID}_secret") == (ID, "secret")


def test_campo_com_underscore():
    assert separar_chave(f"{ID}_objetivo_atual") == (ID, "objetivo_atual")


def test_chaves_invalidas():
    assert separar_chave("secret") is None
    assert separar_chave("abc_secret") is None
    assert separar_chave(f"{ID}_") is None