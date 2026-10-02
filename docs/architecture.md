# Arquitectura y decisiones

## Problema y alcance

Un equipo necesita relacionar cada entrega con su commit, su artefacto y su evidencia; separar la aprobación de la ejecución y mantener un historial consultable de fallos y recuperación. La plataforma implementa ese registro y automatiza su propia entrega como contenedor.

La API es un control de registros. Un integrador debe ejecutar el despliegue real, comprobar su resultado y confirmar la transición. La autorización usa dos credenciales compartidas por rol; no equivale a identidad individual, SSO o atribución personal. Una evolución para múltiples equipos requiere identidad federada.

## Estado y concurrencia

```mermaid
stateDiagram-v2
    [*] --> candidate
    candidate --> approved: approver
    approved --> deployed: operator
    deployed --> superseded: nueva entrega
    deployed --> failed: fallo activo
    failed --> rolled_back: restauración de predecesor
    superseded --> deployed: restauración
```

Una entrega nueva puede recuperar un release fallido sin marcarlo como rollback: conserva el estado `failed` y registra `recovered_at`. Nunca utiliza una entrega fallida como predecesor saludable. No permite rollback de la primera entrega; requiere un reemplazo validado.

SQLite usa WAL y transacciones `BEGIN IMMEDIATE`: cada transición actualiza el release, el puntero activo y los eventos como una unidad. `expected_version` evita decisiones sobre versiones obsoletas. Una restricción única sobre entorno y digest impide registrar el mismo artefacto dos veces en el mismo entorno; staging y production están aislados.

Se utiliza un proceso Uvicorn y una base SQLite local para operación individual. El volumen requiere backup; no se proporciona replicación ni alta disponibilidad. Una implementación de varios nodos necesita almacenamiento compartido transaccional, por ejemplo PostgreSQL, y una estrategia de migraciones.

## Seguridad y operación

- Contenedor de aplicación sin privilegios, UID 10001, sistema de archivos de solo lectura, volumen de datos y capabilities eliminadas.
- Readiness comprueba acceso a la tabla de releases; liveness comprueba respuesta HTTP.
- Tokens distintos, mínimo 32 caracteres; comparación en tiempo constante. Se transmiten por bearer y se mantienen en memoria en el panel.
- Validación estricta de contrato, sentencias SQL parametrizadas, headers de seguridad y logs sin cuerpos ni tokens.
- Métricas y endpoints de salud quedan sin autenticación en la red interna/local; deben protegerse si se expone el servicio públicamente.
- La aprobación en modo `verified` verifica el repositorio configurado, SHA exacto, workflow CI de `main`, ejecución completa y exitosa y evento push/dispatch. Rechaza URLs de otros destinos antes de cualquier petición.
- Verifica bundles Sigstore DSSE: cadena del certificado, prueba de transparencia, identidad OIDC del workflow, commit fuente, ref, entorno GitHub hospedado e invocación con intento. El statement firmado debe tener predicado SLSA y el nombre/digest exactos de la imagen.
- El recibo se persiste junto con la aprobación en una transacción. La verificación externa sucede antes del bloqueo de escritura; la versión se comprueba nuevamente al confirmar.
- `EVIDENCE_MODE=demo` es una excepción explícita para E2E sintético, con `verified:false` en recibos y señal visible en panel. El valor predeterminado es `verified`; no hay fallback automático ante fallos de red o firma.
- Al volver a modo `verified`, un recibo demo o una aprobación histórica sin evidencia verificable no permiten confirmar una nueva entrega.
- El historial es append-only por la API, pero un administrador con acceso a SQLite puede modificarlo. No es almacenamiento inmutable ni un ledger firmado.

## Cadena de suministro

El pipeline utiliza Actions por SHA, imágenes por digest y locks Python con hashes. El job de publicación recibe el archivo de la imagen probada, sin recompilar. Solo ese job tiene permisos de escritura en packages y de atestación OIDC. El escaneo bloqueante cubre vulnerabilidades con corrección disponible en la imagen propia; Prometheus y Grafana deben actualizarse y evaluarse por separado en cada entorno.

El cliente de GitHub y el verificador de firmas son inyectables para pruebas. Las pruebas criptográficas usan un bundle público auténtico del proyecto y rechazan la alteración del payload y la reutilización para otro commit. El workflow posterior a publicación verifica además el flujo completo con GitHub real. La política requiere que la infraestructura de firma de GitHub y Sigstore sea confiable; no protege frente a un cambio malicioso autorizado del workflow de confianza.

Referencias: [procedencia verificable en GitHub](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations), [cardinalidad de métricas Prometheus](https://prometheus.io/docs/practices/instrumentation/), [proveedor Docker para Terraform](https://registry.terraform.io/providers/kreuzwerker/docker/4.6.0/docs).
