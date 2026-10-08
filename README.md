# Financias Web (Django + Tailwind)

Proyecto web con autenticacion, roles (`ADMINISTRADOR`, `SUPERVISOR` y `NORMAL`), rutas protegidas, manejo de sesiones, validaciones y trazabilidad de eventos de seguridad.

## Funcionalidades principales

- Navegacion persistente.
- Breadcrumbs.
- Mapa del sitio.
- Pagina 404 personalizada.
- Paginas de Inicio, Login, Registro y Dashboard (protegido).
- Acceso de supervisor al dashboard y consultas en modo estrictamente de solo lectura.
- Consumo de datos externos (Frankfurter y Yahoo Finance, con TwelveData como respaldo opcional).
- Validaciones frontend y backend.
- Registro de logs de acceso, login y errores.

## Configuracion de entorno

1. Copia `.env.example` a `.env`.
2. Completa credenciales reales y llaves.
3. Por defecto se usa `sqlite`; para PostgreSQL cambia `DB_ENGINE=postgresql`.

### Supabase

El proyecto puede usar Supabase como PostgreSQL administrado sin cambiar los
modelos ni reemplazar la autenticacion de Django. Consulta el procedimiento de
migracion, respaldo y validacion en `docs/MIGRACION_SUPABASE.md`.

Para inicializar una base nueva:

1. Ejecuta `supabase/00_prepare_database.sql` en el SQL Editor.
2. Completa las credenciales de Supabase en el unico archivo activo `.env`.
3. Ejecuta `powershell -ExecutionPolicy Bypass -File scripts/setup_supabase.ps1`.
4. Inicia la aplicacion con `npm run dev:supabase`.

El comando Supabase sirve los archivos estaticos compilados solamente durante
el desarrollo local. En produccion deben servirse con el proxy o plataforma de
despliegue correspondiente.

## Instalacion

1. Instala dependencias Python:
```bash
pip install -r requirements.txt
```
2. Instala dependencias Node:
```bash
npm install
```

## Ejecucion local

1. CSS en modo watch + Django:
```bash
npm run dev
```
2. Solo Django:
```bash
npm run runserver
```

## Ejecucion en red local (LAN)

1. Configura `ALLOWED_HOSTS` en `.env` (por ejemplo: `127.0.0.1,localhost,192.168.1.234`).
2. Inicia servidor en todas las interfaces:
```bash
npm run runserver:lan
```
3. Accede desde otro equipo:
```text
http://IP_LOCAL_DEL_SERVIDOR:8000
```

## Logs de seguridad

- Archivo: `logs/security.log`
- Incluye:
  - Eventos de login exitoso/fallido/restringido.
  - Accesos a rutas y codigos HTTP.
  - Intentos denegados en rutas protegidas.

## Pruebas basicas

```bash
python manage.py test
```

## Documentacion de auditoria y reporte

- Auditoria de seguridad: `docs/AUDITORIA_SEGURIDAD.md`
- Reporte final: `docs/REPORTE_FINAL.md`
