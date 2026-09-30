"""Indicadores e detecção do setup 123 de compra.

Tudo aqui é pandas puro, sem rede, para dar pra testar offline.
Espera um DataFrame com colunas Open, High, Low, Close, Volume indexado por data,
contendo apenas candles FECHADOS.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TICK = 0.01  # variação mínima de preço na B3


def media(serie: pd.Series, periodo: int, tipo: str = "sma") -> pd.Series:
    if tipo == "ema":
        return serie.ewm(span=periodo, adjust=False).mean()
    return serie.rolling(periodo).mean()


def ifr(close: pd.Series, periodo: int) -> pd.Series:
    """IFR (RSI) de Wilder."""
    delta = close.diff()
    ganho = delta.clip(lower=0).ewm(alpha=1 / periodo, adjust=False).mean()
    perda = (-delta.clip(upper=0)).ewm(alpha=1 / periodo, adjust=False).mean()
    rs = ganho / perda.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def atr(df: pd.DataFrame, periodo: int = 14) -> pd.Series:
    prev = df["Close"].shift()
    tr = pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / periodo, adjust=False).mean()


def adicionar_indicadores(
    df: pd.DataFrame, curta: int = 20, longa: int = 72, tipo_media: str = "sma"
) -> pd.DataFrame:
    df = df.copy()
    df["MA_curta"] = media(df["Close"], curta, tipo_media)
    df["MA_longa"] = media(df["Close"], longa, tipo_media)
    df["IFR2"] = ifr(df["Close"], 2)
    df["IFR14"] = ifr(df["Close"], 14)
    df["ATR14"] = atr(df, 14)
    df["VolMed20"] = df["Volume"].rolling(20).mean()
    df["VolFin20"] = (df["Close"] * df["Volume"]).rolling(20).mean()
    return df


@dataclass
class Params:
    curta: int = 20
    longa: int = 72
    tipo_media: str = "sma"
    janela_fundo: int = 8  # candle 2 tem que ser a menor mínima dessa janela
    estrito: bool = False  # exige mínima do candle 3 acima da do candle 1 também
    exigir_medias: bool = True  # fechamento do candle 3 acima das duas médias


def detectar_123(df: pd.DataFrame, p: Params = Params()) -> dict | None:
    """Avalia os 3 últimos candles fechados. Retorna dict com os dados do sinal ou None.

    Candle 1 = antepenúltimo, candle 2 = penúltimo (o fundo), candle 3 = último.
    """
    minimo = max(p.longa, p.janela_fundo, 20) + 3
    if len(df) < minimo:
        return None

    d = adicionar_indicadores(df, p.curta, p.longa, p.tipo_media)
    c1, c2, c3 = d.iloc[-3], d.iloc[-2], d.iloc[-1]

    # 123: candle do meio faz a menor mínima e o candle 3 não perde essa mínima
    if not (c2.Low < c1.Low and c2.Low < c3.Low):
        return None
    if p.estrito and not (c3.Low > c1.Low):
        return None

    # "em um fundo": mínima do candle 2 é a menor da janela recente
    janela = d["Low"].iloc[-p.janela_fundo :]
    if c2.Low > janela.min():
        return None

    acima_curta = c3.Close > c3.MA_curta
    acima_longa = c3.Close > c3.MA_longa
    if p.exigir_medias and not (acima_curta and acima_longa):
        return None

    entrada = round(c3.High + TICK, 2)
    stop = round(c2.Low - TICK, 2)
    risco = entrada - stop
    if risco <= 0:
        return None

    ma_longa_antes = d["MA_longa"].iloc[-6]
    topo_52 = d["High"].iloc[-252:].max()

    return {
        "data": d.index[-1],
        "fechamento": round(c3.Close, 2),
        "entrada": entrada,
        "stop": stop,
        "risco_pct": round(risco / entrada * 100, 2),
        "alvo_2R": round(entrada + 2 * risco, 2),
        "alvo_3R": round(entrada + 3 * risco, 2),
        "ma_curta": round(c3.MA_curta, 2),
        "ma_longa": round(c3.MA_longa, 2),
        "acima_medias": bool(acima_curta and acima_longa),
        "medias_alinhadas": bool(c3.MA_curta > c3.MA_longa),
        "ma_longa_subindo": bool(c3.MA_longa > ma_longa_antes),
        "fundo_na_media": bool(c2.Low <= c2.MA_curta * 1.01),
        "dist_ma_curta_pct": round((c3.Close / c3.MA_curta - 1) * 100, 2),
        "ifr2_fundo": round(c2.IFR2, 1),
        "ifr14": round(c3.IFR14, 1),
        "volume_forte": bool(c3.Volume > c3.VolMed20),
        "risco_em_atr": round(risco / c3.ATR14, 2) if c3.ATR14 else np.nan,
        "espaco_topo52_pct": round((topo_52 / entrada - 1) * 100, 2),
        "vol_fin_medio": round(c3.VolFin20, 0),
    }


def pontuar_tecnico(s: dict) -> int:
    """Pontos extras de confluência técnica (0 a 7)."""
    pts = 0
    pts += s["medias_alinhadas"]  # MA20 > MA72: tendência de alta
    pts += s["ma_longa_subindo"]  # MA72 inclinada pra cima
    pts += s["fundo_na_media"]  # pullback testou a MA20
    pts += s["ifr2_fundo"] <= 25  # fundo sobrevendido no curtíssimo prazo
    pts += s["volume_forte"]  # candle 3 com volume acima da média
    pts += s["risco_pct"] <= 5  # stop curto
    pts += s["dist_ma_curta_pct"] <= 5  # preço não esticado
    return int(pts)
