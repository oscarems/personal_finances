# Design System — Finanzas Personales (Daytime Fintech)

Sistema visual canónico de la SPA. Tokens en `static/styles/design-system.css`;
layout/shell en `static/css/layout.css`. Sin Tailwind ni frameworks.

## Dirección

Look **fintech de día**: fondos blanco / slate muy claro, acento azul sobrio,
verde solo para positivo, tipografía crisp. Densidad equilibrada.

## Tokens principales

| Rol | Valor |
|-----|--------|
| Fondo app (`--fin-bg`) | `#F8FAFC` |
| Superficie / cards | `#FFFFFF` |
| Superficie muted | `#F1F5F9` |
| Texto | `#0F172A` / `#475569` / `#94A3B8` |
| Primary / acento | `#2563EB` |
| Success | `#059669` |
| Danger | `#DC2626` |
| Warning | `#D97706` |
| Border | `rgba(15, 23, 42, 0.10)` |
| Radius card | `12px` |
| Font sans | Plus Jakarta Sans |
| Font mono (montos) | JetBrains Mono |

## Tipografía

- **Sans**: Plus Jakarta Sans (400/500/600/700)
- **Mono**: JetBrains Mono — siempre en montos (clase `.amount` / `.mono`)
- Escala: `--text-xs` … `--text-2xl`

## Componentes canónicos

| Clase | Uso |
|-------|-----|
| `.page-header` | Título + subtítulo + acciones |
| `.kpi-card` / `.kpi-grid` | Métricas arriba de página |
| `.card` / `.card-header` / `.card-body` | Contenedores de sección |
| `.fin-table` | Tablas de datos |
| `.btn` + `.btn-primary` / `.secondary` / `.ghost` / `.danger` | Acciones |
| `.empty-state` | Vacío |
| `.filter-panel` | Filtros de listados |
| `.badge-*` | Estados |
| `.list-row` | Filas tipo lista |

## Patrón de página

1. Page header (título + 1 línea de contexto + CTA)
2. KPI row (3–4 máx.), si aplica
3. Contenido principal (tabla o grid ≤ 2 columnas)
4. Estados: loading / error / empty vía `pageState` / `emptyState`

## Navegación (shell)

```
Dinero          → Dashboard, Cuentas, Transacciones, Ingresos
Planificar      → Presupuesto, Metas, Recurrentes
Analizar        → Reportes, Flujo de caja, Salud, Patrimonio
Deudas e inversiones → Deudas, Hipoteca, Simulador deudas, Portafolio, FIRE
Herramientas    → Fondo emergencia, Simulador inversión, Gmail, Reglas, Reconciliación, Config
```

## Charts

Paleta global en `chart-defaults.js` alineada a `--chart-color-*`.
Primary series: azul `#2563EB`; success `#059669`; danger `#DC2626`.

## Reglas

- No hardcodear verdes/azules en páginas; usar variables CSS.
- Evitar `style=""` para color/espacio cuando exista utilidad o clase canónica.
- Verde = positivo; rojo = negativo; azul = acción / nav activo.
- Sin dark mode en esta ola.
