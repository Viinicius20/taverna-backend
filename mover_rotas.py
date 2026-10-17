"""
Move rotas do main.py para routers/<nome>.py, sem mudar nenhuma URL.

Uso (na pasta do backend):
  python mover_rotas.py <nome> <prefixo> [<prefixo> ...]            # simulacao (nao altera nada)
  python mover_rotas.py <nome> <prefixo> [<prefixo> ...] --aplicar  # move de verdade

Exemplo:
  python mover_rotas.py mundo_vivo /world-events /world-log /world-changelog /flags
"""
import ast
import builtins
import os
import re
import shutil
import subprocess
import sys

METODOS = {"get", "post", "put", "patch", "delete"}


def rota_de(no):
    """Devolve o caminho da rota se a funcao for decorada com @app.<metodo>("..."), senao None."""
    for d in getattr(no, "decorator_list", []):
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and isinstance(d.func.value, ast.Name) and d.func.value.id == "app"
                and d.func.attr in METODOS and d.args and isinstance(d.args[0], ast.Constant)):
            return d.args[0].value
    return None


def nomes_livres(no):
    usados, ligados = set(), set()
    for n in ast.walk(no):
        if isinstance(n, ast.Name):
            (usados if isinstance(n.ctx, ast.Load) else ligados).add(n.id)
        elif isinstance(n, ast.arg):
            ligados.add(n.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            ligados.add(n.name)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n is not no:
            ligados.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                ligados.add((a.asname or a.name).split(".")[0])
    return usados - ligados


def nomes_definidos(no):
    if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {no.name}
    if isinstance(no, ast.Assign):
        return {t.id for t in no.targets if isinstance(t, ast.Name)}
    if isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name):
        return {no.target.id}
    return set()


def faixa(no):
    inicio = min([d.lineno for d in getattr(no, "decorator_list", [])] + [no.lineno])
    return inicio, no.end_lineno


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    aplicar = "--aplicar" in sys.argv
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    nome, prefixos = args[0], args[1:]

    destino = os.path.join("routers", f"{nome}.py")
    if os.path.exists(destino):
        print(f"ERRO: {destino} ja existe. Escolha outro nome.")
        sys.exit(1)

    src = open("main.py", encoding="utf-8").read()
    linhas = src.splitlines(keepends=True)
    tree = ast.parse(src)

    # 1) rotas escolhidas
    rotas = []
    for no in tree.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            caminho = rota_de(no)
            if caminho and any(caminho == p or caminho.startswith(p + "/") for p in prefixos):
                rotas.append(no)
    if not rotas:
        print("Nenhuma rota encontrada para esses prefixos.")
        sys.exit(1)
    ids_rotas = {id(r) for r in rotas}
    proprios = {r.name for r in rotas}

    # 2) o que o main.py define e importa
    imports, defs = {}, {}
    for no in tree.body:
        if isinstance(no, ast.ImportFrom):
            for a in no.names:
                vinculo = a.asname or a.name
                imports[vinculo] = f"from {'.' * no.level}{no.module or ''} import {a.name}" + (f" as {a.asname}" if a.asname else "")
        elif isinstance(no, ast.Import):
            for a in no.names:
                vinculo = (a.asname or a.name).split(".")[0]
                imports[vinculo] = f"import {a.name}" + (f" as {a.asname}" if a.asname else "")
        elif id(no) not in ids_rotas:
            for n in nomes_definidos(no):
                defs[n] = no

    # 3) fecho das dependencias
    precisa, candidatas, naoresolvidos = set(), {}, set()
    fila = list(set().union(*(nomes_livres(r) for r in rotas)) - {"app"} - proprios)
    while fila:
        n = fila.pop()
        if n in precisa:
            continue
        precisa.add(n)
        if n in defs:
            candidatas[n] = defs[n]
            fila.extend(nomes_livres(defs[n]) - {"app"})
        elif n not in imports and not hasattr(builtins, n):
            naoresolvidos.add(n)

    # 4) o que e compartilhado com codigo que fica no main.py
    compartilhadas = set()
    mudou = True
    while mudou:
        mudou = False
        em_candidatas = {id(c) for c in candidatas.values()}
        uso_restante = set()
        for no in tree.body:
            if id(no) not in ids_rotas and id(no) not in em_candidatas:
                uso_restante |= nomes_livres(no)
        for n, no in list(candidatas.items()):
            if n in uso_restante:
                compartilhadas.add(n)
                del candidatas[n]
                mudou = True

    em_candidatas = {id(c) for c in candidatas.values()}
    uso_restante = set()
    for no in tree.body:
        if id(no) not in ids_rotas and id(no) not in em_candidatas:
            uso_restante |= nomes_livres(no)
    rotas_chamadas_de_fora = sorted(proprios & uso_restante)
    rotas_dependentes = sorted(n for n, no in candidatas.items() if rota_de(no))

    # 5) relatorio
    print(f"Rotas encontradas ({len(rotas)}):")
    for r in rotas:
        print(f"  linha {r.lineno:>5}: {rota_de(r)}  ->  {r.name}")
    movidas = sorted(candidatas)
    print(f"\nModelos/funcoes/constantes que vao junto ({len(movidas)}): {', '.join(movidas) or '-'}")

    problemas = []
    if compartilhadas:
        problemas.append("Usados pelas rotas E por codigo que fica no main.py (mova para core.py ou auth.py,\n"
                         "  importe de la no main.py e rode de novo): " + ", ".join(sorted(compartilhadas)))
    if rotas_chamadas_de_fora:
        problemas.append("Rotas movidas que sao chamadas por codigo que fica no main.py: " + ", ".join(rotas_chamadas_de_fora))
    if rotas_dependentes:
        problemas.append("Rotas movidas dependem de outra ROTA que nao esta nos prefixos (inclua o prefixo dela): "
                         + ", ".join(rotas_dependentes))
    if problemas:
        print("\nNAO DA PARA MOVER AINDA:")
        for p in problemas:
            print(" - " + p)
        sys.exit(1)
    if naoresolvidos:
        print(f"\nAviso: nomes nao encontrados no main.py (confira depois): {', '.join(sorted(naoresolvidos))}")

    if not aplicar:
        print("\nSimulacao concluida. Para mover de verdade, rode de novo com --aplicar")
        return

    # 6) aplica
    def trecho(no):
        ini, fim = faixa(no)
        return "".join(linhas[ini - 1:fim])

    imports_router = {"from fastapi import APIRouter"}
    imports_router |= {imports[n] for n in precisa if n in imports}
    cab = "\n".join(sorted(imports_router))
    corpo_defs = [trecho(no) for no in tree.body if id(no) in {id(c) for c in candidatas.values()}]
    corpo_rotas = [re.sub(r"(?m)^@app\.", "@router.", trecho(r)) for r in rotas]
    conteudo = (cab + "\n\nrouter = APIRouter()\n\n\n"
                + "\n\n".join(corpo_defs + corpo_rotas) + "\n")

    shutil.copy("main.py", "main.py.bak")
    os.makedirs("routers", exist_ok=True)
    init = os.path.join("routers", "__init__.py")
    if not os.path.exists(init):
        open(init, "w").close()
    open(destino, "w", encoding="utf-8").write(conteudo)

    remover = sorted([faixa(r) for r in rotas] + [faixa(c) for c in candidatas.values()], reverse=True)
    for ini, fim in remover:
        del linhas[ini - 1:fim]
    novo = "".join(linhas)
    novo = re.sub(r"\n{4,}", "\n\n\n", novo)

    if re.search(r"(?m)^from routers import ", novo):
        novo = re.sub(r"(?m)^(from routers import .*)$", lambda m: m.group(1) + f", {nome}", novo, count=1)
    else:
        novo = f"from routers import {nome}\n" + novo
    todas = list(re.finditer(r"(?m)^app\.include_router\(.*\)\s*$", novo))
    if todas:
        fim = todas[-1].end()
        novo = novo[:fim] + f"\napp.include_router({nome}.router)" + novo[fim:]
        avisar = False
    else:
        avisar = True
    open("main.py", "w", encoding="utf-8").write(novo)

    print(f"\nPronto: {len(rotas)} rotas movidas para {destino}. Copia de seguranca: main.py.bak")
    if avisar:
        print(f"Adicione no main.py, depois do app = FastAPI(...):  app.include_router({nome}.router)")
    res = subprocess.run([sys.executable, "-m", "pyflakes", "main.py", destino],
                         capture_output=True, text=True)
    if "No module named" in res.stderr:
        print("\npyflakes nao esta instalado. Rode: pip install pyflakes")
        print("Depois: python -m pyflakes main.py " + destino)
    else:
        indefinidos = [l for l in res.stdout.splitlines() if "undefined name" in l]
        print("\npyflakes - nomes indefinidos:" if indefinidos else "\npyflakes: nenhum nome indefinido.")
        for l in indefinidos:
            print("  " + l)


if __name__ == "__main__":
    main()