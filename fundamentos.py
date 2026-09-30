"""Fundamentos das ações da B3 via Fundamentus (tabela pública de resultados)."""
from __future__ import annotations

import re
from io import StringIO

import numpy as np
import pandas as pd
import requests

URL = "https://www.fundamentus.com.br/resultado.php"

COLUNAS = {
    "Papel": "ticker",
    "Cotação": "cotacao",
    "P/L": "pl",
    "P/VP": "pvp",
    "Div.Yield": "dy",
    "EV/EBITDA": "ev_ebitda",
    "Mrg. Líq.": "margem_liq",
    "Liq. Corr.": "liq_corrente",
    "ROIC": "roic",
    "ROE": "roe",
    "Liq.2meses": "liq_2m",
    "Dív.Brut/ Patrim.": "div_patrim",
    "Cresc. Rec.5a": "cresc_rec_5a",
}


def _num(valor) -> float:
    """Converte '1.234,56' / '12,3%' / 12.3 em float (percentual vira fração)."""
    if isinstance(valor, (int, float, np.number)):
        return float(valor)
    if not isinstance(valor, str) or not valor.strip():
        return np.nan
    txt = valor.strip()
    pct = txt.endswith("%")
    txt = re.sub(r"[%\s]", "", txt).replace(".", "").replace(",", ".")
    try:
        num = float(txt)
    except ValueError:
        return np.nan
    return num / 100 if pct else num


def parse_tabela(html: str) -> pd.DataFrame:
    tabela = pd.read_html(StringIO(html), decimal=",", thousands=".")[0]
    tabela = tabela.rename(columns=COLUNAS)
    tabela = tabela[[c for c in COLUNAS.values() if c in tabela.columns]]
    for col in tabela.columns:
        if col != "ticker":
            tabela[col] = tabela[col].map(_num)
    return tabela.set_index("ticker")


def baixar_fundamentos(timeout: int = 30) -> pd.DataFrame:
    resp = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = "ISO-8859-1"
    return parse_tabela(resp.text)


def eh_barata(f: pd.Series) -> bool:
    """Filtro de valor clássico: lucrativa, múltiplos baixos, rentável e sem dívida alta."""
    return bool(
        0 < f.get("pl", np.nan) <= 15
        and 0 < f.get("pvp", np.nan) <= 1.5
        and f.get("roe", np.nan) >= 0.10
        and f.get("div_patrim", np.nan) <= 1.5
    )


def pontuar_fundamentos(f: pd.Series) -> int:
    """Pontos de 'valor' (0 a 6), faixas de referência comuns no mercado brasileiro."""
    pts = 0
    pl, pvp = f.get("pl", np.nan), f.get("pvp", np.nan)
    pts += 0 < pl <= 10
    pts += 0 < pvp <= 1.0
    pts += f.get("roe", np.nan) >= 0.15
    pts += f.get("div_patrim", np.nan) <= 0.5
    pts += f.get("dy", np.nan) >= 0.06
    pts += f.get("margem_liq", np.nan) >= 0.10
    return int(pts)
