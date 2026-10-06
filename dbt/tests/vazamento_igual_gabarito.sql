-- O vazamento encontrado precisa bater com o plantado pelo gerador, contrato a contrato e mês a mês.
-- Tolerância de um centavo por usuário: o gerador arredonda em Python e o dbt em SQL.

with gabarito as (
    select
        contrato_id,
        cast(mes as date) as mes,
        tipo,
        cast(vazamento as decimal(18, 2)) as vazamento,
        cast(usuarios_ativos as int) as usuarios
    from read_files('{{ var("gabarito_path") }}/vazamentos.csv', format => 'csv', header => true)
    where cast(mes as date) <= (select max(mes) from {{ ref('termos_mensais') }})
),

encontrado as (
    select contrato_id, mes, tipo, vazamento, usuarios_cobrados as usuarios
    from {{ ref('vazamento_mensal') }}
)

select
    coalesce(g.contrato_id, e.contrato_id) as contrato_id,
    coalesce(g.mes, e.mes) as mes,
    coalesce(g.tipo, e.tipo) as tipo,
    g.vazamento as esperado,
    e.vazamento as encontrado
from gabarito g
full outer join encontrado e using (contrato_id, mes, tipo)
where g.contrato_id is null
    or e.contrato_id is null
    or abs(g.vazamento - e.vazamento) > 0.01 * greatest(g.usuarios, 1) + 0.01
