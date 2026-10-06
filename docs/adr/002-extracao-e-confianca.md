# ADR 002: Extração com dois modelos e confiança verificável

- **Status:** aceito
- **Data:** 2026-10-06

## Contexto

A extração alimenta uma conta de dinheiro: um preço lido errado vira um "vazamento" falso ou esconde um verdadeiro. Modelos de linguagem não devolvem uma confiança calibrada, e revisar 100% dos campos à mão anularia o ganho da automação.

## Decisões

1. **Leitura uma vez só.** `ai_parse_document` e `ai_query` rodam em streaming tables: cada documento novo é lido e extraído uma vez, e reexecutar o pipeline não gasta tokens de novo. Mudar o prompt exige reprocessar só a tabela `extracoes` (`--full-refresh` dela), sem ler os PDFs outra vez.
2. **Saída estruturada.** O modelo responde num JSON Schema estrito, com 20 campos que aceitam `null`. O prompt explica as armadilhas do domínio: preço por usuário vs. valor mensal estimado, desconto promocional (temporário) vs. desconto de pagamento anual (permanente), reajuste por tabela vs. percentual fixo.
3. **Dois modelos.** O mesmo documento é extraído pelo GPT OSS 120B (principal) e pelo Qwen3 80B (segundo), servidos no workspace.
4. **Confiança alta** exige: os dois modelos concordam (após normalizar números, datas e textos) **e**, para dinheiro, percentuais e inteiros, o valor aparece escrito no documento (ancoragem). O resto vai para revisão humana (Fase 2).
5. **Reprocessamento de leituras.** Falhas transitórias do `ai_parse_document` (ex.: timeout numa página) são reenviadas por uma tarefa do job diário, que copia o PDF para `reprocessar/<carimbo>/`. As etapas seguintes usam a leitura bem-sucedida mais recente; há limite de 3 tentativas.
6. **Desenvolvimento vs. controle.** Os 196 documentos usados para ajustar prompt e regras ficam registrados em `lc_raw.conjunto_desenvolvimento`. A avaliação separa os dois conjuntos; a medida que vale é a do conjunto de controle, nunca usado em ajustes.

## O que a primeira rodada ensinou (conjunto de desenvolvimento)

| Rodada | Acerto | Confiança alta | Para revisão | Causa das falhas |
|---|---|---|---|---|
| 1 | 99,0% | 100% | 2,0% | GPT OSS não converteu "1º TERMO ADITIVO" em 1 (21 casos); deduziu "mensal" em aditivos a partir de "por usuário por mês" (18); ancoragem falhou quando a leitura quebrou a linha entre "R$" e o valor (39 revisões desnecessárias) |
| 2 | 100% | 100% | 0,0% | Regras no prompt para número do aditivo e periodicidade; ancoragem ignora quebras de linha |

Na rodada 1, **nenhum erro passaria sem revisão**: todos os campos errados tinham discordância entre os modelos. É o comportamento que o desenho procura: o segundo modelo não precisa ser melhor, só independente o bastante para discordar quando o primeiro erra.

## Resultado no conjunto de controle

A preencher após a execução com os documentos de 280 clientes que não participaram dos ajustes.

## Consequências

- O custo de extração dobra (dois modelos por documento). Em troca, a revisão humana cai para os campos em que há motivo concreto de dúvida.
- Campos de data e texto dependem só da concordância; dois modelos que erram igual passariam. A taxa disso é medida pela avaliação (`erros_que_passariam`).
- Ao reprocessar uma tabela com `--full-refresh <tabela>`, o pipeline exclui as demais da execução; é preciso rodar uma atualização normal em seguida para recalcular as views.
