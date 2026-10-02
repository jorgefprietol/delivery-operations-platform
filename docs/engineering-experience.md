# Experiencia de ingeniería

**Proyecto independiente — Delivery Operations Platform**

Autor: Jorge Prieto

Diseñé e implementé una plataforma de operaciones de entrega con una API transaccional, separación de roles, aprobación de promociones, control de concurrencia y recuperación de releases. Construí un pipeline de GitHub Actions con pruebas en Linux y Windows, validación de infraestructura, escaneo de seguridad, verificación de contenedores y publicación del artefacto probado en GHCR con procedencia OIDC.

Automaticé la infraestructura local con Docker Compose y Terraform e integré Prometheus y Grafana para observar el servicio y analizar frecuencia de entregas, fallos, lead time y recuperación desde registros persistentes.

## Responsabilidades demostrables

- Modelado de estados de entrega y persistencia transaccional con SQLite WAL.
- Diseño de contratos HTTP, validación estricta y autorización por rol.
- Construcción de imágenes multietapa con usuario sin privilegios y dependencias verificadas por hash.
- Ingeniería de CI y entrega de artefactos inmutables, SBOM y atestaciones de procedencia.
- Infraestructura como código, monitoreo provisionado y documentación de operación y recuperación.
- Pruebas de restricciones de acceso, concurrencia real, persistencia después de reinicio y recuperación.

## Versión para perfil profesional

> Desarrollé una plataforma de operaciones de entrega con Python y FastAPI, contenerizada con Docker y respaldada por infraestructura Terraform. Implementé CI y entrega de imágenes verificadas con GitHub Actions y GHCR, junto con controles de aprobación, recuperación y observabilidad mediante Prometheus y Grafana.

Repositorio y ejecuciones del pipeline respaldan estas capacidades. Los escenarios E2E son sintéticos; no se atribuyen resultados de negocio, antigüedad, clientes o experiencia laboral que no estén documentados.
