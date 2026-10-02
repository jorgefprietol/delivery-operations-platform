# Evidencia de verificación

El workflow [CI and Delivery](https://github.com/jorgefprietol/delivery-operations-platform/actions/workflows/ci.yml) conserva reportes JUnit, cobertura, resultado E2E, verificación de monitoreo, logs Compose, análisis de imagen y SBOM en artifacts por catorce días.

## Criterios de aceptación

- Formato y lint sin errores, pruebas con al menos 85% de cobertura de aplicación.
- Pruebas de aislamiento de roles, transiciones ilegales, digest duplicado y dos aprobaciones concurrentes con un solo ganador.
- Entrega y fallo seguidos de recuperación real de registros, con auditoría y métricas coherentes.
- Dos entornos independientes y persistencia de registros después de reiniciar el contenedor.
- API ejecutada sin root, salud y volumen funcional con filesystem de solo lectura.
- Prometheus scrapea la API y recibe métricas de negocio; Grafana provisiona seis paneles y su datasource; tres reglas de alerta válidas.
- Terraform con formato, proveedor bloqueado y esquema válido; Actions validado con actionlint.
- Publicación de la misma imagen que pasó integración, con procedencia verificable por OIDC.

Las métricas de los escenarios de verificación usan datos sintéticos. El porcentaje de cobertura y el número de pruebas se obtienen de los reportes, no se fijan como resultados antes de ejecutarlos. Las verificaciones externas y el despliegue Terraform deben registrarse con su ejecución concreta.
