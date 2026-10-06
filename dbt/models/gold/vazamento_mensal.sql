-- Receita que o contrato dá direito de cobrar e o billing não cobrou, por contrato, mês e tipo.

with termos as (
    select * from {{ ref('termos_mensais') }}
),

preco as (
    select
        contrato_id,
        account_id,
        cliente,
        mes,
        documento_vigente,
        tipo_vazamento_de_preco as tipo,
        assentos as usuarios_cobrados,
        assentos as usuarios_devidos,
        preco_devido,
        preco_cobrado,
        cast(round(assentos * (preco_devido - preco_cobrado), 2) as decimal(18, 2)) as vazamento
    from termos
    where preco_devido - preco_cobrado > {{ var('tolerancia_por_usuario') }}
),

minimo as (
    select
        contrato_id,
        account_id,
        cliente,
        mes,
        documento_vigente,
        'minimo_nao_cobrado' as tipo,
        assentos as usuarios_cobrados,
        minimo_usuarios as usuarios_devidos,
        preco_devido,
        preco_cobrado,
        cast(round((minimo_usuarios - assentos) * preco_devido, 2) as decimal(18, 2)) as vazamento
    from termos
    where minimo_usuarios > assentos
)

select * from preco
union all
select * from minimo
