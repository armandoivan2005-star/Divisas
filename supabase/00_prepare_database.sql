-- DIVISAS: preparacion inicial de Supabase para Django.
-- Pega el archivo completo en Supabase > SQL Editor y pulsa Run una sola vez.
--
-- Las tablas NO se crean a mano: `python manage.py migrate` las crea despues
-- y registra correctamente todas las migraciones de Django.

begin;

create schema if not exists django_app authorization postgres;

-- La aplicacion usa una conexion PostgreSQL de servidor. No utiliza las claves
-- anon/authenticated ni la Data API de Supabase.
revoke all on schema django_app from public;
revoke all on schema django_app from anon, authenticated;
grant usage, create on schema django_app to postgres;

-- Evita que objetos futuros creados por postgres en este esquema reciban
-- privilegios de la Data API por cambios de configuracion del proyecto.
alter default privileges for role postgres in schema django_app
    revoke select, insert, update, delete, truncate, references, trigger
    on tables from anon, authenticated;

alter default privileges for role postgres in schema django_app
    revoke usage, select, update on sequences from anon, authenticated;

alter default privileges for role postgres in schema django_app
    revoke execute on functions from public, anon, authenticated;

commit;

-- Resultado esperado: una fila con schema_name = django_app.
select schema_name
from information_schema.schemata
where schema_name = 'django_app';
