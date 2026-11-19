#!/usr/bin/env python3
"""
CheckLifting -> JSON. Lê MONICLA.PAD, MONIORD.PAD e MONILEG.PAD e grava monicla.json, moniord.json e
monileg.json a cada segundo.
Não escreve nada no console: erros de leitura vão nos próprios JSONs (ok/erro), os de gravação no log.

  python checklifting_json.py [--arquivos PASTA] [--saida PASTA] [--intervalo MS]
"""
import argparse, json, os, re, sys, time
from datetime import datetime
from pathlib import Path

LEVANTAMENTOS = ("agachamento", "supino", "terra")


def num(s, div=1):
    """Campo numérico de largura fixa: ("07320", 100) -> 73.2; None se não for só dígitos."""
    s = s.strip()
    return int(s) / div if s.isdecimal() else None


def num_virgula(s):
    """Número com vírgula decimal: " 50,0" -> 50.0; None se não for número."""
    s = s.strip()
    return float(s.replace(",", ".")) if re.fullmatch(r"\d+[.,]?\d*|[.,]\d+", s) else None


# ---------------------------------------------------------------- MONICLA: cabeçalho 123 + registros de 341
def ler_monicla(b: bytes) -> dict:
    if len(b) < 123:
        raise ValueError("arquivo menor que o cabeçalho (123 bytes)")
    if (len(b) - 123) % 341 not in (0, 2):  # 2 = CRLF final; outro resto = gravação em andamento
        raise ValueError("MONICLA com tamanho inesperado (gravação em andamento?)")
    t = b.decode("latin-1")
    d = {"campeonato": t[0:50].strip(), "titulo": t[50:100].strip(), "levantamento": t[100:110].strip(),
         "controle": t[110:123].strip(), "categorias": []}
    cat = None
    for i in range((len(t) - 123) // 341):
        r = t[123 + i * 341: 123 + (i + 1) * 341]
        if r[:6] == "000000":  # linha de categoria
            nome = " ".join(r[16:100].split())
            if nome:
                cat = {"nome": nome, "atletas": []}
                d["categorias"].append(cat)
            continue
        if cat is None or not r[:6].strip().isdecimal():
            continue
        tent = [{"kg": num(r[228 + 5 * k: 232 + 5 * k], 10),  # 9 tentativas: 3 rodadas x 3 levantamentos
                 "valido": {"S": True, "N": False}.get(r[232 + 5 * k: 233 + 5 * k])} for k in range(9)]
        cat["atletas"].append({
            "id": r[0:6], "divisao": r[10:12].strip(), "numero": r[13:16].strip(), "nome": r[17:56].strip(),
            "equipe": r[56:106].strip(), "voo": r[106:111].strip("[] "), "peso_corporal": num(r[111:116], 100),
            "classificacoes": r[117:216].split(),
            "rodadas": [{"rodada": k + 1, **{l: tent[3 * k + j] for j, l in enumerate(LEVANTAMENTOS)}} for k in range(3)],
            "pontos_gl": num(r[297:301], 100), "pontos_gl_supino": num(r[313:317], 100),
            "supino_isolado_melhor": num(r[283:288], 10),
            "total_provisorio": num(r[273:278], 10),  # já soma a pedida ainda sem julgamento
            "total_oficial": num(r[278:283], 10),     # só tentativas válidas
        })
    return d


# ---------------------------------------------------------------- MONIORD: cabeçalho 111 + 32 vagas de 307
def ler_moniord(b: bytes) -> dict:
    if len(b) < 111 + 32 * 307:
        raise ValueError("MONIORD incompleto (gravação em andamento?)")
    t = b.decode("latin-1")
    d = {"campeonato": t[0:50].strip(), "titulo": t[50:100].strip(), "levantamento": t[100:111].strip(), "chamadas": []}
    for i in range(32):
        v = t[111 + i * 307: 111 + (i + 1) * 307]
        if not v.strip():  # vaga livre
            continue
        tok = v[91:302].split()  # ex.: ["52", "Kg", "CLA-OP"]
        k = next((j for j, x in enumerate(tok) if x.endswith("Kg")), None)
        d["chamadas"].append({
            "ordem": i + 1, "marca": v[0:1].strip(), "nome": v[1:41].strip(), "equipe": v[41:91].strip(),
            "classe_peso": " ".join(tok[:k + 1]) if k is not None else "",
            "classificacoes": tok[k + 1:] if k is not None else tok,
            "pedida_kg": num_virgula(v[302:307]),
        })
    return d


# ---------------------------------------------------------------- MONILEG: só nacionalidade e UF do atleta em quadra
def ler_monileg(b: bytes) -> dict:
    if len(b) < 750:
        raise ValueError("MONILEG incompleto (gravação em andamento?)")
    t = b.decode("latin-1")
    return {"nacionalidade": t[102:105].strip() or None,  # código do país, ex.: BRA (bandeira: Imagens/Paises/BRA.bmp)
            "uf": t[100:102].strip() or None}              # ex.: RS (bandeira: Imagens/Estados/RS.bmp)


# ---------------------------------------------------------------- ciclo: ler, manter o último dado bom, gravar
class Fonte:
    def __init__(self, arquivo: Path, leitor, destino: Path):
        self.arquivo, self.leitor, self.destino = arquivo, leitor, destino
        self.dados, self.ok, self.erro, self.dados_de, self.erro_gravacao = {}, False, None, None, None

    def ciclo(self, log: Path):
        agora = datetime.now().isoformat(timespec="seconds")
        try:
            try:
                bruto = self.arquivo.read_bytes()
            except OSError:
                raise ValueError(f"não consegui abrir {self.arquivo.name}")
            self.dados, self.ok, self.erro, self.dados_de = self.leitor(bruto), True, None, agora
        except Exception as e:  # mantém o último dado bom
            self.ok, self.erro = False, str(e)
        saida = {"ok": self.ok, "erro": self.erro, "atualizado": agora, "dados_de": self.dados_de, **self.dados}
        try:  # grava em temporário e troca, para ninguém ler um JSON pela metade
            tmp = self.destino.with_name(self.destino.name + ".tmp")
            tmp.write_text(json.dumps(saida, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            os.replace(tmp, self.destino)
            self.erro_gravacao = None
        except Exception as e:
            if str(e) != self.erro_gravacao:  # registra só quando o erro muda
                self.erro_gravacao = str(e)
                try:
                    with log.open("a", encoding="utf-8") as f:
                        f.write(f"[{agora}] gravação falhou: {e}\n")
                except OSError:
                    pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arquivos", default=r"C:\PadraoInformatica\CheckLifting\Arquivos", help="pasta dos MONI*.PAD")
    ap.add_argument("--saida", default="saida", help="pasta dos JSONs")
    ap.add_argument("--intervalo", type=int, default=1000, help="milissegundos entre atualizações")
    a = ap.parse_args()
    saida, origem, intervalo = Path(a.saida).resolve(), Path(a.arquivos), max(100, a.intervalo) / 1000
    try:
        saida.mkdir(parents=True, exist_ok=True)
    except OSError:
        sys.exit(2)
    fontes = [Fonte(origem / "MONICLA.PAD", ler_monicla, saida / "monicla.json"),
              Fonte(origem / "MONIORD.PAD", ler_moniord, saida / "moniord.json"),
              Fonte(origem / "MONILEG.PAD", ler_monileg, saida / "monileg.json")]
    proximo = time.monotonic()
    try:
        while True:
            for f in fontes:
                f.ciclo(saida / "checklifting.log")
            proximo = max(proximo + intervalo, time.monotonic())
            time.sleep(max(0, proximo - time.monotonic()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
