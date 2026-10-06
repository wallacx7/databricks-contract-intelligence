# ADR 005: Agente com citação e embeddings em lote

- **Status:** aceito
- **Data:** 2026-10-06

## Contexto

Quem lida com contratos não aceita uma resposta sem fonte. O agente precisa dizer de qual documento e de qual página tirou cada fato, levar em conta os aditivos e recusar o que os contratos não respondem.

## Decisões

1. **Ferramentas:**
   - `localizar_contrato`: pelo nome do cliente;
   - `termos_do_contrato`: um campo por linha, com documento e página de origem;
   - `buscar_clausulas`: Vector Search, busca híbrida filtrada pelo contrato;
   - `vazamento_do_contrato`: o resultado da reconciliação.

   Mesma arquitetura do agente do Ledger: argumentos validados (o número do contrato precisa ter o formato `CT-AAAA-NNNNNN`), SQL parametrizado e laço testável com implementações falsas.
2. **Citação obrigatória** no formato `(documento, p. N)`, com documento e página vindos das ferramentas. A página de cada campo é localizada no pipeline (onde o valor aparece escrito, inclusive datas por extenso).
3. **Valores formatados pela ferramenta:** reais, percentuais e datas no formato brasileiro, para o modelo copiar em vez de converter.
4. **Embeddings em lote.** O índice no modo gerenciado calculava os embeddings um a um pelo endpoint: cerca de 30 trechos por minuto no Free Edition, mais de 4 horas para 10.537 trechos. Os embeddings passaram a ser calculados com `ai_query` em lote no `MERGE` da tabela de origem, só para trechos novos ou alterados (500 em 9 segundos), e o índice usa os vetores prontos. Na pergunta, o agente calcula o embedding da consulta e faz busca híbrida (vetor + palavras). O índice completo ficou pronto em 3 minutos.

## Avaliação

As perguntas são geradas do gabarito: multa de rescisão, preço vigente (exige considerar o aditivo mais recente), fim da vigência, compromisso mínimo, quanto o contrato deixou de faturar e perguntas fora do escopo. Cada resposta é conferida no valor **e** na página citada.

| Rodada | Conjunto | Acerto | Citação na página certa | O que mudou |
|---|---|---|---|---|
| 1 | Ajuste (70) | 58,6% | 57% | — |
| 2 | Ajuste (70) | 95,7% | 95% | Avaliador passou a aceitar hífen tipográfico ("CT‑2021‑000310"); páginas de datas escritas por extenso; datas formatadas pela ferramenta |
| — | **Controle (77)** | **94,8%** | **97%** | Outros contratos, rodado uma única vez |

Resultado do controle por categoria: multa, vigência, compromisso mínimo e recusas fora do escopo **100%**; preço vigente 90%; vazamento 71%. Latência mediana de 3 segundos.

## Limitações conhecidas (falhas do controle)

- **Contrato com dois tipos de vazamento:** a ferramenta devolve uma linha por tipo, e o agente informou só uma delas em vez do total (2 casos), e numa resposta inventou uma citação para o resultado da reconciliação. Correção natural: a ferramenta devolver também o total do contrato, e a regra de citação deixar claro que valores da reconciliação não têm página.
- **Busca por nome parcial:** com o nome completo do cliente na pergunta, o agente pesquisou só parte dele, achou contratos de empresas parecidas e pediu para o usuário escolher (2 casos). Correção natural: pesquisar primeiro o nome exato.

Corrigir esses pontos olhando o conjunto de controle o transformaria em conjunto de ajuste; a próxima rodada precisaria de um controle novo.

## Consequências

- O índice depende da tabela `trechos_indice` (Delta com Change Data Feed), atualizada por `MERGE`; recriá-la exige recriar o índice.
- Trocar o modelo de embedding exige recalcular todos os vetores e recriar o índice, porque a consulta precisa usar o mesmo modelo.
