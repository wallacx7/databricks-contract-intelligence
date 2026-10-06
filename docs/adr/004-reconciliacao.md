# ADR 004: Reconciliação dos contratos com o billing

- **Status:** aceito
- **Data:** 2026-10-06

## Contexto

Com os termos extraídos e revisados, falta a conta que interessa ao negócio: quanto cada contrato manda cobrar, mês a mês, e quanto o billing cobrou de fato.

## Decisões

1. **dbt sobre dois produtos de dados.** A reconciliação lê os campos finais do Contrato Vivo e o snapshot mensal de MRR do [Ledger](https://github.com/wallacx7/databricks-revenue-agent) (`fct_mrr_snapshot_mensal`), além dos meses fechados das métricas dele.
2. **Documento vigente por mês.** Para cada contrato e mês em que a conta estava ativa, vale o documento mais recente (contrato ou aditivo) cujo início é anterior ao fim do mês.
3. **Preço devido.** Preço do documento vigente × desconto promocional (só no contrato original e dentro do prazo) × desconto de pagamento anual × reajuste. O reajuste é fixo (`(1 + r)` elevado ao número de aniversários desde o documento) ou de tabela. O histórico de reajustes de tabela entra como *seed* (`reajustes_de_tabela.csv`), como viria de um catálogo de produtos.
4. **Tipos de vazamento**, inferidos das cláusulas:
   - diferença de preço com desconto promocional no contrato → desconto vencido;
   - com reajuste fixo → reajuste não aplicado;
   - nos demais casos → preço abaixo do contratado;
   - usuários cobrados abaixo do compromisso mínimo → mínimo não cobrado.
5. **Tolerância.** Diferenças de até R$ 0,05 por usuário são arredondamento, não vazamento.
6. **Teste contra o gabarito.** `vazamento_igual_gabarito` compara contrato, mês e tipo com o vazamento plantado pelo gerador e falha o job se houver qualquer linha a mais, a menos ou com diferença acima de um centavo por usuário.

## Resultado (400 contratos, até setembro de 2026)

| Tipo | Contratos encontrados / plantados | Meses | Valor encontrado | Valor plantado |
|---|---|---|---|---|
| Mínimo não cobrado | 25 / 25 | 573 / 573 | R$ 1.426.932,11 | R$ 1.426.932,11 |
| Reajuste não aplicado | 11 / 11 | 211 / 211 | R$ 1.307.269,61 | R$ 1.307.263,91 |
| Desconto vencido | 14 / 14 | 421 / 421 | R$ 695.608,32 | R$ 695.608,32 |
| Preço abaixo do contratado | 5 / 5 | 131 / 131 | R$ 68.529,06 | R$ 68.529,06 |

Nenhum falso positivo nos 345 contratos sem vazamento. A diferença de R$ 5,70 no reajuste vem de arredondamento (Python no gerador, SQL no dbt), dentro da tolerância.

Para o negócio: 55 de 400 contratos vazam receita, R$ 3,50 milhões não cobrados no histórico, R$ 27,7 mil por mês hoje e **R$ 332 mil recuperáveis nos próximos 12 meses** se o billing for corrigido.

## Consequências

- A regra do preço devido existe em dois lugares: no gerador (Python, que planta) e no dbt (SQL, que encontra). O teste contra o gabarito garante que as duas continuam iguais.
- A atribuição do tipo depende de cada contrato ter no máximo um vazamento de preço, o que vale no cenário simulado. Contratos reais com várias causas sobrepostas precisariam decompor a diferença.
