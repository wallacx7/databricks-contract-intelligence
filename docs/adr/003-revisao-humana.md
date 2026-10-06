# ADR 003: Revisão humana com Lakebase

- **Status:** aceito
- **Data:** 2026-10-06

## Contexto

Os campos de confiança baixa precisam de uma pessoa, e a qualidade dos campos de confiança alta precisa ser medida continuamente, sem gabarito. A revisão é trabalho operacional: várias pessoas ao mesmo tempo, gravações linha a linha, resposta imediata na tela. Isso é trabalho de banco transacional, não de tabela analítica.

## Decisões

1. **Fila no lakehouse, decisões no Lakebase.** A fila (`lc_silver.fila_revisao`) é uma view do pipeline. As decisões vão para um Postgres gerenciado (Lakebase), declarado no bundle junto com o resto.
2. **Reserva de item.** Ao abrir um item, o revisor o reserva (`INSERT ... ON CONFLICT DO NOTHING`). Dois revisores nunca recebem o mesmo campo; a reserva expira em 15 minutos para não travar itens abandonados. Decisão e liberação da reserva acontecem na mesma transação.
3. **Duas origens na fila:**
   - campos de **confiança baixa** (ADR 002);
   - uma **amostra de auditoria** de 2% dos campos de confiança alta, sorteada de forma estável por documento e campo. Ela mede o acerto real em produção, onde não existe gabarito.
4. **Volta ao lakehouse.** O banco Postgres é registrado como catálogo no Unity Catalog (`lc_revisao`); a tarefa `sincronizar_revisoes` do job copia as decisões para o Delta com `MERGE`. A view `campos_finais` usa a decisão quando existe e o valor extraído quando não.
5. **App de revisão.** Databricks App em Streamlit: a página do PDF renderizada ao lado do valor, os três sinais de confiança e os botões Aprovar, Corrigir e Pular.
6. **Revisor simulado.** Para demonstrar o fluxo de ponta a ponta, um comando decide os itens com base no gabarito e grava como `revisor-simulado`, deixando alguns pendentes para a App. Numa empresa, essas decisões viriam de pessoas.

## Resultado

| Indicador | Valor |
|---|---|
| Itens na fila | 157 (156 de auditoria, 1 de confiança baixa) |
| Auditoria revisada | 149 campos, **100% aprovados** sem correção |
| Campos aceitos sem revisão | 98,8% |

O item de confiança baixa é o código de cliente lido errado pelo OCR (ADR 002); ele ficou pendente de propósito, para ser corrigido na App.

## Consequências

- A App roda com um service principal próprio, que precisa de permissões no Unity Catalog (leitura da fila e dos PDFs) e no Postgres (tabelas de revisão). Pelas regras de quem mantém o projeto, os comandos `GRANT` são executados manualmente; estão no README.
- Na primeira criação, a App falhou ao configurar o banco porque o papel do service principal ainda não existia no Postgres. Apagar e recriar a App resolveu; o problema não se repetiu.
- Com acerto tão alto, a fila é quase toda auditoria. É o comportamento esperado de um sistema que funciona: o custo humano fica concentrado em medir a qualidade, não em corrigir.
