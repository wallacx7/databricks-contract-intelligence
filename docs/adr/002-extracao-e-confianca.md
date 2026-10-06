# ADR 002: Extração com dois modelos e confiança verificável

- **Status:** aceito
- **Data:** 2026-10-06

## Contexto

A extração alimenta uma conta de dinheiro: um preço lido errado vira um "vazamento" falso ou esconde um verdadeiro. Modelos de linguagem não devolvem uma confiança calibrada, e revisar 100% dos campos à mão anularia o ganho da automação.

## Decisões

1. **Leitura uma vez só.** `ai_parse_document` e `ai_query` rodam em streaming tables: cada documento novo é lido e extraído uma vez, e reexecutar o pipeline não gasta tokens de novo. Mudar o prompt exige reprocessar só a tabela `extracoes` (`--full-refresh` dela), sem ler os PDFs outra vez.
2. **Saída estruturada.** O modelo responde num JSON Schema estrito, com 20 campos que aceitam `null`. O prompt explica as armadilhas do domínio: preço por usuário vs. valor mensal estimado, desconto promocional (temporário) vs. desconto de pagamento anual (permanente), reajuste por tabela vs. percentual fixo.
3. **Dois modelos.** O mesmo documento é extraído pelo GPT OSS 120B (principal) e pelo Qwen3 80B (segundo), servidos no workspace.
4. **Confiança alta** exige três sinais independentes:
   - **concordância:** os dois modelos chegam ao mesmo valor (após normalizar números, datas e textos);
   - **ancoragem:** para dinheiro, percentuais e inteiros, o valor aparece escrito no documento;
   - **validação:** identificadores têm o formato esperado e são coerentes entre si (o número do contrato termina com os dígitos do código do cliente).

   O resto vai para revisão humana (Fase 2).
5. **Reprocessamento de leituras.** Falhas transitórias do `ai_parse_document` (ex.: timeout numa página) são reenviadas por uma tarefa do job diário, que copia o PDF para `reprocessar/<carimbo>/`. As etapas seguintes usam a leitura bem-sucedida mais recente; há limite de 3 tentativas.
6. **Desenvolvimento vs. controle.** Os 196 documentos usados para ajustar prompt e regras ficam registrados em `lc_raw.conjunto_desenvolvimento`. A avaliação separa os dois conjuntos; a medida que vale é a do conjunto de controle, nunca usado em ajustes.

## O que a primeira rodada ensinou (conjunto de desenvolvimento)

| Rodada | Acerto | Confiança alta | Para revisão | Causa das falhas |
|---|---|---|---|---|
| 1 | 99,0% | 100% | 2,0% | GPT OSS não converteu "1º TERMO ADITIVO" em 1 (21 casos); deduziu "mensal" em aditivos a partir de "por usuário por mês" (18); ancoragem falhou quando a leitura quebrou a linha entre "R$" e o valor (39 revisões desnecessárias) |
| 2 | 100% | 100% | 0,0% | Regras no prompt para número do aditivo e periodicidade; ancoragem ignora quebras de linha |

Na rodada 1, **nenhum erro passaria sem revisão**: todos os campos errados tinham discordância entre os modelos. É o comportamento que o desenho procura: o segundo modelo não precisa ser melhor, só independente o bastante para discordar quando o primeiro erra.

## Resultado no conjunto de controle

Documentos de 280 clientes que não participaram dos ajustes, avaliados uma única vez:

| Conjunto | Documentos | Campos | Acerto | Acerto com confiança alta | Para revisão | Erros que passariam sem revisão |
|---|---|---|---|---|---|---|
| Controle | 455 | 9.100 | **99,99%** | **100%** | 0,01% (1 campo) | **0** |
| Desenvolvimento | 196 | 3.920 | 100% | 100% | 0% | 0 |

O único erro do controle foi o GPT OSS devolver `contrato_id` vazio num documento; o Qwen3 acertou, os dois discordaram e o campo foi para revisão. O documento cuja leitura falhou por timeout foi reprocessado pela tarefa `reprocessar_falhas` e lido com sucesso na segunda tentativa.

## Documentos digitalizados

Cerca de 15% dos documentos passaram a ser gerados como digitalização: imagem sem camada de texto, com rotação, ruído, desfoque, manchas e compressão, em três níveis. O `ai_parse_document` faz OCR nesses casos.

Primeira medição com os digitalizados (mesmos clientes, documentos regerados):

| Conjunto | Tipo | Documentos | Acerto | Erros que passariam sem revisão |
|---|---|---|---|---|
| Controle | Digital | 380 | 100% | 0 |
| Controle | Digitalização leve | 39 | 100% | 0 |
| Controle | Digitalização média | 28 | 99,82% | **1** |
| Controle | Digitalização forte | 8 | 100% | 0 |

O erro que passou mostra o limite da concordância: o OCR leu "NIM-002362" como "M-002362", e **os dois modelos, lendo o mesmo texto, concordaram no erro**. Concordância protege contra erro de modelo, não contra erro de leitura. A validação de formato e coerência de identificadores entrou como terceiro sinal e passou a mandar esse campo para revisão.

Como a regra foi criada olhando o conjunto de controle, ele deixa de ser independente para ela. O número que vale para essa etapa é o medido antes da regra (1 erro em 9.100 campos); o efeito da validação será medido num novo conjunto, com os clientes restantes, na fase final.

**Limitação:** os contratos vêm de quatro modelos de redação, e a digitalização é simulada. Contratos reais têm cláusulas fora do padrão, anotações à mão e digitalizações piores; o acerto seria menor.

## Consequências

- O custo de extração dobra (dois modelos por documento). Em troca, a revisão humana cai para os campos em que há motivo concreto de dúvida.
- Campos de data e texto dependem só da concordância; dois modelos que erram igual passariam. A taxa disso é medida pela avaliação (`erros_que_passariam`).
- Ao reprocessar uma tabela com `--full-refresh <tabela>`, o pipeline exclui as demais da execução; é preciso rodar uma atualização normal em seguida para recalcular as views.
