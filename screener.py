#!/usr/bin/env python3
"""Screener de ações da B3: setup 123 de compra em fundo, acima das médias 20 e 72,
com pontuação de confluência técnica e de valor (ações baratas).

Uso rápido:
    python screener.py
    python screener.py --so-baratas --estrito
    python screener.py --intervalo 1wk --tipo-media ema
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from fundamentos import baixar_fundamentos, eh_barata, pontuar_fundamentos
from setup123 import Params, adicionar_indicadores, detectar_123, pontuar_tecnico

# Usado quando o Fundamentus não responde. Ações líquidas (base IBrX 100).
TICKERS_PADRAO = """
ABEV3 ALOS3 ALPA4 ASAI3 AURE3 AZZA3 B3SA3 BBAS3 BBDC3 BBDC4 BBSE3 BEEF3 BPAC11
BRAP4 BRAV3 BRFS3 BRKM5 CMIG4 CMIN3 COGN3 CPFE3 CPLE6 CSAN3 CSMG3 CSNA3 CURY3
CVCB3 CXSE3 CYRE3 DIRR3 DXCO3 EGIE3 ELET3 ELET6 EMBR3 ENEV3 ENGI11 EQTL3 FLRY3
GGBR4 GOAU4 HAPV3 HYPE3 IGTI11 INTB3 IRBR3 ISAE4 ITSA4 ITUB4 JHSF3 KLBN11 LREN3
MGLU3 MOVI3 MRFG3 MRVE3 MULT3 NTCO3 PETR3 PETR4 PETZ3 POMO4 PRIO3 PSSA3 RADL3
RAIL3 RAIZ4 RANI3 RDOR3 RECV3 RENT3 SANB11 SAPR11 SBSP3 SIMH3 SLCE3 SMTO3 STBP3
SUZB3 TAEE11 TIMS3 TOTS3 UGPA3 USIM5 VALE3 VAMO3 VBBR3 VIVA3 VIVT3 WEGE3 YDUQ3
""".split()

FUSO = ZoneInfo("America/Sao_Paulo")


def args_cli(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--intervalo", default="1d", choices=["1d", "1wk"], help="diário ou semanal")
    ap.add_argument("--curta", type=int, default=20, help="média curta (padrão 20)")
    ap.add_argument("--longa", type=int, default=72, help="média longa (padrão 72)")
    ap.add_argument("--tipo-media", default="sma", choices=["sma", "ema"])
    ap.add_argument("--janela-fundo", type=int, default=8,
                    help="candle 2 precisa ser a menor mínima desses N candles")
    ap.add_argument("--estrito", action="store_true",
                    help="mínima do candle 3 acima das mínimas dos candles 1 e 2")
    ap.add_argument("--sem-medias", action="store_true",
                    help="não exige fechamento acima das médias (só informa)")
    ap.add_argument("--liq-min", type=float, default=2_000_000,
                    help="volume financeiro médio diário mínimo em R$ (padrão 2 mi)")
    ap.add_argument("--preco-max", type=float, default=None, help="preço máximo por ação")
    ap.add_argument("--so-baratas", action="store_true",
                    help="só mostra ações que passam no filtro de valor (P/L, P/VP, ROE, dívida)")
    ap.add_argument("--tickers", nargs="*", help="lista própria de tickers (ex: PETR4 VALE3)")
    ap.add_argument("--incluir-candle-aberto", action="store_true",
                    help="usa o candle do dia mesmo com pregão aberto")
    ap.add_argument("--saida", default="resultado_123.csv")
    return ap.parse_args(argv)


def montar_universo(a) -> tuple[list[str], pd.DataFrame | None]:
    fund = None
    try:
        fund = baixar_fundamentos()
        print(f"Fundamentus: {len(fund)} papéis carregados")
    except Exception as e:  # noqa: BLE001
        print(f"[aviso] Fundamentus indisponível ({e}). Seguindo sem fundamentos.")

    if a.tickers:
        return [t.upper() for t in a.tickers], fund
    if fund is not None:
        # liq_2m do Fundamentus é volume financeiro médio diário dos últimos 2 meses
        liquidos = fund[fund["liq_2m"] >= a.liq_min]
        if a.so_baratas:
            liquidos = liquidos[liquidos.apply(eh_barata, axis=1)]
        return sorted(liquidos.index), fund
    return TICKERS_PADRAO, fund


def baixar_precos(tickers: list[str], intervalo: str, sufixo: str = ".SA") -> dict[str, pd.DataFrame]:
    import yfinance as yf

    periodo = "2y" if intervalo == "1d" else "5y"
    simbolos = [f"{t}{sufixo}" for t in tickers]
    bruto = yf.download(simbolos, period=periodo, interval=intervalo, group_by="ticker",
                        auto_adjust=True, progress=False, threads=True)
    saida = {}
    for t, s in zip(tickers, simbolos):
        if isinstance(bruto.columns, pd.MultiIndex):
            if s not in bruto.columns.get_level_values(0):
                continue
            df = bruto[s]
        else:
            df = bruto
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        if not df.empty:
            saida[t] = df
    return saida


def remover_candle_aberto(df: pd.DataFrame, intervalo: str) -> pd.DataFrame:
    """Durante o pregão o Yahoo devolve o candle do dia/semana ainda em formação."""
    agora = datetime.now(FUSO)
    ultimo = df.index[-1].date()
    fechou = agora.hour > 18 or (agora.hour == 18 and agora.minute >= 30)
    if intervalo == "1d" and ultimo == agora.date() and not fechou:
        return df.iloc[:-1]
    if intervalo == "1wk" and (agora.date() - ultimo).days < 7 and not (agora.weekday() >= 5 or (agora.weekday() == 4 and fechou)):
        return df.iloc[:-1]
    return df


def contexto_ibov(intervalo: str, p: Params, incluir_aberto: bool) -> str:
    try:
        df = baixar_precos(["^BVSP"], intervalo, sufixo="").get("^BVSP")
    except Exception:  # noqa: BLE001
        df = None
    if df is None or len(df) < p.longa:
        return "Ibovespa: sem dados"
    if not incluir_aberto:
        df = remover_candle_aberto(df, intervalo)
    d = adicionar_indicadores(df, p.curta, p.longa, p.tipo_media).iloc[-1]
    tend = "ALTA" if d.Close > d.MA_curta > d.MA_longa else "BAIXA" if d.Close < d.MA_curta < d.MA_longa else "LATERAL/INDEFINIDA"
    return (f"Ibovespa {d.Close:,.0f} | MA{p.curta} {d.MA_curta:,.0f} | MA{p.longa} {d.MA_longa:,.0f}"
            f" -> tendência {tend}")


def rodar(a) -> pd.DataFrame:
    p = Params(curta=a.curta, longa=a.longa, tipo_media=a.tipo_media,
               janela_fundo=a.janela_fundo, estrito=a.estrito, exigir_medias=not a.sem_medias)

    tickers, fund = montar_universo(a)
    print(f"Analisando {len(tickers)} ativos no {'diário' if a.intervalo == '1d' else 'semanal'}...")
    print(contexto_ibov(a.intervalo, p, a.incluir_candle_aberto))

    precos = baixar_precos(tickers, a.intervalo)
    linhas = []
    for t, df in precos.items():
        if not a.incluir_candle_aberto:
            df = remover_candle_aberto(df, a.intervalo)
        sinal = detectar_123(df, p)
        if not sinal:
            continue
        if sinal["vol_fin_medio"] < a.liq_min:
            continue
        if a.preco_max and sinal["fechamento"] > a.preco_max:
            continue

        linha = {"ticker": t, **sinal, "pts_tecnico": pontuar_tecnico(sinal)}
        if fund is not None and t in fund.index:
            f = fund.loc[t]
            if isinstance(f, pd.DataFrame):
                f = f.iloc[0]
            linha.update(pl=f.get("pl"), pvp=f.get("pvp"), roe=f.get("roe"), dy=f.get("dy"),
                         div_patrim=f.get("div_patrim"), barata=eh_barata(f),
                         pts_valor=pontuar_fundamentos(f))
        else:
            linha.update(barata=None, pts_valor=0)
        if a.so_baratas and not linha["barata"]:
            continue
        linha["score"] = linha["pts_tecnico"] + linha["pts_valor"]
        linhas.append(linha)

    res = pd.DataFrame(linhas)
    if res.empty:
        return res
    return res.sort_values(["score", "risco_pct"], ascending=[False, True]).reset_index(drop=True)


def main(argv=None):
    a = args_cli(argv)
    res = rodar(a)
    if res.empty:
        print("\nNenhum setup 123 de compra encontrado com esses filtros hoje.")
        return 0

    res.to_csv(a.saida, index=False, sep=";", decimal=",")
    colunas = ["ticker", "fechamento", "entrada", "stop", "risco_pct", "alvo_2R", "ifr2_fundo",
               "medias_alinhadas", "fundo_na_media", "pl", "pvp", "roe", "barata",
               "pts_tecnico", "pts_valor", "score"]
    colunas = [c for c in colunas if c in res.columns]
    with pd.option_context("display.max_rows", None, "display.width", 200):
        print(f"\n{len(res)} setups 123 de compra encontrados:\n")
        print(res[colunas].to_string(index=False))
    print(f"\nTabela completa salva em {a.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
