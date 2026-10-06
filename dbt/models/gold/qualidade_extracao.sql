-- Indicadores da extração e da revisão humana, numa linha. A auditoria mede o acerto real dos campos de
-- confiança alta sem depender de gabarito: é o número que acompanharia a qualidade em produção.

with campos as (
    select * from {{ source('contrato_vivo', 'campos_finais') }}
),

fila as (
    select * from {{ source('contrato_vivo', 'fila_revisao') }}
),

revisoes as (
    select * from {{ source('contrato_vivo', 'revisoes') }}
)

select
    (select count(distinct documento_id) from campos) as documentos,
    (select count(*) from campos) as campos,
    (select count_if(origem = 'automatico') from campos) as campos_automaticos,
    (select count_if(origem = 'revisado') from campos) as campos_revisados,
    (select count_if(origem = 'pendente') from campos) as campos_pendentes,
    (select count_if(motivo = 'confianca_baixa') from fila) as enviados_por_confianca_baixa,
    (select count_if(motivo = 'auditoria') from fila) as amostra_de_auditoria,
    (select count_if(motivo = 'auditoria') from revisoes) as auditoria_revisada,
    (select count_if(motivo = 'auditoria' and decisao = 'aprovado') from revisoes) as auditoria_aprovada,
    try_divide(
        (select count_if(motivo = 'auditoria' and decisao = 'aprovado') from revisoes),
        (select count_if(motivo = 'auditoria') from revisoes)
    ) as acerto_medido_na_auditoria
