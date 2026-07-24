# dbt/

dbt project for analytics transformations on Snowflake.

| Subdirectory | Purpose |
|--------------|---------|
| `models/`   | Staging, intermediate, and mart SQL models |
| `seeds/`    | Static reference data loaded via `dbt seed` |
| `macros/`   | Reusable Jinja/SQL macros |
