# Roadmap

## Fase 0: Fundação

- [x] Repositório, bundle e schemas `lc_*`
- [x] Viabilidade no Free Edition: `ai_parse_document`, extração com JSON Schema (14/14 campos numa amostra), Vector Search e Lakebase
- [x] ADR 001: arquitetura, origem dos dados e confiança por concordância
- [ ] Gerador de contratos e aditivos em PDF a partir do billing do Ledger, com vazamentos plantados e gabarito
- [ ] Job do gerador e testes

## Fase 1: Leitura e extração

- [ ] Pipeline: Auto Loader (binário) → `ai_parse_document` → texto por página
- [ ] Extração com dois modelos e JSON Schema, incremental (cada documento é lido uma vez)
- [ ] Validação (expectations), concordância e ancoragem
- [ ] Avaliação da extração por campo contra o gabarito

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
