import pandas as pd
import pytest

from fiis import filtrar, parse_tabela, planejar_aporte, pontuar

HTML = """<table><thead><tr><th>Papel</th><th>Segmento</th><th>Cotação</th><th>Dividend Yield</th>
<th>P/VP</th><th>Valor de Mercado</th><th>Liquidez</th><th>Qtd de imóveis</th><th>Vacância Média</th></tr></thead><tbody>
<tr><td>BOMT11</td><td>Logística</td><td>100,00</td><td>9,50%</td><td>0,92</td><td>3.000.000.000</td><td>8.000.000</td><td>20</td><td>3,00%</td></tr>
<tr><td>PAPL11</td><td>Títulos e Val. Mob.</td><td>98,00</td><td>13,00%</td><td>1,00</td><td>5.000.000.000</td><td>15.000.000</td><td>0</td><td>0,00%</td></tr>
<tr><td>PODR11</td><td>Títulos e Val. Mob.</td><td>12,00</td><td>40,00%</td><td>0,15</td><td>600.000.000</td><td>2.000.000</td><td>0</td><td>0,00%</td></tr>
<tr><td>VAZI11</td><td>Lajes Corporativas</td><td>50,00</td><td>9,00%</td><td>0,80</td><td>900.000.000</td><td>1.500.000</td><td>6</td><td>35,00%</td></tr>
</tbody></table>"""


def test_parse_e_filtros():
    t = parse_tabela(HTML)
    assert t.loc["BOMT11", "tipo"] == "tijolo"
    assert t.loc["PAPL11", "tipo"] == "papel/fof"
    assert t.loc["BOMT11", "dy"] == pytest.approx(0.095)
    f = filtrar(t)
    # PODR11: DY absurdo e P/VP 0,15 (armadilha); VAZI11: vacância de 35%
    assert set(f.index) == {"BOMT11", "PAPL11"}
    assert pontuar(f).between(0, 100).all()


def test_aporte_compra_quem_esta_abaixo_do_alvo():
    cart = pd.DataFrame({"cotas": [10, 0], "peso_alvo": [50, 50]}, index=["AAAA11", "BBBB11"])
    precos = pd.Series({"AAAA11": 100.0, "BBBB11": 10.0})
    plano = planejar_aporte(cart, precos, 500)
    assert plano.loc["AAAA11", "comprar"] == 0
    assert plano.loc["BBBB11", "comprar"] == 50
    assert plano.attrs["sobra"] == pytest.approx(0)


def test_aporte_pula_fii_caro_e_respeita_caixa():
    cart = pd.DataFrame({"cotas": [0, 0], "peso_alvo": [50, 50]}, index=["CARO11", "OK11"])
    precos = pd.Series({"CARO11": 100.0, "OK11": 30.0})
    pvp = pd.Series({"CARO11": 1.3, "OK11": 0.9})
    plano = planejar_aporte(cart, precos, 100, pvp=pvp, pvp_teto=1.1)
    assert "CARO11" not in plano.index
    assert plano.loc["OK11", "comprar"] == 3
    assert plano.attrs["sobra"] == pytest.approx(10)
