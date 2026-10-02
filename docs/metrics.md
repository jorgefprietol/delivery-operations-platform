# Métricas y mejora continua

Las métricas de entrega se derivan de los registros y timestamps persistidos, únicamente para `production`. La ventana predeterminada es de 30 días y selecciona releases cuyo primer `deployed_at` está dentro de ella. No representan estadísticas de una empresa ni un benchmarking externo.

| Métrica | Cálculo / límite |
| --- | --- |
| Deployments | Releases entregados por primera vez en la ventana; restaurar uno no incrementa el conteo |
| Deployments per day | Conteo dividido entre los días completos de la ventana, aunque haya días sin actividad |
| Change failure rate | Releases con fallo registrado / releases entregados en la ventana |
| Mean lead time | Media de `deployed_at - committed_at` de esos releases |
| Mean recovery time | Media de `recovered_at - failed_at`, solo fallos recuperados de esos releases |
| Open incidents | Fallos aún sin recuperación entre los releases incluidos |

Si no hay muestra, las medias y la tasa de fallo son `null`; Prometheus omite esas series y el panel muestra `—`. El conteo cero es válido. Los incidentes abiertos anteriores a la ventana no se incluyen; consultar el historial y los entornos activos para la operación completa. Los timestamps son UTC y los commits no pueden tener fecha futura.

Estas medidas ofrecen una aproximación operativa inspirada en métricas de entrega. No implementan todas las definiciones ni el modelo actual completo de DORA: solo registran el primer fallo de cada release, usan medias y no descubren incidentes automáticamente. La calidad depende de que el integrador confirme las transiciones con evidencia real.

## Servicio

Los contadores y el histograma HTTP se agrupan por plantilla de ruta y estado, sin IDs de release, URLs arbitrarias o token como etiquetas. Salud y scraping se excluyen de la medición. Son métricas del proceso y reinician al reiniciar la API; Prometheus calcula sus tasas y retiene siete días.

Las reglas detectan scraping caído, más del 1% de errores 5xx sostenidos por cinco minutos y un incidente de entrega sin resolver por dos minutos. Son alertas evaluadas en Prometheus; no se configura envío a correo ni canales externos.

## Práctica de mejora

1. Identificar una fricción a partir del historial: cambios bloqueados, recuperación lenta o revisiones manuales repetidas.
2. Formular una hipótesis y un cambio acotado, con criterio de aceptación.
3. Ejecutar el pipeline y conservar evidencias de calidad y seguridad.
4. Revisar fallos y tiempos en una ventana comparable; separar muestras sintéticas de actividad real.
5. Documentar la decisión y la siguiente acción en una revisión operativa sin atribuir culpa.

El diseño facilita flujo mediante artefactos reproducibles, feedback mediante pruebas y telemetría, y experimentación mediante cambios pequeños y recuperación verificable. No asigna automáticamente un nivel de madurez a un equipo.
