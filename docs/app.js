// Supabase configuration
const SUPABASE_URL = 'https://otbaaunfywxixuzsdwrv.supabase.co';
const SUPABASE_KEY = 'sb_publishable_EkZm5FPjxuhQDnupZ9qtLw_65QZWHXh';

// Pass/fail thresholds for a run
const THRESHOLDS = { expectancy: 0, profitFactor: 1.5, maxDrawdown: -15 };

function passes(m) {
  return m.expectancy_pct > THRESHOLDS.expectancy
    && m.profit_factor > THRESHOLDS.profitFactor
    && m.max_drawdown_pct > THRESHOLDS.maxDrawdown;
}

function fmtDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { year: '2-digit', month: 'short', day: '2-digit' })
    + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function renderConfig(cfg) {
  const strip = document.getElementById('configStrip');
  const fields = [
    ['Symbol', cfg.symbol],
    ['MA fast', cfg.ma_fast],
    ['MA slow', cfg.ma_slow],
    ['RSI buy <', cfg.rsi_buy_below],
    ['Stop loss', (cfg.stop_loss_pct * 100).toFixed(1) + '%'],
    ['Take profit', (cfg.take_profit_pct * 100).toFixed(1) + '%'],
  ];
  strip.innerHTML = fields.map(([k, v]) =>
    `<div class="config-cell"><div class="k">${k}</div><div class="v">${v}</div></div>`
  ).join('');
  document.getElementById('configSection').style.display = '';
  document.getElementById('tickerLabel').textContent = cfg.symbol || '—';
}

function renderChart(runs) {
  const svg = document.getElementById('chart');
  const w = 900, h = 160, pad = 12;
  const vals = runs.map(r => r.metrics.expectancy_pct).reverse();

  if (vals.length < 2) {
    document.getElementById('chartSection').style.display = 'none';
    return;
  }
  document.getElementById('chartSection').style.display = '';

  const min = Math.min(...vals, 0), max = Math.max(...vals, 0);
  const range = (max - min) || 1;
  const xStep = (w - pad * 2) / (vals.length - 1);
  const y = v => h - pad - ((v - min) / range) * (h - pad * 2);
  const zeroY = y(0);

  const points = vals.map((v, i) => `${pad + i * xStep},${y(v)}`).join(' ');

  svg.innerHTML = `
    <line x1="${pad}" y1="${zeroY}" x2="${w - pad}" y2="${zeroY}"
      stroke="#2A323C" stroke-width="1" stroke-dasharray="2,3" />
    <polyline points="${points}" fill="none" stroke="#C9A227" stroke-width="1.5" />
    ${vals.map((v, i) => `<circle cx="${pad + i * xStep}" cy="${y(v)}" r="2.5"
      fill="${v >= 0 ? '#5FA35A' : '#B3503F'}" />`).join('')}
  `;
}

function renderTable(runs) {
  const rows = runs.map(r => {
    const m = r.metrics;
    const ok = passes(m);
    const expClass = m.expectancy_pct >= 0 ? 'gain' : 'loss';
    const ddClass = m.max_drawdown_pct >= -10 ? 'gain' : 'loss';
    return `
      <tr>
        <td><span class="seal ${ok ? 'pass' : 'fail'}"></span></td>
        <td>${fmtDate(r.created_at)}</td>
        <td class="num">${m.num_trades}</td>
        <td class="num">${m.win_rate.toFixed(1)}%</td>
        <td class="num ${expClass}">${m.expectancy_pct.toFixed(2)}%</td>
        <td class="num">${m.profit_factor.toFixed(2)}</td>
        <td class="num ${ddClass}">${m.max_drawdown_pct.toFixed(2)}%</td>
      </tr>`;
  }).join('');
  document.getElementById('runRows').innerHTML = rows;
  document.getElementById('tableSection').style.display = '';
  document.getElementById('countLabel').textContent =
    `${runs.length} run${runs.length === 1 ? '' : 's'} logged`;
}

async function load() {
  ['configSection', 'chartSection', 'tableSection', 'emptySection', 'errorSection']
    .forEach(id => document.getElementById(id).style.display = 'none');

  try {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/runs?select=*&order=created_at.desc&limit=200`,
      { headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` } }
    );
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const runs = await res.json();

    if (!runs.length) {
      document.getElementById('emptySection').style.display = '';
      return;
    }

    renderConfig(runs[0].config);
    renderChart(runs);
    renderTable(runs);
  } catch (err) {
    document.getElementById('errorDetail').textContent = err.message;
    document.getElementById('errorSection').style.display = '';
  }
}

// Initial load on page ready
load();
