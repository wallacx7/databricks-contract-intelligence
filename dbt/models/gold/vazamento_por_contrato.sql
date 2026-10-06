-- Visão para o negócio: o que cada contrato deixou de faturar e quanto ainda deixa por mês.

with v as (
    select * from {{ ref('vazamento_mensal') }}
),

ultimo as (
    select max(mes) as mes from {{ ref('termos_mensais') }}
)

select
    v.contrato_id,
    v.account_id,
    any_value(v.cliente) as cliente,
    v.tipo,
    min(v.mes) as primeiro_mes,
    max(v.mes) as ultimo_mes,
    count(*) as meses,
    cast(sum(v.vazamento) as decimal(18, 2)) as vazamento_acumulado,
    cast(sum(case when v.mes = u.mes then v.vazamento else 0 end) as decimal(18, 2)) as vazamento_mes_atual,
    cast(sum(case when v.mes = u.mes then v.vazamento else 0 end) * 12 as decimal(18, 2)) as recuperavel_12_meses
from v
cross join ultimo u
group by v.contrato_id, v.account_id, v.tipo
