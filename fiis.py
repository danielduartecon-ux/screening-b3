#!/usr/bin/env python3
"""Screener de fundos imobiliários (FIIs) e planejador de aporte semanal.

    python fiis.py ranking                      # lista os FIIs que passam nos filtros
    python fiis.py aporte --valor 500           # o que comprar nesta semana com R$ 500
    python fiis.py aporte --valor 500 --carteira minha_carteira.csv

Dados: tabela pública de FIIs do Fundamentus.
"""
from __future__ import annotations

import argparse
import math
import sys
from io import StringIO

import numpy as np
import pandas as pd
import requests

from fundamentos import _num

URL = "https://www.fundamentus.com.br/fii_resultado.php"

COLUNAS = {
    "Papel": "ticker",
    "Segmento": "segmento",
    "Cotação": "cotacao",
    "FFO Yield": "ffo_yield",
    "Dividend Yield": "dy",
    "P/VP": "pvp",
    "Valor de Mercado": "valor_mercado",
    "Liquidez": "liquidez",
    "Qtd de imóveis": "qtd_imoveis",
    "Cap Rate": "cap_rate",
    "Vacância Média": "vacancia",
}


def parse_tabela(html: str) -> pd.DataFrame:
    t = pd.read_html(StringIO(html), decimal=",", thousands=".")[0].rename(columns=COLUNAS)
    t = t[[c for c in COLUNAS.values() if c in t.columns]]
    for col in t.columns:
        if col not in ("ticker", "segmento"):
            t[col] = t[col].map(_num)
    t["tipo"] = np.where(t["qtd_imoveis"].fillna(0) > 0, "tijolo", "papel/fof")
    return t.set_index("ticker")


def baixar_fiis(timeout: int = 30) -> pd.DataFrame:
    resp = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = "ISO-8859-1"
    return parse_tabela(resp.text)


# ---------------------------------------------------------------- ranking

def filtrar(t: pd.DataFrame, liq_min=1_000_000, vm_min=500_000_000, pvp_min=0.70, pvp_max=1.05,
            dy_min=0.08, dy_max=0.16, vac_max=0.12, imoveis_min=5) -> pd.DataFrame:
    """Filtros de qualidade. DY alto demais com P/VP muito baixo costuma ser crédito podre, não pechincha."""
    ok = (
        (t["liquidez"] >= liq_min)
        & (t["valor_mercado"] >= vm_min)
        & t["pvp"].between(pvp_min, pvp_max)
        & t["dy"].between(dy_min, dy_max)
    )
    tijolo = t["tipo"] == "tijolo"
    ok &= ~tijolo | ((t["vacancia"].fillna(0) <= vac_max) & (t["qtd_imoveis"] >= imoveis_min))
    return t[ok]


def pontuar(t: pd.DataFrame) -> pd.Series:
    """Nota 0-100: desconto no P/VP, yield, liquidez e (tijolo) vacância baixa. Ranking relativo."""
    r = lambda s, asc=True: s.rank(pct=True, ascending=asc)  # noqa: E731
    nota = 0.35 * r(t["pvp"], asc=False) + 0.30 * r(t["dy"]) + 0.20 * r(t["liquidez"])
    nota += 0.15 * r(t["vacancia"].fillna(0), asc=False)
    return (nota * 100).round(0)


def cmd_ranking(a):
    t = baixar_fiis()
    f = filtrar(t, liq_min=a.liq_min, pvp_max=a.pvp_max)
    f = f.assign(nota=pontuar(f)).sort_values("nota", ascending=False)
    cols = ["segmento", "tipo", "cotacao", "pvp", "dy", "liquidez", "qtd_imoveis", "vacancia", "nota"]
    with pd.option_context("display.max_rows", None, "display.width", 200):
        print(f"{len(f)} FIIs passaram nos filtros (de {len(t)}):\n")
        print(f[cols].head(a.top).to_string())
    f.to_csv("ranking_fiis.csv", sep=";", decimal=",")
    print("\nTabela completa em ranking_fiis.csv")


# ---------------------------------------------------------------- aporte semanal

CARTEIRA_SUGERIDA = """ticker;cotas;peso_alvo
KNCR11;0;15
KNIP11;0;15
MXRF11;0;10
BTLG11;0;12
HGLG11;0;8
XPML11;0;12
HGRU11;0;10
KNRI11;0;10
PVBI11;0;8
"""


def planejar_aporte(carteira: pd.DataFrame, precos: pd.Series, valor: float,
                    pvp: pd.Series | None = None, pvp_teto: float = 1.10) -> pd.DataFrame:
    """Distribui o aporte comprando, cota a cota, o FII mais abaixo do peso-alvo.

    FIIs com P/VP acima de pvp_teto ficam de fora nesta semana (caros).
    """
    c = carteira.copy()
    c["preco"] = precos.reindex(c.index)
    c = c.dropna(subset=["preco"])
    if pvp is not None:
        c["pvp"] = pvp.reindex(c.index)
        c = c[~(c["pvp"] > pvp_teto)]
    c["peso_alvo"] = c["peso_alvo"] / c["peso_alvo"].sum()
    c["comprar"] = 0

    caixa = valor
    while True:
        atual = (c["cotas"] + c["comprar"]) * c["preco"]
        total = atual.sum() + c["preco"].min()  # patrimônio depois da próxima compra (aprox.)
        deficit = c["peso_alvo"] - atual / total
        cabe = c["preco"] <= caixa
        if not cabe.any():
            break
        escolhido = deficit[cabe].idxmax()
        c.loc[escolhido, "comprar"] += 1
        caixa -= c.loc[escolhido, "preco"]

    c["valor_compra"] = (c["comprar"] * c["preco"]).round(2)
    total_final = ((c["cotas"] + c["comprar"]) * c["preco"]).sum()
    c["peso_final_%"] = ((c["cotas"] + c["comprar"]) * c["preco"] / total_final * 100).round(1)
    c["peso_alvo_%"] = (c["peso_alvo"] * 100).round(1)
    c.attrs["sobra"] = round(caixa, 2)
    return c


def cmd_aporte(a):
    if a.carteira:
        carteira = pd.read_csv(a.carteira, sep=";")
    else:
        print("Sem --carteira: usando a carteira sugerida (salva em carteira_fiis.csv para você editar).\n")
        carteira = pd.read_csv(StringIO(CARTEIRA_SUGERIDA), sep=";")
        with open("carteira_fiis.csv", "w") as fh:
            fh.write(CARTEIRA_SUGERIDA)
    carteira["ticker"] = carteira["ticker"].str.upper()
    carteira = carteira.set_index("ticker")

    t = baixar_fiis()
    plano = planejar_aporte(carteira, t["cotacao"], a.valor, t["pvp"], a.pvp_teto)
    cols = ["preco", "pvp", "cotas", "comprar", "valor_compra", "peso_alvo_%", "peso_final_%"]
    print(plano[cols].to_string())
    fora = sorted(set(carteira.index) - set(plano.index))
    if fora:
        print(f"\nFora desta semana (caros ou sem cotação): {', '.join(fora)}")
    print(f"\nTotal a comprar: R$ {plano['valor_compra'].sum():.2f} | sobra: R$ {plano.attrs['sobra']:.2f}")
    print("Depois de comprar, some as cotas na coluna 'cotas' do CSV da carteira.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("ranking", help="ranking de FIIs pelos filtros de qualidade")
    r.add_argument("--liq-min", type=float, default=1_000_000)
    r.add_argument("--pvp-max", type=float, default=1.05)
    r.add_argument("--top", type=int, default=40)
    p = sub.add_parser("aporte", help="o que comprar nesta semana")
    p.add_argument("--valor", type=float, required=True, help="quanto vai aportar (R$)")
    p.add_argument("--carteira", help="CSV ticker;cotas;peso_alvo")
    p.add_argument("--pvp-teto", type=float, default=1.10, help="não compra FII acima desse P/VP")
    a = ap.parse_args(argv)
    {"ranking": cmd_ranking, "aporte": cmd_aporte}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
