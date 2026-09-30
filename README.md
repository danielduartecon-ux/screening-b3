# Screener B3: setup 123 de compra em ações baratas

Varre as ações líquidas da B3 atrás do **123 de compra** formado num fundo, com o candle de sinal
fechando **acima das médias de 20 e 72**. Depois dá uma nota para cada sinal somando confluências
técnicas e fundamentos de valor, pra você estudar primeiro o que tem mais coisa a favor.

## Como rodar

```bash
pip install -r requirements.txt
python screener.py                      # diário, padrão
python screener.py --so-baratas         # só ações que passam no filtro de valor
python screener.py --estrito            # mínima do candle 3 acima das mínimas do 1 e do 2
python screener.py --intervalo 1wk      # gráfico semanal
python screener.py --tipo-media ema     # médias exponenciais em vez de aritméticas
python screener.py --preco-max 20       # só papéis até R$ 20
python screener.py --tickers PETR4 VALE3 ITUB4
```

O resultado aparece no terminal e vai completo para `resultado_123.csv` (separador `;`, abre direto no Excel).

Dados de preço vêm do Yahoo Finance (`yfinance`) e os fundamentos da tabela pública do
[Fundamentus](https://www.fundamentus.com.br/resultado.php). Se o Fundamentus cair, o screener
segue só com a parte técnica numa lista fixa de ~90 ações líquidas.

## As regras do 123

Olhando os 3 últimos candles **fechados** (durante o pregão o candle do dia é ignorado, a não ser
que você passe `--incluir-candle-aberto`):

| Regra | Como está no código |
|---|---|
| Candle 2 é o fundo | mínima do candle 2 < mínima do candle 1 **e** < mínima do candle 3 |
| Fundo de verdade | mínima do candle 2 é a menor dos últimos 8 candles (`--janela-fundo`) |
| Modo estrito (opcional) | mínima do candle 3 também maior que a do candle 1 |
| Tendência | fechamento do candle 3 acima da MA20 e da MA72 (`--sem-medias` desliga) |
| Entrada | 1 centavo acima da máxima do candle 3 |
| Stop | 1 centavo abaixo da mínima do candle 2 |
| Alvos | 2R e 3R (2x e 3x o risco) |

## Filtros e pontuação extras

Coisas que pesquisei e que costumam separar um 123 bom de um 123 qualquer.

**Técnico (0 a 7 pontos)**

- MA20 acima da MA72: tendência de alta alinhada, não só preço acima das médias.
- MA72 inclinada pra cima nos últimos 5 candles.
- Fundo testou a MA20 (pullback na média, o cenário clássico de continuação).
- IFR2 do candle 2 ≤ 25: fundo sobrevendido no curtíssimo prazo, ideia do IFR2 do Stormer.
- Volume do candle 3 acima da média de 20.
- Risco até 5% entre entrada e stop.
- Preço no máximo 5% acima da MA20 (não compra esticado).

Também saem no CSV, sem pontuar: IFR14, risco medido em ATRs, espaço até o topo de 52 semanas
e volume financeiro médio.

**Valor / "barata" (0 a 6 pontos)**, faixas de referência comuns no mercado:

- P/L entre 0 e 10
- P/VP ≤ 1,0
- ROE ≥ 15%
- Dívida bruta / patrimônio ≤ 0,5
- Dividend yield ≥ 6%
- Margem líquida ≥ 10%

A coluna `barata` é um filtro mais frouxo e binário: P/L ≤ 15, P/VP ≤ 1,5, ROE ≥ 10% e dívida/PL ≤ 1,5.
É ele que o `--so-baratas` usa.

**Liquidez:** volume financeiro médio diário mínimo de R$ 2 milhões (`--liq-min`). Setup em papel
sem liquidez é armadilha, o stop não sai onde você quer.

**Contexto:** o screener imprime a tendência do Ibovespa pelas mesmas médias. 123 de compra com
o índice em tendência de baixa tem taxa de acerto bem pior, vale pesar isso.

## Testes

```bash
pip install pytest
pytest
```

Isto é ferramenta de estudo, não recomendação de investimento.

## Versão para o Profit Pro (NTSL)

A pasta `profit/` tem a mesma lógica técnica escrita em NTSL, a linguagem do Profit:

- `screening_123.ntsl`: cole numa estratégia do tipo **Screening** e rode na janela de Screening.
- `execucao_123.ntsl`: estratégia de **Execução** para backtest (entrada no rompimento, stop na mínima do candle 2, alvo em 2R).

O NTSL não tem os fundamentos (P/L, P/VP, ROE), então o filtro de "barata" continua no script Python.
