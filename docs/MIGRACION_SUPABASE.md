# Migracion de Django a Supabase PostgreSQL

Este proyecto usa Supabase como una base PostgreSQL administrada. Los usuarios,
contrasenas cifradas, grupos, sesiones, favoritos, alertas y notificaciones
continuan siendo gestionados por Django. Esta migracion no activa Supabase Auth.

## 1. Inicializacion desde cero

Como la base anterior no contiene datos recuperables, no es necesario ejecutar
`dumpdata`, `pg_dump` ni `loaddata`.

1. Crea el proyecto en Supabase.
2. Abre `SQL Editor`, pega `supabase/00_prepare_database.sql` y ejecutalo.
3. Completa el unico archivo activo `.env` usando `.env.example` como referencia.
4. En `Connect > Session pooler`, copia host, usuario, puerto y contrasena al
   archivo `.env`. No uses la anon key ni la service_role key.
5. Ejecuta:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_supabase.ps1
```

6. Para crear el administrador principal de la aplicacion:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_supabase.ps1 -CreateAdmin
```

7. Pega `supabase/01_verify_database.sql` en el SQL Editor para inspeccionar las
   tablas, privilegios y conteos iniciales.

8. Inicia Django usando ese archivo de credenciales:

```powershell
npm run dev:supabase
```

Las tablas se crean mediante las migraciones de Django. No pegues un esquema de
tablas generado a mano: eso desincronizaria `django_migrations`.

## 2. Antes de migrar una base existente

1. Confirma cual es la base de origen: PostgreSQL local o `db.sqlite3`.
2. Deten temporalmente los cambios en la aplicacion durante la exportacion final.
3. Conserva un respaldo probado de la base de origen.
4. Crea un proyecto en Supabase y guarda la contrasena de la base de datos.
5. Instala Python, las dependencias de `requirements.txt` y las herramientas de
   PostgreSQL si se utilizara `pg_dump`.

Nunca pegues contrasenas en este documento ni las confirmes en Git.

## 3. Conexion recomendada

Para desarrollo local o un servidor Django persistente en una red IPv4, abre
`Connect` en Supabase y elige `Session pooler`. Copia exactamente los valores
mostrados por Supabase; el host del pooler no debe construirse manualmente.

Configura `.env`:

```dotenv
DB_ENGINE=postgresql
DB_NAME=postgres
DB_USER=postgres.PROJECT_REF
DB_PASSWORD=YOUR_DATABASE_PASSWORD
DB_HOST=YOUR_SESSION_POOLER_HOST
DB_PORT=5432
DB_SSLMODE=require
DB_SCHEMA=django_app
DB_CONN_MAX_AGE=60
DB_CONNECT_TIMEOUT=10
DB_DISABLE_SERVER_SIDE_CURSORS=0
DB_DISABLE_PREPARED_STATEMENTS=0
```

Si el despliegue es serverless, usa el `Transaction pooler` del panel, puerto
6543, `DB_CONN_MAX_AGE=0` y activa `DB_DISABLE_SERVER_SIDE_CURSORS` y
`DB_DISABLE_PREPARED_STATEMENTS`.

## 4. Migracion de datos opcional

La base es pequena y utiliza modelos Django convencionales. `dumpdata` y
`loaddata` evitan copiar roles internos y esquemas administrados por Supabase.

### 3.1 Exportar desde la base de origen

Manteniendo `.env` apuntando a la base actual:

```powershell
New-Item -ItemType Directory -Force backups
python manage.py check
python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --exclude admin.logentry --indent 2 --output backups/django-data.json
```

El respaldo incluye los hashes de contrasena de Django, no las contrasenas en
texto plano. Aun asi, debe tratarse como un archivo sensible.

### 3.2 Crear el esquema en Supabase

Actualiza `.env` con los valores de Supabase y ejecuta:

```powershell
python manage.py check --database default
python manage.py migrate --noinput
python manage.py showmigrations
```

### 3.3 Importar los datos

```powershell
python manage.py loaddata backups/django-data.json
```

Si la base destino ya contiene datos de prueba, crea un proyecto Supabase nuevo
o limpia solamente las tablas de Django antes de importar. No borres los
esquemas internos `auth`, `storage`, `realtime`, `supabase_functions` ni
`extensions`.

## 5. Validacion antes del corte

Ejecuta:

```powershell
python manage.py check --deploy
python manage.py test
python manage.py shell -c "from django.contrib.auth.models import User, Group; from divisas.models import FavoriteCurrency, AdminNotification, ExchangeAlert, UserAlertNotification; print({'users': User.objects.count(), 'groups': Group.objects.count(), 'favorites': FavoriteCurrency.objects.count(), 'admin_notifications': AdminNotification.objects.count(), 'alerts': ExchangeAlert.objects.count(), 'alert_notifications': UserAlertNotification.objects.count()})"
```

Compara los conteos con la base de origen y verifica manualmente:

- inicio de sesion de un usuario normal y un administrador;
- grupos `NORMAL`, `SUPERVISOR` y `ADMINISTRADOR`;
- favoritos y alertas existentes;
- creacion y eliminacion de una alerta;
- dashboard y panel bursatil;
- envio de correo, si esta habilitado.

Solo despues de validar, cambia la aplicacion desplegada para que use Supabase.
Mantén la base anterior sin escrituras hasta confirmar el funcionamiento.

## 6. Alternativa PostgreSQL nativa

Para una base grande, usa `pg_dump`/`pg_restore` siguiendo la guia oficial de
Supabase. Realiza la importacion mediante la conexion indicada por Supabase para
migraciones y evita restaurar propietarios, roles globales o esquemas internos
de Supabase. Para este proyecto pequeno, el flujo Django anterior es mas seguro
y sencillo.

## 7. Seguridad del repositorio

`.env`, bases locales, logs, respaldos y `node_modules` estan excluidos por
`.gitignore`. Como esos archivos ya estuvieron versionados anteriormente,
agregarlos a `.gitignore` no los elimina del historial. Se deben rotar las
credenciales expuestas y limpiar el indice/historial en una tarea separada y
controlada.
