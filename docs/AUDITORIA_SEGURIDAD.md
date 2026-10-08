# Auditoria de Seguridad de Red

## Herramientas solicitadas

- Nmap
- Angry IP Scanner

## Comandos sugeridos (Nmap)

Escaneo de host especifico:
```bash
nmap -sV -Pn <IP_OBJETIVO>
```

Escaneo de toda la red local:
```bash
nmap -sV -sn 192.168.1.0/24
```

Escaneo de puertos comunes:
```bash
nmap -sV -Pn -p 21,22,23,25,53,80,135,139,443,445,3306,5432,8000 <IP_OBJETIVO>
```

## Baseline local levantado en este entorno

Se obtuvo inventario inicial con:
```bash
netstat -ano | findstr LISTENING
```

Puertos observados (extracto):
- 135, 139, 445
- 3306 (MySQL)
- 5432 (PostgreSQL)
- 8080
- varios puertos altos del sistema (49664+)

Nota:
- `nmap` no estaba instalado en este entorno de trabajo al momento de esta corrida.
- El escaneo formal con Nmap/Angry IP debe ejecutarse en el equipo objetivo para reporte definitivo.

## Riesgos detectados (preliminar)

1. Exposicion de puertos de base de datos (`3306`, `5432`) en `0.0.0.0`.
2. Exposicion de SMB (`445`) y NetBIOS (`139`) en interfaces de red.
3. Multiples servicios escuchando en todas las interfaces, ampliando superficie de ataque.

## Puertos potencialmente innecesarios

- 3306 si la app no usa MySQL.
- 8080 si no hay servicio requerido en ese puerto.
- Cualquier puerto de desarrollo no usado para pruebas del proyecto.

## Nivel de seguridad (preliminar)

- Estado actual: **Medio**.
- Motivo: existen controles de aplicacion (auth, roles, validaciones, logs), pero hay superficie de red amplia a validar/reducir.

## Recomendaciones

1. Restringir bases de datos a `127.0.0.1` cuando sea posible.
2. Bloquear puertos innecesarios con firewall.
3. Ejecutar Nmap en cada entrega para evidencia de hardening.
4. Mantener `DEBUG=0` y variables sensibles fuera del codigo.
5. Revisar `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` por ambiente.
