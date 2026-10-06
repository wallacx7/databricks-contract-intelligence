{#- Pastas declaram o schema lógico; o físico vem da variável <schema>_schema (dev_<usuário>_lc_gold em dev). -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ var(custom_schema_name ~ '_schema', target.schema) }}
    {%- endif -%}
{%- endmacro %}
