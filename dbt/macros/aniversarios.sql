{#- Quantos aniversários de `inicio` aconteceram antes de `ate` (exclusivo). Mesma regra do gerador. -#}
{% macro aniversarios(inicio, ate) -%}
    greatest(
        0,
        year({{ ate }}) - year({{ inicio }})
        - case
            when month({{ ate }}) * 100 + day({{ ate }}) <= month({{ inicio }}) * 100 + day({{ inicio }}) then 1
            else 0
        end
    )
{%- endmacro %}
