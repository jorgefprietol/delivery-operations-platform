# Operación, recuperación e infraestructura

## Diagnóstico

```powershell
docker compose ps
docker compose logs --tail 100 api
Invoke-RestMethod http://127.0.0.1:18095/health/ready
```

En Grafana: entrar con `admin` y `GRAFANA_PASSWORD`, abrir **Platform Engineering → Delivery Operations | Engineering Overview**. Los datos del panel web se consultan manualmente al conectar o actualizar. Las series de Grafana se refrescan cada diez segundos.

Compose utiliza una red independiente `10.240.95.0/24`, configurable mediante `DELIVERY_SUBNET` en `.env`. Si ese rango coincide con una red de tu entorno, elegir uno libre antes de iniciar; no es necesario eliminar redes de otros proyectos.

## Recuperación de registros

Ante un fallo confirmado por el integrador, registrar `fail` sobre el release activo usando su versión actual. Ejecutar la restauración real de su imagen predecesora, comprobar su salud y luego registrar `rollback`. La API mueve el puntero activo y registra la recuperación en una sola transacción. Si no hay predecesor saludable, ejecutar y registrar una nueva entrega aprobada.

## Recuperación de la propia plataforma

Conservar el digest conocido de la versión anterior. Cambiar `APP_IMAGE` en `.env` a ese digest y ejecutar `docker compose up -d --no-build --wait`. Confirmar readiness y consultar los registros. Esta operación es manual; el proyecto no instala un runner con acceso permanente a la máquina.

El esquema inicial es compatible con sus entregas actuales. Antes de cambios de esquema se necesita migración y backup con prueba de restauración. Nunca ejecutar `docker compose down --volumes` si se deben preservar los registros. Los jobs CI usan sus propios volúmenes efímeros y sí los eliminan al terminar.

## Backup SQLite

La copia debe usar la API de backup de SQLite, que incluye el estado confirmado aun con WAL activo:

```powershell
docker compose exec api python -c "import sqlite3; source=sqlite3.connect('/data/delivery.db'); target=sqlite3.connect('/data/backup.db'); source.backup(target); target.close(); source.close()"
docker compose cp api:/data/backup.db ./artifacts/backup.db
```

Crear primero `artifacts/` si no existe. Para restaurar, detener la API, colocar la copia con el propietario UID 10001 en el volumen y eliminar archivos WAL/SHM antiguos antes de iniciar. Validar esa restauración en un volumen separado antes de reemplazar datos de uso real. La automatización de backups externos queda fuera del alcance.

## Terraform

`infra/` despliega únicamente la API en un contenedor distinto, con volumen propio y puerto 18096. Compose despliega el stack de observabilidad. No administrar el mismo contenedor con ambas herramientas.

```powershell
cd infra
terraform init -lockfile=readonly
# Docker Desktop en Windows:
$env:DOCKER_HOST = docker context inspect desktop-linux --format '{{.Endpoints.docker.Host}}'
$env:TF_VAR_image = 'ghcr.io/jorgefprietol/delivery-operations-platform@sha256:<digest-verificado>'
$env:TF_VAR_operator_token = '<token independiente de 32+ caracteres>'
$env:TF_VAR_approver_token = '<token independiente de 32+ caracteres>'
terraform plan -out=delivery.tfplan
terraform apply delivery.tfplan
```

El estado de Terraform contiene secretos aunque se marquen como `sensitive`. Estado, planes y `.tfvars` se excluyen de Git; protegerlos y usar un backend cifrado y controlado cuando se trabaje en equipo. El directorio contiene un lock de proveedor para Linux y Windows. El contenedor usa un digest fijo; cualquier promoción se revisa en `terraform plan`.

Las verificaciones automatizadas ejecutan `fmt`, `init` y `validate`; la prueba de despliegue local se documenta en [verificación](verification.md).
