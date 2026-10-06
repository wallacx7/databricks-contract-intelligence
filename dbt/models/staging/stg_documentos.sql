-- Uma linha por documento, com os campos finais (extração ou decisão do revisor) já tipados.

with campos as (
    select documento_id, campo, valor_final, origem
    from {{ source('contrato_vivo', 'campos_finais') }}
),

pivotado as (
    select
        documento_id,
        max(case when campo = 'tipo_documento' then valor_final end) as tipo_documento,
        upper(max(case when campo = 'contrato_id' then valor_final end)) as contrato_id,
        try_cast(max(case when campo = 'numero_aditivo' then valor_final end) as int) as numero_aditivo,
        upper(max(case when campo = 'codigo_cliente' then valor_final end)) as codigo_cliente,
        max(case when campo = 'cliente' then valor_final end) as cliente,
        try_to_date(max(case when campo = 'data_assinatura' then valor_final end)) as data_assinatura,
        try_to_date(max(case when campo = 'inicio_vigencia' then valor_final end)) as inicio_vigencia,
        try_to_date(max(case when campo = 'fim_vigencia' then valor_final end)) as fim_vigencia,
        max(case when campo = 'plano' then valor_final end) as plano,
        try_cast(max(case when campo = 'preco_usuario' then valor_final end) as decimal(18, 2)) as preco_usuario,
        try_cast(max(case when campo = 'usuarios_contratados' then valor_final end) as int) as usuarios_contratados,
        max(case when campo = 'periodicidade' then valor_final end) as periodicidade,
        try_cast(max(case when campo = 'desconto_anual_percentual' then valor_final end) as double)
            as desconto_anual_percentual,
        try_cast(max(case when campo = 'desconto_promocional_percentual' then valor_final end) as double)
            as desconto_promocional_percentual,
        try_cast(max(case when campo = 'desconto_promocional_meses' then valor_final end) as int)
            as desconto_promocional_meses,
        max(case when campo = 'reajuste_tipo' then valor_final end) as reajuste_tipo,
        try_cast(max(case when campo = 'reajuste_percentual' then valor_final end) as double) as reajuste_percentual,
        try_cast(max(case when campo = 'minimo_usuarios' then valor_final end) as int) as minimo_usuarios,
        try_cast(max(case when campo = 'multa_percentual' then valor_final end) as double) as multa_percentual,
        try_cast(max(case when campo = 'multa_limite_mensalidades' then valor_final end) as int)
            as multa_limite_mensalidades,
        count_if(origem = 'pendente') as campos_pendentes,
        count_if(origem = 'revisado') as campos_revisados
    from campos
    group by documento_id
)

select
    *,
    -- Código do cliente no contrato (NIM-000123) corresponde à conta no billing do Ledger (acc_000123).
    concat('acc_', regexp_extract(codigo_cliente, '([0-9]{6})', 1)) as account_id
from pivotado
