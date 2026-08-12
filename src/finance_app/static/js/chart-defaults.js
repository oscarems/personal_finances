/**
 * Global Chart.js v4 defaults — Daytime Fintech theme
 * Loaded once after chart.js CDN; affects every chart in the app.
 */
(function () {
  if (typeof Chart === 'undefined') return;

  // Matches --chart-color-* tokens in design-system.css
  const PALETTE = [
    '#2563EB', // primary blue
    '#059669', // success green
    '#DC2626', // danger red
    '#D97706', // warning amber
    '#7C3AED', // violet
    '#0891B2', // cyan
    '#64748B', // slate
    '#DB2777', // pink
  ];

  Chart.defaults.font.family  = "'Plus Jakarta Sans', system-ui, sans-serif";
  Chart.defaults.font.size    = 12;
  Chart.defaults.color        = '#475569';
  Chart.defaults.borderColor  = 'rgba(15, 23, 42, 0.06)';
  Chart.defaults.layout.padding = 4;

  Chart.defaults.animation.duration = 550;
  Chart.defaults.animation.easing   = 'easeOutQuart';

  Chart.defaults.plugins.legend.labels.usePointStyle    = true;
  Chart.defaults.plugins.legend.labels.pointStyle       = 'circle';
  Chart.defaults.plugins.legend.labels.padding          = 16;
  Chart.defaults.plugins.legend.labels.color            = '#475569';
  Chart.defaults.plugins.legend.labels.font             = { size: 11.5, weight: '600' };
  Chart.defaults.plugins.legend.labels.boxWidth         = 8;
  Chart.defaults.plugins.legend.labels.boxHeight        = 8;

  Chart.defaults.plugins.tooltip.backgroundColor = '#0F172A';
  Chart.defaults.plugins.tooltip.titleColor      = '#F8FAFC';
  Chart.defaults.plugins.tooltip.bodyColor       = '#E2E8F0';
  Chart.defaults.plugins.tooltip.borderColor     = 'rgba(15, 23, 42, 0.20)';
  Chart.defaults.plugins.tooltip.borderWidth     = 1;
  Chart.defaults.plugins.tooltip.padding         = 10;
  Chart.defaults.plugins.tooltip.cornerRadius    = 8;
  Chart.defaults.plugins.tooltip.titleFont       = { size: 12, weight: '700', family: '"Plus Jakarta Sans", system-ui, sans-serif' };
  Chart.defaults.plugins.tooltip.bodyFont        = { size: 12, family: '"Plus Jakarta Sans", system-ui, sans-serif' };
  Chart.defaults.plugins.tooltip.caretSize       = 5;
  Chart.defaults.plugins.tooltip.boxPadding      = 5;
  Chart.defaults.plugins.tooltip.usePointStyle   = true;
  Chart.defaults.plugins.tooltip.mode            = 'index';
  Chart.defaults.plugins.tooltip.intersect       = false;

  const scaleStyle = {
    grid: {
      color:      'rgba(15, 23, 42, 0.06)',
      lineWidth:  1,
      drawBorder: false,
    },
    border: {
      display: false,
    },
    ticks: {
      color:   '#94A3B8',
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

  try {
    const bar = Chart.overrides.bar;
    bar.borderRadius ??= 4;
    bar.borderSkipped ??= false;
    if (!bar.datasets) bar.datasets = {};
    bar.datasets.borderRadius ??= 4;
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
