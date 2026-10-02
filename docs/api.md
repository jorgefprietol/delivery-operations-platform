# Contrato de operación

`/openapi.json` contiene el esquema completo. Endpoints de negocio requieren `Authorization: Bearer <token>`.

| Método | Ruta | Acceso / resultado |
| --- | --- | --- |
| GET | `/api/v1/releases?limit=50` | Ambos roles; máximo 200 registros |
| POST | `/api/v1/releases` | Operador; 201, candidate |
| GET | `/api/v1/releases/{id}` | Ambos roles |
| GET | `/api/v1/releases/{id}/events` | Ambos roles; eventos ordenados |
| POST | `/api/v1/releases/{id}/approve` | Aprobador; candidate → approved |
| POST | `/api/v1/releases/{id}/deploy` | Operador; approved → deployed |
| POST | `/api/v1/releases/{id}/fail` | Operador; release activo → failed |
| POST | `/api/v1/releases/{id}/rollback` | Operador; failed → rolled_back |
| GET | `/api/v1/summary?days=30` | Ambos roles; ventana de 1 a 90 días |

Errores: 401 sin credencial válida, 403 rol incorrecto, 404 release inexistente, 409 transición ilegal/digest duplicado/versión obsoleta, 422 contrato inválido. Los registros aceptan únicamente SHA completo y digest SHA-256, timestamp con zona horaria no futuro, URL HTTPS de GitHub Actions y los tres gates declarados como verdaderos.

Ejemplo PowerShell, usando una imagen y evidencia verificadas previamente:

```powershell
$settings = @{}
Get-Content .env | ForEach-Object {
  if ($_ -match '^([^=]+)=(.*)$') { $settings[$matches[1]] = $matches[2] }
}
$operator = @{ Authorization = "Bearer $($settings.OPERATOR_TOKEN)" }
$approver = @{ Authorization = "Bearer $($settings.APPROVER_TOKEN)" }
$payload = @{
  environment = 'staging'
  commit_sha = '<SHA de 40 caracteres>'
  image_digest = 'sha256:<digest de 64 caracteres>'
  committed_at = '<timestamp ISO8601 del commit con zona horaria>'
  evidence_url = 'https://github.com/jorgefprietol/delivery-operations-platform/actions/runs/<run-id>'
  quality_passed = $true
  security_passed = $true
  integration_passed = $true
} | ConvertTo-Json
$release = Invoke-RestMethod http://127.0.0.1:18095/api/v1/releases -Method Post -Headers $operator -ContentType application/json -Body $payload
$base = "http://127.0.0.1:18095/api/v1/releases/$($release.id)"
$body = @{ expected_version = $release.version } | ConvertTo-Json
$release = Invoke-RestMethod "$base/approve" -Method Post -Headers $approver -ContentType application/json -Body $body
# Ejecutar el despliegue real y comprobar readiness antes de confirmar su resultado.
$body = @{ expected_version = $release.version } | ConvertTo-Json
$release = Invoke-RestMethod "$base/deploy" -Method Post -Headers $operator -ContentType application/json -Body $body
```

La versión aumenta también cuando otro release modifica el estado de su predecesor. Consultar nuevamente el registro antes de cada decisión. Un 409 exige recargar y evaluar el estado; no se debe reintentar una transición a ciegas.
