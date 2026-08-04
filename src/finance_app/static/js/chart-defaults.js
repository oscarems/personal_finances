/**
 * Global Chart.js v4 defaults -- Terra theme (green-white surface, forest accents).
 * Loaded once after chart.js CDN; affects every chart in the app.
 */
(function () {
  if (typeof Chart === 'undefined') return;

  // Design-system Terra palette (matches --chart-color-* tokens)
  const PALETTE = [
    '#316342', // forest green   (--chart-color-1)
    '#BA1A1A', // error red      (--chart-color-2)
    '#735142', // umber          (--chart-color-3)
    '#3B6D7A', // teal           (--chart-color-4)
    '#8E6959', // clay           (--chart-color-5)
    '#57615A', // sage gray      (--chart-color-6)
    '#9DD3AA', // mint           (--chart-color-7)
    '#C9A98F', // sand           (--chart-color-8)
  ];

  // -- Global font & color -----------------------------------------------------
  Chart.defaults.font.family  = "'Nunito Sans', system-ui, sans-serif";
  Chart.defaults.font.size    = 12;
  Chart.defaults.color        = '#414942';   // --fin-ink-2 (readable on light surface)
  Chart.defaults.borderColor  = 'rgba(22, 29, 25, 0.08)';
  Chart.defaults.layout.padding = 4;

  // -- Animation ----------------------------------------------------------------
  Chart.defaults.animation.duration = 550;
  Chart.defaults.animation.easing   = 'easeOutQuart';

  // -- Legend ---------------------------------------------------------------------
  Chart.defaults.plugins.legend.labels.usePointStyle    = true;
  Chart.defaults.plugins.legend.labels.pointStyle       = 'circle';
  Chart.defaults.plugins.legend.labels.padding          = 16;
  Chart.defaults.plugins.legend.labels.color            = '#414942';  // --fin-ink-2
  Chart.defaults.plugins.legend.labels.font             = { size: 11.5, weight: '600' };
  Chart.defaults.plugins.legend.labels.boxWidth         = 8;
  Chart.defaults.plugins.legend.labels.boxHeight        = 8;

  // -- Tooltip ----------------------------------------------------------------
  Chart.defaults.plugins.tooltip.backgroundColor = '#161D19';
  Chart.defaults.plugins.tooltip.titleColor      = '#F4FBF3';
  Chart.defaults.plugins.tooltip.bodyColor       = '#DDE4DD';
  Chart.defaults.plugins.tooltip.borderColor     = 'rgba(22, 29, 25, 0.20)';
  Chart.defaults.plugins.tooltip.borderWidth     = 1;
  Chart.defaults.plugins.tooltip.padding         = 10;
  Chart.defaults.plugins.tooltip.cornerRadius    = 8;
  Chart.defaults.plugins.tooltip.titleFont       = { size: 12, weight: '700', family: '"Nunito Sans", system-ui, sans-serif' };
  Chart.defaults.plugins.tooltip.bodyFont        = { size: 12, family: '"Nunito Sans", system-ui, sans-serif' };
  Chart.defaults.plugins.tooltip.caretSize       = 5;
  Chart.defaults.plugins.tooltip.boxPadding      = 5;
  Chart.defaults.plugins.tooltip.usePointStyle   = true;
  Chart.defaults.plugins.tooltip.mode            = 'index';
  Chart.defaults.plugins.tooltip.intersect       = false;

  // -- Scale grid & ticks (light theme) ----------------------------------------
  const scaleStyle = {
    grid: {
      color:      'rgba(22, 29, 25, 0.08)',  // --chart-grid
      lineWidth:  1,
      drawBorder: false,
    },
    border: {
      display: false,
    },
    ticks: {
      color:   '#717971',   // --fin-ink-3
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

  // -- Chart type overrides (v4 API) -------------------------------------------
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
