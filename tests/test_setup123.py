import numpy as np
import pandas as pd
import pytest

from fundamentos import _num, eh_barata, parse_tabela, pontuar_fundamentos
from setup123 import Params, detectar_123, pontuar_tecnico


def serie_alta(n=120, inicio=10.0, passo=0.05):
    """Tendência de alta limpa: cada candle sobe 'passo'."""
    close = inicio + passo * np.arange(n)
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({
        "Open": close - 0.02, "High": close + 0.10, "Low": close - 0.10,
        "Close": close, "Volume": np.full(n, 1_000_000.0),
    }, index=idx)


def com_123(df, low1, low2, low3, close3=None, high3=None):
    df = df.copy()
    base = df["Close"].iloc[-4]
    df.iloc[-3, df.columns.get_loc("Low")] = base + low1
    df.iloc[-2, df.columns.get_loc("Low")] = base + low2
    df.iloc[-1, df.columns.get_loc("Low")] = base + low3
    if close3 is not None:
        df.iloc[-1, df.columns.get_loc("Close")] = close3
    if high3 is not None:
        df.iloc[-1, df.columns.get_loc("High")] = high3
    return df


def test_detecta_123_em_fundo_acima_das_medias():
    df = com_123(serie_alta(), low1=-0.30, low2=-0.50, low3=-0.20)
    s = detectar_123(df)
    assert s is not None
    assert s["stop"] == round(df["Low"].iloc[-2] - 0.01, 2)
    assert s["entrada"] == round(df["High"].iloc[-1] + 0.01, 2)
    assert s["acima_medias"] and s["medias_alinhadas"]
    assert 0 <= pontuar_tecnico(s) <= 7


def test_rejeita_quando_candle2_nao_e_o_fundo():
    df = com_123(serie_alta(), low1=-0.60, low2=-0.50, low3=-0.20)
    assert detectar_123(df) is None


def test_rejeita_quando_candle3_perde_minima_do_2():
    df = com_123(serie_alta(), low1=-0.30, low2=-0.50, low3=-0.70)
    assert detectar_123(df) is None


def test_modo_estrito_exige_minima3_acima_da_minima1():
    df = com_123(serie_alta(), low1=-0.20, low2=-0.50, low3=-0.30)
    assert detectar_123(df) is not None
    assert detectar_123(df, Params(estrito=True)) is None


def test_rejeita_abaixo_das_medias():
    queda = serie_alta(passo=-0.03, inicio=20)
    df = com_123(queda, low1=-0.30, low2=-0.50, low3=-0.20)
    assert detectar_123(df) is None
    assert detectar_123(df, Params(exigir_medias=False)) is not None


def test_rejeita_se_nao_for_fundo_da_janela():
    df = com_123(serie_alta(), low1=-0.30, low2=-0.50, low3=-0.20)
    df.iloc[-5, df.columns.get_loc("Low")] = df["Low"].iloc[-2] - 1
    assert detectar_123(df) is None


def test_poucos_dados():
    assert detectar_123(serie_alta(n=50)) is None


@pytest.mark.parametrize("txt,esperado", [
    ("1.234,56", 1234.56), ("12,5%", 0.125), ("-3,2%", -0.032), ("", np.nan), (7.5, 7.5),
])
def test_num(txt, esperado):
    r = _num(txt)
    assert (np.isnan(r) and np.isnan(esperado)) or r == pytest.approx(esperado)


def test_parse_fundamentus_e_filtro_valor():
    html = """<table><thead><tr><th>Papel</th><th>Cotação</th><th>P/L</th><th>P/VP</th>
    <th>Div.Yield</th><th>Mrg. Líq.</th><th>ROE</th><th>Liq.2meses</th><th>Dív.Brut/ Patrim.</th></tr></thead>
    <tbody><tr><td>BARA3</td><td>10,50</td><td>6,20</td><td>0,90</td><td>8,10%</td><td>15,0%</td>
    <td>18,30%</td><td>25.000.000,00</td><td>0,40</td></tr>
    <tr><td>CARA3</td><td>50,00</td><td>40,00</td><td>6,00</td><td>1,00%</td><td>5,0%</td>
    <td>8,00%</td><td>3.000.000,00</td><td>2,10</td></tr></tbody></table>"""
    t = parse_tabela(html)
    assert t.loc["BARA3", "pl"] == pytest.approx(6.2)
    assert t.loc["BARA3", "roe"] == pytest.approx(0.183)
    assert t.loc["BARA3", "liq_2m"] == pytest.approx(25_000_000)
    assert eh_barata(t.loc["BARA3"]) and not eh_barata(t.loc["CARA3"])
    assert pontuar_fundamentos(t.loc["BARA3"]) == 6
