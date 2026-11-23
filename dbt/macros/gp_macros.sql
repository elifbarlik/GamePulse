{# Use custom schema names as-is (silver / gold) instead of <target>_<custom>. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim }}{%- endif -%}
{%- endmacro %}

{# Raw timestamps are ISO-8601 strings ending in Z. Returns NULL when unparsable. #}
{% macro gp_parse_ts(col) -%}
  {%- if target.type == 'bigquery' -%}
    safe_cast({{ col }} as timestamp)
  {%- else -%}
    try_cast(replace({{ col }}, 'Z', '') as timestamp)
  {%- endif -%}
{%- endmacro %}

{% macro gp_safe_divide(num, den) -%}
  (1.0 * ({{ num }}) / nullif(({{ den }}), 0))
{%- endmacro %}

{% macro gp_incremental_strategy() -%}
  {{ 'merge' if target.type == 'bigquery' else 'delete+insert' }}
{%- endmacro %}
