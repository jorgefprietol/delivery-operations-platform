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
- Rechazo de ejecuciones fallidas, incompletas, de otro repositorio o commit; rechazo de firmas, identidades y digests incorrectos. Una aprobación demo no habilita una entrega en modo verificado.

Las métricas de los escenarios de verificación usan datos sintéticos. El porcentaje de cobertura y el número de pruebas se obtienen de los reportes, no se fijan como resultados antes de ejecutarlos. Las verificaciones externas y el despliegue Terraform deben registrarse con su ejecución concreta.

## Verificación local — 2 de octubre de 2026

Python 3.12.15 en Windows: **55 pruebas aprobadas y 95,70% de cobertura de aplicación**, lint y formato sin errores. Auditoría de dependencias sin vulnerabilidades conocidas; escaneo de secretos sin hallazgos; actionlint sin errores; promtool confirma tres reglas válidas. Los reportes generados permanecen fuera del repositorio y se reproducen mediante los comandos documentados.

La aprobación en modo verificado se comprobó contra [Actions run 37051819952](https://github.com/jorgefprietol/delivery-operations-platform/actions/runs/37051819952), commit `3069ac8a2b68c7446c064b368dc77781507a8cc2` e imagen `sha256:79d0a62c204fac8981af1d77994ef94ac77daffd697b65bf6a783bba282cd282`. La API consultó el resultado real y Sigstore verificó firma, identidad, commit, intento y digest antes de guardar el recibo de aprobación. El bundle público auténtico en `tests/fixtures/provenance.json` permite repetir las pruebas criptográficas sin red.

El workflow [Verify published release evidence](https://github.com/jorgefprietol/delivery-operations-platform/actions/workflows/verify-evidence.yml) repite esta comprobación después de cada publicación exitosa y conserva `verified-evidence.json` como artifact. La captura del panel muestra datos sintéticos identificados explícitamente:

![Dashboard con escenario sintético](images/dashboard.png)
