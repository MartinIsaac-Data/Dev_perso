// Broli S&OP Portal — the only custom JavaScript: Chart.js rendering, file download, print, fullscreen.
window.sop = (() => {
  const charts = {};
  const css = () => getComputedStyle(document.documentElement);
  const color = (v) => (v && v.startsWith("--")) ? css().getPropertyValue(v).trim() : v;
  const compact = (n) => {
    if (n === null || n === undefined || !isFinite(n)) return "—";
    const a = Math.abs(n);
    if (a >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
    if (a >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (a >= 1e4) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "k";
    return a >= 100 ? Math.round(n).toLocaleString("fr-FR") : (Math.round(n * 10) / 10).toLocaleString("fr-FR");
  };

  function renderChart(id, cfg, dotnet) {
    const canvas = document.getElementById(id);
    if (!canvas || !window.Chart) return;
    if (charts[id]) { charts[id].destroy(); delete charts[id]; }

    const muted = color("--text-muted"), grid = color("--grid"), ink = color("--text-secondary"), surface = color("--surface");
    const unit = cfg.unit ? " " + cfg.unit : "";
    const horizontal = !!cfg.horizontal;
    const datasets = cfg.datasets.map((d) => {
      const c = color(d.color);
      const type = d.type || cfg.type;
      const base = { label: d.label, data: d.data, type };
      if (type === "line") {
        return Object.assign(base, {
          borderColor: c, backgroundColor: c, borderWidth: 2, tension: 0.25, spanGaps: true,
          pointRadius: 3, pointHoverRadius: 6, pointBackgroundColor: c, pointBorderColor: surface, pointBorderWidth: 2,
          borderDash: d.dashed ? [6, 4] : [], order: 0,
        });
      }
      const colors = d.pointColors ? d.pointColors.map(color) : c;
      return Object.assign(base, {
        backgroundColor: colors, borderColor: surface, borderWidth: { top: 0, right: 0, bottom: 0, left: 0 },
        borderRadius: 4, borderSkipped: "start", maxBarThickness: 34, categoryPercentage: 0.72, barPercentage: 0.9, order: 1,
      });
    });

    const valueAxis = {
      beginAtZero: true, stacked: !!cfg.stacked, grid: { color: grid, drawTicks: false }, border: { display: false },
      ticks: { color: muted, padding: 6, callback: (v) => compact(v) + (cfg.unit === "%" ? "%" : "") },
      suggestedMax: cfg.suggestedMax ?? undefined, max: cfg.max ?? undefined, min: cfg.min ?? undefined,
    };
    const categoryAxis = {
      stacked: !!cfg.stacked, grid: { display: false }, border: { color: color("--axis") },
      ticks: { color: ink, autoSkip: true, maxRotation: 0, font: { size: 11 },
        callback: function (v) { const l = this.getLabelForValue(v); return l && l.length > 28 ? l.slice(0, 27) + "…" : l; } },
    };

    const chart = new Chart(canvas, {
      type: cfg.type,
      data: { labels: cfg.labels, datasets },
      options: {
        indexAxis: horizontal ? "y" : "x",
        responsive: true, maintainAspectRatio: false, animation: { duration: 250 },
        interaction: { mode: cfg.type === "line" || cfg.datasets.length > 1 ? "index" : "nearest", intersect: false, axis: horizontal ? "y" : "x" },
        layout: { padding: { top: 4, right: 8 } },
        scales: horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis },
        plugins: {
          legend: { display: cfg.datasets.length > 1, position: "top", align: "end",
            labels: { color: ink, usePointStyle: true, pointStyle: "rectRounded", boxWidth: 10, boxHeight: 10, font: { size: 12 } } },
          tooltip: {
            backgroundColor: color("--tooltip-bg"), titleColor: color("--tooltip-ink"), bodyColor: color("--tooltip-ink"),
            padding: 10, cornerRadius: 6, boxPadding: 4, usePointStyle: true,
            callbacks: { label: (ctx) => {
              const v = horizontal ? ctx.parsed.x : ctx.parsed.y;
              const shown = (v === null || v === undefined || !isFinite(v)) ? "—" : (Math.abs(v) < 100 ? (Math.round(v * 10) / 10).toLocaleString("fr-FR") : Math.round(v).toLocaleString("fr-FR"));
              return ` ${ctx.dataset.label}: ${shown}${unit}`;
            } },
          },
        },
        onHover: (evt, els) => { evt.native.target.style.cursor = cfg.clickable && els.length ? "pointer" : "default"; },
        onClick: (evt, els) => {
          if (!cfg.clickable || !dotnet) return;
          const hit = els.length ? els : chart.getElementsAtEventForMode(evt, "nearest", { intersect: false, axis: horizontal ? "y" : "x" }, true);
          if (hit.length) dotnet.invokeMethodAsync("OnChartClick", hit[0].datasetIndex, hit[0].index);
        },
      },
    });
    charts[id] = chart;
  }

  function destroyChart(id) { if (charts[id]) { charts[id].destroy(); delete charts[id]; } }

  async function download(fileName, contentType, streamRef) {
    const buffer = await streamRef.arrayBuffer();
    const url = URL.createObjectURL(new Blob([buffer], { type: contentType }));
    const a = document.createElement("a");
    a.href = url; a.download = fileName ?? "export"; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen?.();
  }

  function setTheme(theme) {
    if (theme) document.documentElement.setAttribute("data-theme", theme); else document.documentElement.removeAttribute("data-theme");
    Object.keys(charts).forEach((id) => charts[id].update());
  }

  function focus(id) { document.getElementById(id)?.focus(); }

  return { renderChart, destroyChart, download, print: () => window.print(), toggleFullscreen, setTheme, focus };
})();
