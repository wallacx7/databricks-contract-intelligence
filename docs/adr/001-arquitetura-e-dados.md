# ADR 001: Arquitetura e origem dos dados

- **Status:** aceito
- **Data:** 2026-10-06

## Contexto

O projeto precisa de contratos em PDF realistas, de um billing para comparar com eles e de um gabarito para medir a extração e o vazamento de receita. Um conjunto público de contratos não teria billing correspondente nem gabarito.

## Decisões

### Os contratos nascem do billing do Ledger

O gerador lê as tabelas Silver do [Ledger](https://github.com/wallacx7/databricks-revenue-agent) no mesmo workspace (contas e histórico SCD2 das assinaturas) e escreve, para cada cliente **Mid-Market e Enterprise**, o contrato que deu origem à assinatura. Clientes SMB aderem a termos padrão e não têm contrato negociado, como acontece de fato em empresas SaaS.

- **Contrato:** emitido na criação da assinatura, com o plano, o preço por usuário e a quantidade de usuários da primeira versão.
- **Aditivos:** um por mudança de plano (upgrade ou downgrade), com o novo plano e preço.
- **Código do cliente** no cabeçalho (`NIM-000123` ↔ `acc_000123`), como sistemas de gestão de contratos fazem; é a chave de ligação com o billing.

Os dois projetos passam a ser produtos de dados que se consomem: o Contrato Vivo depende do Ledger, não de uma cópia dele.

### O vazamento é plantado em cláusulas, não no billing

O billing do Ledger é fixo; o gerador escreve cláusulas que dão direito a cobrar mais do que o billing cobra. Cada contrato recebe no máximo um vazamento de preço, e a cláusula de compromisso mínimo é independente:

| Tipo | Cláusula no contrato | Como o billing diverge |
|---|---|---|
| Desconto vencido | 15% de desconto nos primeiros 12 meses | Continua aplicando o desconto depois do prazo |
| Preço abaixo do contratado | Preço por usuário acima do cobrado | Cobra o preço de tabela antigo desde o início |
| Reajuste não aplicado | Reajuste anual fixo (4% a 8%) | Nunca reajusta |
| Compromisso mínimo | Mínimo de N usuários faturados | Cobra só os usuários ativos quando a conta encolhe |

Contratos sem vazamento usam cláusulas coerentes com o billing ("reajuste conforme tabela vigente", "desconto de 15% para pagamento anual antecipado", que o billing aplica). Essas cláusulas parecidas com as de vazamento são de propósito: a extração precisa distinguir desconto temporário de permanente.

O vazamento mensal de cada contrato é calculado pelo gerador, a partir do histórico do billing, e gravado no gabarito junto com o valor correto de cada campo de cada documento.

### Fluxo

```
Ledger (silver) ──► gerador ──► PDFs (Volume) ──► Auto Loader ──► ai_parse_document ──► texto por página
                        │                                                                   │
                        └──► gabarito                     extração com dois modelos ◄──────┘
                                                                     │
                                         confiança alta ─────────────┼──── confiança baixa ──► App de revisão (Lakebase)
                                                                     ▼                                │
                                                    contrato vigente (dbt) ◄──────────── decisões ◄──┘
                                                                     │
                                       billing do Ledger ──► reconciliação ──► vazamento ──► dashboard
                                                                     │
                                         trechos ──► Vector Search ──► agente com citação
```

### Confiança por concordância

Modelos de linguagem não devolvem uma confiança calibrada. A confiança de cada campo vem de dois sinais verificáveis:

1. **Concordância:** o documento é extraído por dois modelos diferentes servidos no workspace. Valores iguais indicam extração estável.
2. **Ancoragem:** o valor extraído aparece no texto da página que o modelo citou como origem.

Campos que concordam e estão ancorados seguem direto. Os demais vão para a revisão humana. A taxa de acerto de cada faixa é medida contra o gabarito, o que permite ajustar o critério com dados.

### Nomes

Os schemas usam o prefixo `lc_` (live contract), porque o catálogo é dividido com o Ledger, que já usa `raw`, `bronze`, `silver` e `gold`.

## Consequências

- O Contrato Vivo só roda num workspace onde o Ledger já rodou. O schema de origem é uma variável do bundle.
- Os números de vazamento são de um cenário simulado; o que o projeto demonstra é o método e a medição.
- Rodar a extração em todos os documentos consome cota de tokens do Free Edition; o desenvolvimento usa um subconjunto.
