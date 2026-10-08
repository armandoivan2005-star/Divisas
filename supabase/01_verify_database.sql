-- Ejecuta este bloque DESPUES de scripts/setup_supabase.ps1.

select table_name
from information_schema.tables
where table_schema = 'django_app'
order by table_name;

-- anon y authenticated deben ser false; postgres debe ser true.
select
    has_schema_privilege('anon', 'django_app', 'usage') as anon_has_usage,
    has_schema_privilege('authenticated', 'django_app', 'usage') as authenticated_has_usage,
    has_schema_privilege('postgres', 'django_app', 'usage') as postgres_has_usage;

-- Conteos iniciales. auth_user sera 0 hasta crear el administrador.
select
    (select count(*) from django_app.auth_user) as users,
    (select count(*) from django_app.auth_group) as groups,
    (select count(*) from django_app.divisas_favoritecurrency) as favorites,
    (select count(*) from django_app.divisas_exchangealert) as alerts;
