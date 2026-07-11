/**
 * Global Chart.js v4 defaults — Daylight theme (light background, indigo accent).
 * Loaded once after chart.js CDN; affects every chart in the app.
 */
(function () {
  if (typeof Chart === 'undefined') return;

  // Design-system Daylight palette (matches --chart-color-* tokens)
  const PALETTE = [
    '#6366F1', // indigo   (--chart-color-1)
    '#10B981', // emerald  (--chart-color-2)
    '#F59E0B', // amber    (--chart-color-3)
    '#EF4444', // red      (--chart-color-4)
    '#8B5CF6', // violet   (--chart-color-5)
    '#06B6D4', // cyan     (--chart-color-6)
    '#F97316', // orange   (--chart-color-7)
    '#EC4899', // pink     (--chart-color-8)
  ];

  // ── Global font & color ────────────────────────────────────────────────────
  Chart.defaults.font.family  = "'Inter', system-ui, sans-serif";
  Chart.defaults.font.size    = 12;
  Chart.defaults.color        = '#64748B';   // --fin-ink-2 (readable on light bg)
  Chart.defaults.borderColor  = 'rgba(15, 23, 42, 0.07)';
  Chart.defaults.layout.padding = 4;

  // ── Animation ──────────────────────────────────────────────────────────────
  Chart.defaults.animation.duration = 550;
  Chart.defaults.animation.easing   = 'easeOutQuart';

  // ── Legend ─────────────────────────────────────────────────────────────────
  Chart.defaults.plugins.legend.labels.usePointStyle    = true;
  Chart.defaults.plugins.legend.labels.pointStyle       = 'circle';
  Chart.defaults.plugins.legend.labels.padding          = 16;
  Chart.defaults.plugins.legend.labels.color            = '#475569';  // --fin-ink-2
  Chart.defaults.plugins.legend.labels.font             = { size: 11.5, weight: '500' };
  Chart.defaults.plugins.legend.labels.boxWidth         = 8;
  Chart.defaults.plugins.legend.labels.boxHeight        = 8;

  // ── Tooltip ────────────────────────────────────────────────────────────────
  Chart.defaults.plugins.tooltip.backgroundColor = '#1E293B';
  Chart.defaults.plugins.tooltip.titleColor      = '#F1F5F9';
  Chart.defaults.plugins.tooltip.bodyColor       = '#94A3B8';
  Chart.defaults.plugins.tooltip.borderColor     = 'rgba(15, 23, 42, 0.15)';
  Chart.defaults.plugins.tooltip.borderWidth     = 1;
  Chart.defaults.plugins.tooltip.padding         = 10;
  Chart.defaults.plugins.tooltip.cornerRadius    = 10;
  Chart.defaults.plugins.tooltip.titleFont       = { size: 12, weight: '600', family: '"Inter", system-ui, sans-serif' };
  Chart.defaults.plugins.tooltip.bodyFont        = { size: 12, family: '"Inter", system-ui, sans-serif' };
  Chart.defaults.plugins.tooltip.caretSize       = 5;
  Chart.defaults.plugins.tooltip.boxPadding      = 5;
  Chart.defaults.plugins.tooltip.usePointStyle   = true;
  Chart.defaults.plugins.tooltip.mode            = 'index';
  Chart.defaults.plugins.tooltip.intersect       = false;

  // ── Scale grid & ticks (light theme) ──────────────────────────────────────
  const scaleStyle = {
    grid: {
      color:      'rgba(15, 23, 42, 0.06)',  // --chart-grid
      lineWidth:  1,
      drawBorder: false,
    },
    border: {
      display: false,
    },
    ticks: {
      color:   '#94A3B8',   // --fin-ink-3
      padding: 8,
      font:    { size: 11 },
    },
  };

  ['linear', 'logarithmic', 'time', 'timeseries', 'category'].forEach((type) => {
    try {
      const s = Chart.defaults.scales[type];
      if (!s) return;
      if (s.grid)   Object.assign(s.grid,   scaleStyle.grid);
      if (s.border) Object.assign(s.border, scaleStyle.border);
      if (s.ticks)  Object.assign(s.ticks,  scaleStyle.ticks);
    } catch (_) {}
  });

  // ── Chart type overrides (v4 API) ──────────────────────────────────────────
  try {
    const bar = Chart.overrides.bar;
    bar.borderRadius ??= 6;
    bar.borderSkipped ??= false;
    if (!bar.datasets) bar.datasets = {};
    bar.datasets.borderRadius ??= 6;
  } catch (_) {}

  try {
    const line = Chart.overrides.line;
    line.tension ??= 0.4;
    line.pointRadius ??= 0;
    line.pointHoverRadius ??= 5;
    line.borderWidth ??= 2.5;
  } catch (_) {}

  try {
    const doughnut = Chart.overrides.doughnut;
    doughnut.cutout ??= '68%';
    doughnut.hoverOffset ??= 6;
  } catch (_) {}

  try {
    Chart.overrides.pie.hoverOffset ??= 6;
  } catch (_) {}

  window.CHART_PALETTE = PALETTE;
})();
