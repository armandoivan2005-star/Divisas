# Reporte Final del Proyecto

## 1. Introduccion

Se desarrollo un sitio web funcional orientado a gestion financiera, con autenticacion, roles, rutas protegidas y consumo de APIs externas.  
El objetivo fue cubrir requerimientos funcionales y de seguridad, incorporando controles tecnicos y evidencia de pruebas.

## 2. Analisis (requerimientos funcionales y de seguridad)

### Requerimientos funcionales cubiertos

- Navegacion persistente.
- Secciones principales: Inicio, Login, Registro, Dashboard.
- Pagina 404.
- Mapa del sitio.
- Breadcrumbs.
- Consumo de APIs para datos de divisas y acciones.
- Interacciones dinamicas en frontend (eventos, actualizacion de contenido, graficas).

### Requerimientos de seguridad cubiertos

- Autenticacion basada en Django.
- Proteccion de rutas con `@login_required` y validacion de rol.
- Manejo de sesion con middleware de autenticacion.
- Roles `ADMINISTRADOR`, `SUPERVISOR` y `NORMAL`.
- Sanitizacion y validacion de inputs.
- Manejo controlado de errores con vistas 403/404/500.
- Logging de accesos, errores y eventos de login.

## 3. Diseño (arquitectura, navegacion, roles)

### Arquitectura

- Backend y renderizado con Django (plantillas).
- Estilos con Tailwind.
- Consumo de APIs externas:
  - Frankfurter (tipos de cambio).
  - TwelveData (acciones).

### Navegacion

- Menu persistente en layout base.
- Breadcrumbs generados por contexto.
- Mapa del sitio con enlaces publicos y privados.
- Paginas de error personalizadas.

### Roles

- `NORMAL`: uso de funciones de usuario final.
- `SUPERVISOR`: acceso de solo lectura al dashboard, consultas y listados.
- `ADMINISTRADOR`: acceso a dashboard, panel de acciones y administracion de usuarios.

## 4. Desarrollo (tecnologias y componentes)

### Tecnologias

- Python + Django
- PostgreSQL
- TailwindCSS
- JavaScript para dinamismo del lado cliente

### Componentes principales

- Vistas y validaciones de autenticacion/registro.
- CRUD de usuarios por rol en dashboard.
- Alertas de divisas y favoritos.
- Panel de acciones para administradores.
- Middleware de logging de seguridad.

## 5. Seguridad implementada

- Variables sensibles en entorno (`.env`) y plantilla `.env.example`.
- `DEBUG` configurable por entorno (seguro por defecto).
- `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` por variable de entorno.
- Cookies de sesion HttpOnly.
- Politicas de seguridad basicas (`X_FRAME_OPTIONS`, `SECURE_CONTENT_TYPE_NOSNIFF`).
- Sanitizacion de entrada para consultas de simbolos.
- Registro de eventos de seguridad en `logs/security.log`.

## 6. Pruebas de seguridad

### Pruebas automaticas implementadas

- Acceso a rutas publicas.
- Proteccion de dashboard para usuarios no autenticados.
- Bloqueo de dashboard para usuarios sin rol admin.
- Acceso permitido para admin principal.
- Validacion de pagina 404.
- Prueba unitaria de sanitizacion de input.

### Auditoria de red

- Se incluyo procedimiento y analisis en `docs/AUDITORIA_SEGURIDAD.md`.
- Se levantaron puertos en escucha como baseline con `netstat`.
- Se documenta pendiente de corrida final con Nmap/Angry IP en ambiente objetivo.

## 7. Resultados

Se obtuvo un sistema funcional que cumple los criterios de navegacion, autenticacion, proteccion de rutas, validaciones y controles base de seguridad, incluyendo observabilidad por logs y documentacion de auditoria.

## 8. Conclusiones

El proyecto alcanza un nivel de seguridad y funcionalidad adecuado para entorno academico y de desarrollo controlado.  
Como siguiente mejora, se recomienda reforzar hardening de red (cierre de puertos no usados), automatizar auditorias y mantener segregacion estricta por ambiente (dev/test/prod).
