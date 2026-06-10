/**
 * Global Chart.js v4 defaults — modern dark-theme style.
 * Loaded once after chart.js CDN; affects every chart in the app.
 */
(function () {
  if (typeof Chart === 'undefined') return;

  const PALETTE = [
    '#3B82F6','#10B981','#F59E0B','#8B5CF6','#EF4444',
    '#06B6D4','#F97316','#A855F7','#14B8A6','#EC4899',
    '#84CC16','#6366F1',
  ];

  // ── Global font & color ────────────────────────────────────────────────────
  Chart.defaults.font.family  = '"Inter", system-ui, sans-serif';
  Chart.defaults.font.size    = 12;
  Chart.defaults.color        = 'rgba(148,163,184,0.85)';
  Chart.defaults.layout.padding = 4;

  // ── Animation ──────────────────────────────────────────────────────────────
  Chart.defaults.animation.duration = 550;
  Chart.defaults.animation.easing   = 'easeOutQuart';

  // ── Legend ─────────────────────────────────────────────────────────────────
  Chart.defaults.plugins.legend.labels.usePointStyle    = true;
  Chart.defaults.plugins.legend.labels.pointStyle       = 'circle';
  Chart.defaults.plugins.legend.labels.padding          = 16;
  Chart.defaults.plugins.legend.labels.color            = 'rgba(148,163,184,0.85)';
  Chart.defaults.plugins.legend.labels.font             = { size: 11.5, weight: '500' };
  Chart.defaults.plugins.legend.labels.boxWidth         = 8;
  Chart.defaults.plugins.legend.labels.boxHeight        = 8;

  // ── Tooltip ────────────────────────────────────────────────────────────────
  Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15,23,42,0.93)';
  Chart.defaults.plugins.tooltip.titleColor      = '#f1f5f9';
  Chart.defaults.plugins.tooltip.bodyColor       = 'rgba(148,163,184,0.9)';
  Chart.defaults.plugins.tooltip.borderColor     = 'rgba(255,255,255,0.08)';
  Chart.defaults.plugins.tooltip.borderWidth     = 1;
  Chart.defaults.plugins.tooltip.padding         = { x: 14, y: 10 };
  Chart.defaults.plugins.tooltip.cornerRadius    = 10;
  Chart.defaults.plugins.tooltip.titleFont       = { size: 12, weight: '600', family: '"Inter", system-ui, sans-serif' };
  Chart.defaults.plugins.tooltip.bodyFont        = { size: 12, family: '"Inter", system-ui, sans-serif' };
  Chart.defaults.plugins.tooltip.caretSize       = 5;
  Chart.defaults.plugins.tooltip.boxPadding      = 5;
  Chart.defaults.plugins.tooltip.usePointStyle   = true;
  Chart.defaults.plugins.tooltip.mode            = 'index';
  Chart.defaults.plugins.tooltip.intersect       = false;

  // ── Scale grid & ticks (Chart.js v4: use overrides per scale type) ─────────
  const scaleStyle = {
    grid: {
      color:       'rgba(148,163,184,0.08)',
      lineWidth:   1,
    },
    border: {
      display: false,
    },
    ticks: {
      color:   'rgba(148,163,184,0.7)',
      padding: 8,
      font:    { size: 11 },
    },
  };

  // Apply to every cartesian scale type in v4
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
  // Bar
  try {
    const bar = Chart.overrides.bar;
    bar.borderRadius ??= 6;
    bar.borderSkipped ??= false;
    if (!bar.datasets) bar.datasets = {};
    bar.datasets.borderRadius ??= 6;
  } catch (_) {}

  // Line
  try {
    const line = Chart.overrides.line;
    line.tension ??= 0.4;
    line.pointRadius ??= 0;
    line.pointHoverRadius ??= 5;
    line.borderWidth ??= 2.5;
  } catch (_) {}

  // Doughnut
  try {
    const doughnut = Chart.overrides.doughnut;
    doughnut.cutout ??= '68%';
    doughnut.hoverOffset ??= 6;
  } catch (_) {}

  // Pie
  try {
    Chart.overrides.pie.hoverOffset ??= 6;
  } catch (_) {}

  // ── Named exports ──────────────────────────────────────────────────────────
  window.CHART_PALETTE = PALETTE;
})();
