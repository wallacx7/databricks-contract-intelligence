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

- [x] Fila de revisão no Lakebase (confiança baixa e auditoria de 2%)
- [x] Databricks App de revisão com a página do contrato ao lado do valor
- [x] Decisões de volta ao lakehouse pelo catálogo do Unity Catalog

## Fase 3: Reconciliação

- [x] Contrato vigente (contrato + aditivos + correções) em dbt
- [x] Reconciliação com o billing e vazamento por tipo (idêntico ao plantado)
- [x] Testes contra o gabarito e dashboard

## Fase 4: Perguntas sobre contratos

- [x] Trechos indexados no Vector Search, com embeddings em lote
- [x] Agente com citação de documento e página
- [x] Avaliação com valor e página citada (controle: 94,8%)

## Fase 5: Lançamento

- [x] README e ADRs 001 a 005
- [ ] Prints, GIF e post
- [ ] Repositório público

## Próximos passos

- [ ] Agente: total do vazamento quando há mais de um tipo; pesquisa pelo nome exato do cliente; novo conjunto de controle
- [ ] Novo conjunto de controle de extração com os clientes restantes
