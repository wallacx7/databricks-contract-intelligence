-- Para cada contrato e mês fechado em que a conta estava ativa no billing: o documento vigente, o preço por
-- usuário que o contrato manda cobrar e o que o billing cobrou de fato.
--
-- Preço devido = preço do documento vigente
--   x (1 - desconto promocional)   se o documento vigente é o contrato e ainda está dentro do prazo
--   x (1 - desconto anual)         se o pagamento é anual antecipado
--   x reajuste                     fixo: (1 + r) ^ aniversários desde o documento; tabela: reajustes do período

with documentos as (
    select * from {{ ref('stg_documentos') }}
),

contratos as (
    select * from documentos where tipo_documento = 'contrato'
),

ultimo_mes as (
    select max(mes) as mes
    from {{ source('ledger_metrics', 'mrr_mensal') }}
    where mes_fechado and segmento = 'total'
),

billing as (
    select s.mes, s.account_id, s.plano, s.assentos, s.mrr
    from {{ source('ledger_gold', 'fct_mrr_snapshot_mensal') }} s
    cross join ultimo_mes u
    where s.mes <= u.mes
),

meses as (
    select
        c.contrato_id,
        c.account_id,
        c.cliente,
        b.mes,
        add_months(b.mes, 1) as corte,  -- fim do mês: 00:00 do dia 1º seguinte
        b.plano as plano_cobrado,
        b.assentos,
        cast(b.mrr / b.assentos as decimal(18, 2)) as preco_cobrado,
        c.inicio_vigencia as inicio_contrato,
        c.desconto_promocional_percentual,
        c.desconto_promocional_meses,
        c.desconto_anual_percentual,
        c.reajuste_tipo,
        c.reajuste_percentual,
        c.minimo_usuarios
    from contratos c
    join billing b
        on b.account_id = c.account_id
        and b.mes >= date_trunc('MONTH', c.inicio_vigencia)
),

com_vigente as (
    select
        m.*,
        d.documento_id as documento_vigente,
        d.tipo_documento as tipo_vigente,
        d.inicio_vigencia as inicio_vigente,
        d.preco_usuario as preco_documento,
        row_number() over (partition by m.contrato_id, m.mes order by d.inicio_vigencia desc) as n
    from meses m
    join documentos d
        on d.contrato_id = m.contrato_id
        and d.inicio_vigencia < m.corte
),

calendario as (
    select
        *,
        greatest(
            0,
            (year(corte) - year(inicio_contrato)) * 12 + month(corte) - month(inicio_contrato)
            - case when day(corte) <= day(inicio_contrato) then 1 else 0 end
        ) as meses_completos,
        {{ aniversarios('inicio_contrato', 'corte') }} - {{ aniversarios('inicio_contrato', 'inicio_vigente') }}
            as anos_de_reajuste
    from com_vigente
    where n = 1
),

fator_tabela as (
    select
        c.contrato_id,
        c.mes,
        coalesce(exp(sum(ln(1 + r.percentual / 100))), 1) as fator
    from calendario c
    left join {{ ref('reajustes_de_tabela') }} r
        on r.plano = c.plano_cobrado
        and c.inicio_vigente < r.data_vigencia
        and r.data_vigencia < c.corte
    group by c.contrato_id, c.mes
)

select
    c.contrato_id,
    c.account_id,
    c.cliente,
    c.mes,
    c.documento_vigente,
    c.assentos,
    c.minimo_usuarios,
    c.preco_cobrado,
    cast(round(
        c.preco_documento
        * case
            when c.tipo_vigente = 'contrato' and c.desconto_promocional_meses is not null
                and c.meses_completos < c.desconto_promocional_meses
            then 1 - c.desconto_promocional_percentual / 100
            else 1
        end
        * coalesce(1 - c.desconto_anual_percentual / 100, 1)
        * case
            when c.reajuste_tipo = 'fixo' then pow(1 + c.reajuste_percentual / 100, c.anos_de_reajuste)
            else f.fator
        end,
        2
    ) as decimal(18, 2)) as preco_devido,
    case
        when c.desconto_promocional_percentual is not null then 'desconto_vencido'
        when c.reajuste_tipo = 'fixo' then 'reajuste_nao_aplicado'
        else 'preco_abaixo'
    end as tipo_vazamento_de_preco
from calendario c
join fator_tabela f using (contrato_id, mes)
