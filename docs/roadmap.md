# Roadmap

## Fase 0: Fundação

- [x] Repositório, bundle e schemas `lc_*`
- [x] Viabilidade no Free Edition: `ai_parse_document`, extração com JSON Schema (14/14 campos numa amostra), Vector Search e Lakebase
- [x] ADR 001: arquitetura, origem dos dados e confiança por concordância
- [x] Gerador de contratos e aditivos em PDF a partir do billing do Ledger, com vazamentos plantados e gabarito
- [x] Job do gerador e testes (2.219 documentos, 5.060 páginas na geração completa)

## Fase 1: Leitura e extração

- [x] Pipeline: Auto Loader (binário) → `ai_parse_document` → texto por página
- [x] Extração com dois modelos e JSON Schema, incremental (cada documento é lido uma vez)
- [x] Validação (expectations), concordância e ancoragem
- [x] Avaliação da extração por campo contra o gabarito, separando desenvolvimento e controle
- [x] Reprocessamento de leituras que falharam
- [x] Resultado no conjunto de controle: 99,99% em 9.100 campos, 0 erros com confiança alta
- [x] Lote de documentos digitalizados com ruído (14% dos documentos, três níveis)
- [x] Validação de formato e coerência de identificadores como terceiro sinal de confiança
- [ ] Novo conjunto de controle com os clientes restantes (fase final)

## Fase 2: Revisão humana

- [ ] Fila de revisão no Lakebase
- [ ] Databricks App de revisão com o trecho do contrato ao lado do valor
- [ ] Decisões de volta ao lakehouse

## Fase 3: Reconciliação

- [ ] Contrato vigente (contrato + aditivos + correções) em dbt
- [ ] Reconciliação com o billing e vazamento por tipo
- [ ] Testes contra o gabarito e dashboard

## Fase 4: Perguntas sobre contratos

- [ ] Trechos indexados no Vector Search
- [ ] Agente com citação de contrato, página e cláusula
- [ ] Avaliação com LLM como juiz

## Fase 5: Lançamento

- [ ] README, ADRs, prints e post
