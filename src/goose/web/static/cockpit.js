/* ══════════════════════════════════════════════════════════
   Goose Cockpit — Interactive Flight Data Visualization
   Uses uPlot for high-performance time-series charting
   ══════════════════════════════════════════════════════════ */

const Cockpit = (() => {
  'use strict';

  // ── State ─────────────────────────────────────────────
  let charts = [];
  let tsData = null;
  let modeChanges = [];
  let events = [];
  let flightDuration = 0;
  let cursorTime = null;
  let isDragging = false;

  // ── Colors ────────────────────────────────────────────
  const C = {
    green:  '#6ECC72',
    amber:  '#EF9F27',
    red:    '#E24B4A',
    blue:   '#5B9BD5',
    purple: '#A77BCA',
    cyan:   '#5BC0BE',
    orange: '#E8854A',
    pink:   '#D46A9F',
    lime:   '#A3C44A',
    grid:   'rgba(255,255,255,0.04)',
    axis:   'rgba(255,255,255,0.15)',
    text:   'rgba(216,213,206,0.4)',
    cursor: 'rgba(110,204,114,0.3)',
  };

  // Mode colors for timeline bands
  const MODE_COLORS = {
    manual:     '#5B9BD5',
    stabilized: '#A77BCA',
    altitude:   '#5BC0BE',
    position:   '#6ECC72',
    mission:    '#EF9F27',
    hold:       '#E8854A',
    return:     '#D46A9F',
    land:       '#A3C44A',
    takeoff:    '#6ECC72',
    acro:       '#E24B4A',
    offboard:   '#5B9BD5',
    orbit:      '#5BC0BE',
    none:       'rgba(255,255,255,0.05)',
  };

  // ── uPlot defaults ────────────────────────────────────
  function baseOpts(title, width, seriesDefs) {
    return {
      width: width,
      height: 180,
      cursor: {
        sync: { key: 'goose-sync' },
        drag: { x: true, y: false, setScale: true },
        focus: { prox: 30 },
      },
      scales: {
        x: { time: false },
      },
      axes: [
        {
          stroke: C.axis,
          grid: { stroke: C.grid, width: 1 },
          ticks: { stroke: C.grid, width: 1 },
          font: '10px JetBrains Mono, monospace',
          values: (u, vals) => vals.map(v => {
            if (v >= 3600) return Math.floor(v/3600) + 'h' + String(Math.floor((v%3600)/60)).padStart(2,'0') + 'm';
            if (v >= 60) return Math.floor(v/60) + 'm' + String(Math.floor(v%60)).padStart(2,'0') + 's';
            return v.toFixed(0) + 's';
          }),
        },
        {
          stroke: C.axis,
          grid: { stroke: C.grid, width: 1 },
          ticks: { stroke: C.grid, width: 1 },
          font: '10px JetBrains Mono, monospace',
          size: 50,
        },
      ],
      legend: { show: true },
      series: [
        { label: 'Time' },
        ...seriesDefs,
      ],
    };
  }

  function seriesDef(label, color, opts = {}) {
    return {
      label,
      stroke: color,
      width: 1.5,
      fill: opts.fill || undefined,
      paths: opts.paths || undefined,
      points: { show: false },
      ...opts,
    };
  }

  // ── Chart builders ────────────────────────────────────

  function buildAltitudeChart(container, ts) {
    const d = ts.altitude;
    if (!d) return null;

    const data = [d.timestamps];
    const series = [];

    if (d.alt_rel) {
      data.push(d.alt_rel);
      series.push(seriesDef('Altitude (rel)', C.green, {
        fill: 'rgba(110,204,114,0.06)',
      }));
    }
    if (d.alt_msl) {
      data.push(d.alt_msl);
      series.push(seriesDef('Altitude (MSL)', C.blue, { width: 1 }));
    }

    if (series.length === 0) return null;

    const opts = baseOpts('Altitude', container.clientWidth - 12, series);
    opts.axes[1].label = 'Meters';
    return new uPlot(opts, data, container);
  }

  function buildBatteryChart(container, ts) {
    const d = ts.battery;
    if (!d) return null;

    const data = [d.timestamps];
    const series = [];

    if (d.voltage) {
      data.push(d.voltage);
      series.push(seriesDef('Voltage', C.amber));
    }
    if (d.current) {
      data.push(d.current);
      series.push(seriesDef('Current', C.red));
    }
    if (d.remaining_pct) {
      data.push(d.remaining_pct);
      series.push(seriesDef('Remaining %', C.green, { width: 1 }));
    }

    if (series.length === 0) return null;

    const opts = baseOpts('Battery', container.clientWidth - 12, series);
    return new uPlot(opts, data, container);
  }

  function buildMotorsChart(container, ts) {
    const d = ts.motors;
    if (!d) return null;

    const motorKeys = Object.keys(d).filter(k => k.startsWith('output_')).sort();
    if (motorKeys.length === 0) return null;

    const motorColors = [C.green, C.red, C.blue, C.amber, C.purple, C.cyan, C.orange, C.pink];
    const data = [d.timestamps];
    const series = [];

    motorKeys.forEach((key, i) => {
      data.push(d[key]);
      const idx = parseInt(key.replace('output_', ''));
      series.push(seriesDef(`Motor ${idx + 1}`, motorColors[i % motorColors.length], { width: 1.2 }));
    });

    const opts = baseOpts('Motors', container.clientWidth - 12, series);
    opts.height = 200;
    opts.axes[1].label = 'Output (0-1)';
    return new uPlot(opts, data, container);
  }

  function buildAttitudeChart(container, ts) {
    const d = ts.attitude;
    if (!d) return null;

    const sp = ts.attitude_setpoint;
    const data = [d.timestamps];
    const series = [];

    if (d.roll) {
      data.push(d.roll);
      series.push(seriesDef('Roll', C.red));
    }
    if (d.pitch) {
      data.push(d.pitch);
      series.push(seriesDef('Pitch', C.green));
    }
    if (d.yaw) {
      data.push(d.yaw);
      series.push(seriesDef('Yaw', C.blue));
    }

    // Add setpoints as dashed lines if available and same length
    if (sp && sp.roll && sp.timestamps.length === d.timestamps.length) {
      if (sp.roll) {
        data.push(sp.roll);
        series.push(seriesDef('Roll SP', C.red, {
          width: 1,
          dash: [4, 4],
        }));
      }
      if (sp.pitch) {
        data.push(sp.pitch);
        series.push(seriesDef('Pitch SP', C.green, {
          width: 1,
          dash: [4, 4],
        }));
      }
    }

    if (series.length === 0) return null;

    const opts = baseOpts('Attitude', container.clientWidth - 12, series);
    opts.axes[1].label = 'Degrees';
    return new uPlot(opts, data, container);
  }

  function buildVibrationChart(container, ts) {
    const d = ts.vibration;
    if (!d) return null;

    const data = [d.timestamps];
    const series = [];

    if (d.accel_x) {
      data.push(d.accel_x);
      series.push(seriesDef('X', C.red, { width: 1 }));
    }
    if (d.accel_y) {
      data.push(d.accel_y);
      series.push(seriesDef('Y', C.green, { width: 1 }));
    }
    if (d.accel_z) {
      data.push(d.accel_z);
      series.push(seriesDef('Z', C.blue, { width: 1 }));
    }

    if (series.length === 0) return null;

    const opts = baseOpts('Vibration', container.clientWidth - 12, series);
    opts.axes[1].label = 'm/s\u00B2';
    return new uPlot(opts, data, container);
  }

  function buildGPSChart(container, ts) {
    const d = ts.gps;
    if (!d) return null;

    const data = [d.timestamps];
    const series = [];

    if (d.satellites) {
      data.push(d.satellites);
      series.push(seriesDef('Satellites', C.green));
    }
    if (d.hdop) {
      data.push(d.hdop);
      series.push(seriesDef('HDOP', C.amber));
    }

    if (series.length === 0) return null;

    const opts = baseOpts('GPS Health', container.clientWidth - 12, series);
    return new uPlot(opts, data, container);
  }

  function buildVelocityChart(container, ts) {
    const d = ts.velocity;
    if (!d) return null;

    const data = [d.timestamps];
    const series = [];

    if (d.vx) {
      data.push(d.vx);
      series.push(seriesDef('Vx (North)', C.red, { width: 1 }));
    }
    if (d.vy) {
      data.push(d.vy);
      series.push(seriesDef('Vy (East)', C.green, { width: 1 }));
    }
    if (d.vz) {
      data.push(d.vz);
      series.push(seriesDef('Vz (Down)', C.blue, { width: 1 }));
    }

    if (series.length === 0) return null;

    const opts = baseOpts('Velocity', container.clientWidth - 12, series);
    opts.axes[1].label = 'm/s';
    return new uPlot(opts, data, container);
  }

  function buildRCChart(container, ts) {
    const d = ts.rc;
    if (!d || !d.rssi) return null;

    const data = [d.timestamps, d.rssi];
    const series = [seriesDef('RSSI', C.amber, {
      fill: 'rgba(239,159,39,0.06)',
    })];

    const opts = baseOpts('RC Signal', container.clientWidth - 12, series);
    return new uPlot(opts, data, container);
  }

  // ── Timeline ──────────────────────────────────────────

  function renderTimeline(container, mc, evts, duration) {
    if (!duration) return;

    // Mode bands
    const modesBar = container.querySelector('.timeline-modes-bar');
    if (modesBar && mc.length > 0) {
      modesBar.innerHTML = mc.map((m, i) => {
        const start = m.timestamp / duration * 100;
        const end = i < mc.length - 1 ? mc[i + 1].timestamp / duration * 100 : 100;
        const width = end - start;
        const color = MODE_COLORS[m.to_mode] || 'rgba(255,255,255,0.1)';
        const label = width > 5 ? m.to_mode : '';
        return `<div class="mode-band" style="left:${start}%;width:${width}%;background:${color}30;border-color:${color};">${label}</div>`;
      }).join('');
    }

    // Event markers
    const evtContainer = container.querySelector('.timeline-event-markers');
    if (evtContainer && evts.length > 0) {
      const sevColor = { critical: '#E24B4A', warning: '#EF9F27', info: '#A3C44A' };
      evtContainer.innerHTML = evts
        .filter(e => e.severity !== 'info')
        .slice(0, 50)  // limit markers
        .map(e => {
          const pct = (e.timestamp / duration) * 100;
          const col = sevColor[e.severity] || 'rgba(255,255,255,0.3)';
          return `<div class="timeline-evt-dot" style="left:${pct}%;background:${col};" title="${e.message || ''}"></div>`;
        }).join('');
    }

    // Slider interaction
    const sliderWrap = container.querySelector('.timeline-slider-wrap');
    const cursorEl = container.querySelector('.timeline-slider-cursor');

    function updateCursor(e) {
      const rect = sliderWrap.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      cursorEl.style.left = (pct * 100) + '%';
      cursorTime = pct * duration;

      const timeLabel = container.querySelector('.timeline-cursor-time');
      if (timeLabel) {
        timeLabel.textContent = formatTime(cursorTime);
      }

      // Sync all charts to this cursor position
      syncCursorToCharts(cursorTime);
    }

    if (sliderWrap) {
      sliderWrap.addEventListener('mousedown', e => {
        isDragging = true;
        updateCursor(e);
      });
      document.addEventListener('mousemove', e => {
        if (isDragging) updateCursor(e);
      });
      document.addEventListener('mouseup', () => {
        isDragging = false;
      });
      sliderWrap.addEventListener('click', updateCursor);
    }

    // Also make modes bar clickable
    if (modesBar) {
      modesBar.addEventListener('click', e => {
        const rect = modesBar.getBoundingClientRect();
        const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        cursorTime = pct * duration;
        if (cursorEl) cursorEl.style.left = (pct * 100) + '%';
        const timeLabel = container.querySelector('.timeline-cursor-time');
        if (timeLabel) timeLabel.textContent = formatTime(cursorTime);
        syncCursorToCharts(cursorTime);
      });
    }
  }

  function syncCursorToCharts(time) {
    charts.forEach(chart => {
      if (!chart || !chart.data || !chart.data[0]) return;
      // Find nearest index
      const ts = chart.data[0];
      let idx = 0;
      for (let i = 0; i < ts.length; i++) {
        if (ts[i] !== null && ts[i] >= time) { idx = i; break; }
        idx = i;
      }
      chart.setCursor({ left: chart.valToPos(ts[idx], 'x'), top: -1 });
    });

    // Update chart-value badges with current readings
    _updateChartValues(time);
  }

  function _nearestVal(arr, idx) {
    if (!arr || idx == null || arr[idx] == null) return null;
    return arr[idx];
  }

  function _fmtVal(v, unit, decimals = 1) {
    if (v == null) return '--';
    return v.toFixed(decimals) + (unit ? '\u202f' + unit : '');
  }

  function _updateChartValues(time) {
    // Helper to find nearest index in a timestamps array
    function nearestIdx(timestamps) {
      if (!timestamps) return 0;
      let idx = 0;
      for (let i = 0; i < timestamps.length; i++) {
        if (timestamps[i] >= time) { idx = i; break; }
        idx = i;
      }
      return idx;
    }

    const d = tsData;

    // Altitude
    if (d.altitude) {
      const i = nearestIdx(d.altitude.timestamps);
      const rel = _nearestVal(d.altitude.alt_rel, i);
      const msl = _nearestVal(d.altitude.alt_msl, i);
      const el = document.getElementById('cv-altitude');
      if (el) el.textContent = rel != null ? _fmtVal(rel, 'm') : (msl != null ? _fmtVal(msl, 'm MSL') : '');
    }

    // Battery
    if (d.battery) {
      const i = nearestIdx(d.battery.timestamps);
      const pct = _nearestVal(d.battery.remaining_pct, i);
      const v = _nearestVal(d.battery.voltage, i);
      const el = document.getElementById('cv-battery');
      if (el) {
        const parts = [];
        if (pct != null) parts.push(_fmtVal(pct, '%', 0));
        if (v != null) parts.push(_fmtVal(v, 'V'));
        el.textContent = parts.join('  ');
      }
    }

    // GPS
    if (d.gps) {
      const i = nearestIdx(d.gps.timestamps);
      const sats = _nearestVal(d.gps.satellites, i);
      const hdop = _nearestVal(d.gps.hdop, i);
      const el = document.getElementById('cv-gps');
      if (el) {
        const parts = [];
        if (sats != null) parts.push(sats.toFixed(0) + '\u202fsats');
        if (hdop != null) parts.push('HDOP\u202f' + _fmtVal(hdop, '', 2));
        el.textContent = parts.join('  ');
      }
    }

    // Attitude
    if (d.attitude) {
      const i = nearestIdx(d.attitude.timestamps);
      const roll = _nearestVal(d.attitude.roll, i);
      const pitch = _nearestVal(d.attitude.pitch, i);
      const el = document.getElementById('cv-attitude');
      if (el) {
        const parts = [];
        if (roll != null) parts.push('R\u202f' + _fmtVal(roll, '\u00B0'));
        if (pitch != null) parts.push('P\u202f' + _fmtVal(pitch, '\u00B0'));
        el.textContent = parts.join('  ');
      }
    }

    // Vibration
    if (d.vibration) {
      const i = nearestIdx(d.vibration.timestamps);
      const x = _nearestVal(d.vibration.accel_x, i);
      const y = _nearestVal(d.vibration.accel_y, i);
      const z = _nearestVal(d.vibration.accel_z, i);
      const el = document.getElementById('cv-vibration');
      if (el && (x != null || y != null || z != null)) {
        const mag = Math.sqrt((x||0)**2 + (y||0)**2 + (z||0)**2);
        el.textContent = _fmtVal(mag, 'm/s\u00B2');
      }
    }

    // Velocity
    if (d.velocity) {
      const i = nearestIdx(d.velocity.timestamps);
      const vx = _nearestVal(d.velocity.vx, i);
      const vy = _nearestVal(d.velocity.vy, i);
      const vz = _nearestVal(d.velocity.vz, i);
      const el = document.getElementById('cv-velocity');
      if (el && (vx != null || vy != null)) {
        const spd = Math.sqrt((vx||0)**2 + (vy||0)**2);
        el.textContent = _fmtVal(spd, 'm/s');
      }
    }
  }

  // ── Helpers ───────────────────────────────────────────

  function formatTime(sec) {
    if (sec == null) return '--';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    const ms = Math.floor((sec % 1) * 10);
    if (m > 0) return m + 'm ' + String(s).padStart(2, '0') + '.' + ms + 's';
    return s + '.' + ms + 's';
  }

  // ── Main render ───────────────────────────────────────

  function render(data, targetEl) {
    const view = targetEl || document.getElementById('cockpit-view');
    if (!view) return;

    // Cleanup old charts
    destroy();

    tsData = data.timeseries || {};
    modeChanges = tsData.mode_changes || [];
    events = tsData.events || [];
    flightDuration = (data.metadata && data.metadata.duration_sec) || 0;

    // Check if we have any data
    const hasData = Object.keys(tsData).some(k =>
      k !== 'mode_changes' && k !== 'events' && tsData[k] && tsData[k].timestamps
    );

    if (!hasData) {
      view.innerHTML = `
        <div class="cockpit-no-data">
          <div class="cockpit-no-data-icon">&#x1F4CA;</div>
          <div class="cockpit-no-data-text">No time-series data available for this flight log.<br>Supported formats: ULog (.ulg), DataFlash (.bin/.log), CSV (.csv)</div>
        </div>`;
      return;
    }

    // Build cockpit HTML
    view.innerHTML = `
      <div class="cockpit-header">
        <div class="cockpit-title">FLIGHT DATA COCKPIT</div>
        <div class="cockpit-controls">
          <button class="cockpit-btn active" onclick="Cockpit.setLayout('grid')">2-Col</button>
          <button class="cockpit-btn" onclick="Cockpit.setLayout('single')">1-Col</button>
        </div>
      </div>

      <div class="cockpit-timeline">
        <div class="timeline-scrubber-label">
          <span>FLIGHT TIMELINE</span>
          <span class="timeline-cursor-time">--</span>
        </div>
        <div class="timeline-modes-bar"></div>
        <div class="timeline-slider-wrap">
          <div class="timeline-slider-track"></div>
          <div class="timeline-slider-cursor" style="left:0%"></div>
        </div>
        <div class="timeline-event-markers"></div>
      </div>

      <div class="cockpit-grid" id="cockpit-grid">
        <div class="chart-panel full-width" id="cp-altitude">
          <div class="chart-header">
            <span class="chart-title">Altitude</span>
            <span class="chart-value" id="cv-altitude"></span>
          </div>
          <div class="chart-body" id="chart-altitude"></div>
        </div>

        <div class="chart-panel" id="cp-battery">
          <div class="chart-header">
            <span class="chart-title">Battery</span>
            <span class="chart-value" id="cv-battery"></span>
          </div>
          <div class="chart-body" id="chart-battery"></div>
        </div>

        <div class="chart-panel" id="cp-gps">
          <div class="chart-header">
            <span class="chart-title">GPS Health</span>
            <span class="chart-value" id="cv-gps"></span>
          </div>
          <div class="chart-body" id="chart-gps"></div>
        </div>

        <div class="chart-panel full-width" id="cp-motors">
          <div class="chart-header">
            <span class="chart-title">Motor Outputs</span>
            <span class="chart-value" id="cv-motors"></span>
          </div>
          <div class="chart-body" id="chart-motors"></div>
        </div>

        <div class="chart-panel" id="cp-attitude">
          <div class="chart-header">
            <span class="chart-title">Attitude</span>
            <span class="chart-value" id="cv-attitude"></span>
          </div>
          <div class="chart-body" id="chart-attitude"></div>
        </div>

        <div class="chart-panel" id="cp-vibration">
          <div class="chart-header">
            <span class="chart-title">Vibration</span>
            <span class="chart-value" id="cv-vibration"></span>
          </div>
          <div class="chart-body" id="chart-vibration"></div>
        </div>

        <div class="chart-panel" id="cp-velocity">
          <div class="chart-header">
            <span class="chart-title">Velocity</span>
            <span class="chart-value" id="cv-velocity"></span>
          </div>
          <div class="chart-body" id="chart-velocity"></div>
        </div>

        <div class="chart-panel" id="cp-rc">
          <div class="chart-header">
            <span class="chart-title">RC Signal</span>
            <span class="chart-value" id="cv-rc"></span>
          </div>
          <div class="chart-body" id="chart-rc"></div>
        </div>
      </div>
    `;

    // Render timeline
    const timelineEl = view.querySelector('.cockpit-timeline');
    renderTimeline(timelineEl, modeChanges, events, flightDuration);

    // Build charts (slight delay for DOM to settle)
    requestAnimationFrame(() => {
      const builders = [
        ['chart-altitude',  buildAltitudeChart],
        ['chart-battery',   buildBatteryChart],
        ['chart-gps',       buildGPSChart],
        ['chart-motors',    buildMotorsChart],
        ['chart-attitude',  buildAttitudeChart],
        ['chart-vibration', buildVibrationChart],
        ['chart-velocity',  buildVelocityChart],
        ['chart-rc',        buildRCChart],
      ];

      builders.forEach(([id, builder]) => {
        const el = document.getElementById(id);
        if (!el) return;
        try {
          const chart = builder(el, tsData);
          if (chart) {
            charts.push(chart);
          } else {
            el.innerHTML = '<div class="chart-empty">No data available</div>';
            // Hide the panel if no data
            const panel = el.closest('.chart-panel');
            if (panel) panel.style.display = 'none';
          }
        } catch (err) {
          console.error(`Chart ${id} failed:`, err);
          el.innerHTML = '<div class="chart-empty">Chart error</div>';
        }
      });
    });
  }

  function destroy() {
    charts.forEach(c => { try { c.destroy(); } catch(_) {} });
    charts = [];
    tsData = null;
    cursorTime = null;
  }

  function setLayout(mode) {
    const grid = document.getElementById('cockpit-grid');
    if (!grid) return;

    // Update buttons
    document.querySelectorAll('.cockpit-controls .cockpit-btn').forEach(btn => {
      btn.classList.remove('active');
    });
    event.target.classList.add('active');

    if (mode === 'single') {
      grid.classList.add('single-col');
    } else {
      grid.classList.remove('single-col');
    }

    // Resize all charts
    requestAnimationFrame(() => {
      charts.forEach(c => {
        const parent = c.root.parentElement;
        if (parent) {
          c.setSize({ width: parent.clientWidth - 12, height: c.height });
        }
      });
    });
  }

  // ── Resize handler ────────────────────────────────────
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      charts.forEach(c => {
        const parent = c.root.parentElement;
        if (parent) {
          c.setSize({ width: parent.clientWidth - 12, height: c.height });
        }
      });
    }, 200);
  });

  // ── Public API ────────────────────────────────────────
  return { render, destroy, setLayout };
})();
