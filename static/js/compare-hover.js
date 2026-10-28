/**
 * Chart.js hover mode "dateLines" for the two-line comparison charts
 * (Backtest "Strategy vs. holding" and the Dashboard's paper test panel).
 *
 * Picks the date under the cursor and returns every line dataset ($line)
 * at that point, so the tooltip always shows both lines. When the cursor is
 * on a Buy/Sell badge ($trade dataset), it uses that badge's date.
 * The lines must share their x values (one point per candle).
 */
(function () {
  if (!window.Chart) return;
  Chart.Interaction.modes.dateLines = (chart, e) => {
    const lines = chart.data.datasets.map((d, i) => [d, i]).filter(([d]) => d.$line && !d.hidden);
    if (!lines.length || !chart.chartArea) return [];
    let x = chart.scales.x.getValueForPixel(e.x);
    // On a badge (they sit up to ~26px from their point), use that trade's date
    chart.data.datasets.forEach((d, i) => {
      if (!d.$trade || d.hidden) return;
      chart.getDatasetMeta(i).data.forEach((el, j) => {
        if (Math.abs(el.x - e.x) <= 12 && Math.abs(el.y - e.y) <= 30) x = d.data[j].x;
      });
    });
    const data = lines[0][0].data;
    if (!data.length) return [];
    let lo = 0, hi = data.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (data[mid].x <= x) lo = mid; else hi = mid; }
    const idx = Math.abs(data[lo].x - x) <= Math.abs(data[hi].x - x) ? lo : hi;
    return lines
      .filter(([d]) => d.data[idx])
      .map(([, i]) => ({ element: chart.getDatasetMeta(i).data[idx], datasetIndex: i, index: idx }))
      .filter((it) => it.element);
  };
})();
