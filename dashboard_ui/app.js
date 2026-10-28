const $ = (selector, root = document) => root.querySelector(selector);
const app = $('#app');
let page = 'live';
let status = {};
let analyticsHistory = { sessions: [], summary: {} };
let streamFailed = false;

const esc = value => String(value ?? '—').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));
const duration = value => {
  const seconds = Math.max(0, Number(value) || 0);
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
};
const row = (label, value, tone = '') =>
  `<div class="data-row" data-label="${label}"><span>${label}</span><b class="value ${tone}">${value}</b></div>`;
const metric = (label, value, foot, id = '') =>
  `<article class="card metric"><div class="metric-label">${label}</div><div class="metric-value" ${id ? `id="${id}-value"` : ''}>${value}</div><div class="metric-foot" ${id ? `id="${id}-foot"` : ''}>${foot}</div></article>`;
const pageHead = (kicker, title, subtitle) =>
  `<div class="page-head"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p class="subhead">${subtitle}</p></div></div>`;

function setSystemPill() {
  const camera = !!status.camera_connected;
  const serial = !!status.serial_port_open;
  const tone = camera && serial ? 'ok' : camera || serial ? 'warn' : 'bad';
  const label = camera && serial ? 'CAMERA + SERIAL OPEN' : camera ? 'ESP32 PORT CLOSED' : serial ? 'CAMERA OFFLINE' : 'HARDWARE OFFLINE';
  $('#system-pill').innerHTML = `<i class="dot ${tone}"></i><span>${label}</span>`;
}

function renderLive() {
  const s = status;
  app.innerHTML = `${pageHead('MONITORING OVERVIEW', 'Live driver monitoring', 'Real-time observations from the connected camera and detector.')}
    <div class="live-layout">
      <section class="card camera-card"><div class="camera-frame">
        <img id="camera-stream" src="/api/stream" alt="Live processed USB camera stream">
        <div id="camera-placeholder" class="camera-placeholder"><div class="camera-icon">◉</div><strong id="placeholder-title">${s.camera_connected ? 'Waiting for camera frames' : 'Camera unavailable'}</strong><p id="placeholder-copy">${s.camera_connected ? 'The local detector will show its processed camera feed here.' : 'Check camera index 0, USB connection, and camera permissions.'}</p></div>
        <div class="cam-top"><span id="camera-badge" class="badge"><i class="dot ${s.camera_connected ? 'ok' : 'bad'}"></i>${s.camera_connected ? 'CAMERA LIVE' : 'CAMERA OFFLINE'}</span><span id="alert-chip" class="badge alert-chip" ${s.alert_active ? '' : 'hidden'}>● ALERT CYCLE ACTIVE</span></div>
        <div class="cam-bottom"><span class="cam-caption">OpenCV Haar Cascade · USB camera ${esc(s.camera_index)}</span><span id="overlay-state" class="badge">${esc(s.eyes || 'UNKNOWN')}</span></div>
      </div></section>
      <aside class="side-stack"><section class="card status-card"><h2 class="card-title">CURRENT DRIVER <span class="tag">LIVE</span></h2>
        <div class="status-main"><div id="status-symbol" class="status-symbol">?</div><div><strong id="driver-title">Starting detector</strong><small id="driver-detail">Waiting for the first frame</small></div></div>
        <div class="rows">${row('Eye state', 'UNKNOWN')}${row('Eyes closed for', '—')}${row('Alert cycle', 'Inactive')}${row('Trigger threshold', '2.0 seconds')}${row('FaceLandmarker', 'Loading')}${row('Model blink score', '—')}${row('Yawns this session', '—')}${row('Yawning now', '—')}${row('Head nods this session', '—')}${row('Head pose', '—')}${row('Head turn from neutral', '—')}${row('Look-away episodes', '—')}${row('ESP32 serial port', 'Checking')}${row('Monitoring time', '0.0s')}</div>
        <div class="note">The alert indicator reports the detector’s command cycle. An open COM port does not confirm the ESP32 or buzzer is responding.</div>
      </section></aside>
    </div>
    <h2 class="section-title">LIVE FATIGUE SIGNALS</h2><div class="metric-grid">${metric('CAMERA', 'Checking', 'Configured index 0', 'camera')}${metric('YAWNS', '—', 'Model unavailable', 'yawns')}${metric('HEAD NODS', '—', 'Model unavailable', 'nods')}${metric('LOOK-AWAY', '—', 'Model unavailable', 'distraction')}${metric('ALERT OUTPUT', 'Standby', 'No current alert command', 'alert')}</div>`;
  const image = $('#camera-stream');
  image.addEventListener('load', () => { streamFailed = false; $('#camera-placeholder').hidden = true; });
  image.addEventListener('error', () => {
    streamFailed = true;
    $('#camera-placeholder').hidden = false;
    $('#placeholder-title').textContent = 'Camera stream unavailable';
    $('#placeholder-copy').textContent = 'The local detector is not publishing camera frames.';
  });
  updateLive();
}

function renderAnalytics() {
  const s = status;
  app.innerHTML = `${pageHead('SESSION INSIGHTS', 'Analytics', 'Completed drive sessions and the current live detector signals.')}
    <div class="metric-grid five">${metric('COMPLETED SESSIONS', '—', 'Saved session records', 'history-sessions')}${metric('TOTAL DRIVE', '—', 'Across completed sessions', 'history-drive')}${metric('EYE CLOSURE', '—', 'Cumulative closed-eye time', 'history-closure')}${metric('ALERTS', '—', 'Across completed sessions', 'history-alerts')}${metric('CLOSURE RATE', '—', 'Closed-eye time / drive time', 'history-rate')}</div>
    <h2 class="section-title">RECENT SESSION HISTORY</h2><section class="card history-card"><div id="history-chart" class="history-chart"><span class="muted">Loading saved sessions…</span></div><div class="table-wrap"><table class="history-table"><thead><tr><th>Session</th><th>Started</th><th>Duration</th><th>Eyes closed</th><th>Alerts</th><th>Longest closure</th></tr></thead><tbody id="history-rows"><tr><td colspan="6">Loading saved sessions…</td></tr></tbody></table></div></section>
    <h2 class="section-title">CURRENT RUN SIGNALS</h2><div class="metric-grid five">${metric('MONITORING TIME', duration(s.uptime_seconds), 'Current run', 'analytics-session')}${metric('CURRENT EYE CLOSURE', s.eyes === 'CLOSED' ? duration(s.closed_duration) : s.eyes === 'OPEN' ? '0.0s' : 'N/A', 'Continuous closure now', 'analytics-eyes')}${metric('YAWNS', s.face_model_available ? esc(s.yawn_count) : 'N/A', 'Model-observed this run', 'analytics-yawns')}${metric('HEAD NODS', s.face_model_available ? esc(s.head_nod_count) : 'N/A', 'Model-observed this run', 'analytics-nods')}${metric('LOOK-AWAY EPISODES', s.face_model_available ? esc(s.distraction_count) : 'N/A', 'Head yaw vs neutral', 'analytics-distraction')}</div>
    <div class="chart-grid">
      <article class="card chart-card"><div class="chart-title">Closure vs trigger threshold</div><p id="closure-summary">Eyes are currently classified open.</p><div class="measure-track"><span id="closure-progress" class="measure-fill closure-fill"></span></div><small class="meter-caption">${Number(s.closed_threshold_seconds ?? 2).toFixed(1)} seconds to alert trigger</small></article>
      <article class="card chart-card"><div class="chart-title">Current alert command cycle</div><p id="alert-summary">No alert cycle is active.</p><div class="measure-track"><span id="alert-progress" class="measure-fill alert-fill"></span></div><small class="meter-caption">${Number(s.buzzer_duration_seconds ?? 5).toFixed(1)} second cycle</small></article>
      <article class="card chart-card"><div class="chart-title">Model availability</div><p id="model-summary">Loading the bundled FaceLandmarker model.</p><span id="model-tag" class="tag">CHECKING</span></article>
    </div>
    <h2 class="section-title">LIVE EVENT COUNTS</h2><section class="card status-card"><div class="rows">${row('Yawn events', '—')}${row('Head nod events', '—')}${row('Sustained look-away episodes', '—')}${row('Current model face', '—')}</div><div class="note">History uses the detector’s saved session summaries. Yawns, head nods, and look-away counts are available for the current run only.</div></section>`;
  updateAnalytics();
  refreshAnalyticsHistory();
}

function refreshAnalyticsHistory() {
  fetch('/api/analytics', { cache: 'no-store' }).then(response => {
    if (!response.ok) throw new Error('analytics unavailable');
    return response.json();
  }).then(data => {
    analyticsHistory = data;
    if (page === 'analytics') renderAnalyticsHistory();
  }).catch(() => {
    const rows = $('#history-rows');
    if (rows) rows.innerHTML = '<tr><td colspan="6">Could not load saved session history.</td></tr>';
  });
}

function renderAnalyticsHistory() {
  const summary = analyticsHistory.summary || {};
  const sessions = analyticsHistory.sessions || [];
  const values = {
    'history-sessions': String(summary.session_count ?? 0),
    'history-drive': duration(summary.total_duration_seconds),
    'history-closure': duration(summary.closed_eye_seconds),
    'history-alerts': String(summary.alert_count ?? 0),
    'history-rate': `${Number(summary.average_fatigue_percent || 0).toFixed(1)}%`,
  };
  Object.entries(values).forEach(([id, value]) => { const element = $(`#${id}-value`); if (element) element.textContent = value; });
  const chart = $('#history-chart');
  const rows = $('#history-rows');
  if (!chart || !rows) return;
  if (!sessions.length) {
    chart.innerHTML = '<span class="muted">No completed sessions have been saved yet.</span>';
    rows.innerHTML = '<tr><td colspan="6">Completed session summaries will appear here.</td></tr>';
    return;
  }
  const maxClosed = Math.max(1, ...sessions.slice(0, 10).map(item => Number(item.closed_eye_seconds) || 0));
  chart.innerHTML = sessions.slice(0, 10).reverse().map(item => {
    const label = item.started_at ? new Date(item.started_at).toLocaleDateString() : item.id;
    const width = Math.max(2, (Number(item.closed_eye_seconds) || 0) / maxClosed * 100);
    return `<div class="history-bar-row"><span>${esc(label)}</span><div class="history-bar-track"><i style="width:${width}%"></i></div><b>${duration(item.closed_eye_seconds)}</b></div>`;
  }).join('');
  rows.innerHTML = sessions.slice(0, 20).map(item => `<tr><td>${esc(item.id)}</td><td>${esc(item.started_at ? new Date(item.started_at).toLocaleString() : '—')}</td><td>${duration(item.duration_seconds)}</td><td>${duration(item.closed_eye_seconds)}</td><td>${esc(item.alert_count)}</td><td>${duration(item.longest_closure_seconds)}</td></tr>`).join('');
}

function renderFleet() {
  const s = status;
  app.innerHTML = `${pageHead('LOCAL STATION', 'Fleet & devices', 'This project currently monitors one local driver station.')}
    <div class="fleet-grid">
      <section class="card device-card"><div class="device-head"><div class="device-icon">◉</div><div><h2>USB camera</h2><p>OpenCV capture · configured index ${esc(s.camera_index)}</p></div><div id="fleet-camera-state" class="status-line"></div></div><div class="rows">${row('Resolution', esc(s.camera_resolution))}${row('Detector', esc(s.face_detector))}${row('Driver state', esc(s.driver))}</div></section>
      <section class="card device-card"><div class="device-head"><div class="device-icon">⌁</div><div><h2>ESP32 serial interface</h2><p>COM handle state · hardware response is not verified</p></div><div id="fleet-serial-state" class="status-line"></div></div><div class="rows">${row('Serial port', esc(s.serial_port))}${row('Baud rate', esc(s.baud_rate))}${row('Last command', esc(s.last_command || 'None'))}</div></section>
      <section class="card device-card"><div class="device-head"><div class="device-icon">◎</div><div><h2>FaceLandmarker model</h2><p>Supplementary vision metrics; does not control ESP32</p></div><div id="fleet-model-state" class="status-line"></div></div><div class="rows">${row('Head nods', esc(s.head_nod_count ?? 'Unavailable'))}${row('Yawns', esc(s.yawn_count ?? 'Unavailable'))}${row('Look-away episodes', esc(s.distraction_count ?? 'Unavailable'))}</div></section>
    </div><h2 class="section-title">FLEET COVERAGE</h2><section class="card empty"><strong>No additional vehicles registered</strong>This is a single local monitoring station. Multi-vehicle fleet data is not configured.</section>`;
  updateFleet();
}

function renderSettings() {
  const s = status;
  app.innerHTML = `${pageHead('SYSTEM CONFIGURATION', 'Settings', 'Read-only values from the running Python detector.')}
    <div class="settings-grid">
      <section class="card setting-card"><h2>DETECTION & HARDWARE</h2><div class="rows">${row('USB camera index', esc(s.camera_index))}${row('Camera resolution', esc(s.camera_resolution))}${row('Face detector', esc(s.face_detector))}${row('Eye detector', esc(s.eye_detector))}${row('Supplementary model', 'models/face_landmarker.task')}${row('FaceLandmarker status', s.face_model_available ? 'Ready' : 'Unavailable')}${row('Yawn heuristic', `MAR > ${Number(s.yawn_mar_threshold ?? .6).toFixed(2)} for ${Number(s.yawn_min_seconds ?? .4).toFixed(2)}s`)}${row('Head nod heuristic', `Pitch drop > ${Number(s.nod_pitch_margin_degrees ?? 12).toFixed(0)}° for ${Number(s.nod_count_after_seconds ?? .6).toFixed(2)}s`)}${row('Head turn heuristic', `Yaw > ${Number(s.distraction_yaw_degrees ?? 30).toFixed(0)}° for ${Number(s.distraction_alert_seconds ?? 2).toFixed(1)}s`)}${row('Serial port', esc(s.serial_port))}${row('Serial baud rate', esc(s.baud_rate))}${row('Eye-closure trigger', `${Number(s.closed_threshold_seconds ?? 2).toFixed(1)} seconds`)}${row('Buzzer cycle', `${Number(s.buzzer_duration_seconds ?? 5).toFixed(1)} seconds`)}</div><div class="note">Yawn is sustained mouth opening (speech may resemble it); look-away uses head yaw relative to neutral, not eye-gaze tracking. These metrics are display-only and never send ESP32 commands.</div></section>
      <section class="card setting-card"><h2>CONNECTION HEALTH</h2><div class="rows">${row('Camera', 'Checking')}${row('ESP32 serial port', 'Checking')}${row('Monitoring process', 'Running')}${row('Local dashboard', '127.0.0.1:8000')}</div><div class="note">Serial status reports whether the COM port is open. This application has no device acknowledgement.</div></section>
    </div>`;
  updateSettings();
}

function updateRow(label, value, tone = '') {
  const item = Array.from(app.querySelectorAll('.data-row')).find(element => element.dataset.label === label);
  if (!item) return;
  const output = item.querySelector('.value');
  output.textContent = value;
  output.className = `value ${tone}`;
}

function updateLive() {
  if (!$('#camera-stream')) return;
  const s = status;
  const eyes = s.eyes || 'UNKNOWN';
  const active = !!s.alert_active;
  const title = active ? 'DROWSINESS ALERT' : eyes === 'CLOSED' ? 'EYES CLOSED' : eyes === 'OPEN' ? 'EYES OPEN' : s.driver || 'STARTING';
  const tone = active ? 'bad' : eyes === 'CLOSED' ? 'warn' : 'ok';
  $('#alert-chip').hidden = !active;
  $('#camera-badge').innerHTML = `<i class="dot ${s.camera_connected ? 'ok' : 'bad'}"></i>${s.camera_connected ? 'CAMERA LIVE' : 'CAMERA OFFLINE'}`;
  $('#overlay-state').textContent = title;
  $('#status-symbol').className = `status-symbol ${tone}`;
  $('#status-symbol').textContent = active ? '!' : eyes === 'OPEN' ? '✓' : eyes === 'CLOSED' ? '◌' : '?';
  $('#driver-title').textContent = title;
  $('#driver-detail').textContent = s.driver === 'FACE DETECTED' ? 'FACE DETECTED' : s.driver || 'Waiting for detector';
  $('#camera-placeholder').hidden = !!s.frame_available && !streamFailed;
  if (!streamFailed) {
    $('#placeholder-title').textContent = s.camera_connected ? 'Waiting for camera frames' : 'Camera unavailable';
    $('#placeholder-copy').textContent = s.camera_connected ? 'The local detector will show its processed camera feed here.' : 'Check camera index 0, USB connection, and camera permissions.';
  }
  updateRow('Eye state', eyes, eyes === 'OPEN' ? 'ok' : eyes === 'CLOSED' ? 'warn' : '');
  updateRow('Eyes closed for', eyes === 'CLOSED' ? duration(s.closed_duration) : '—', eyes === 'CLOSED' ? 'warn' : '');
  updateRow('Alert cycle', active ? `${duration(s.buzzer_remaining)} remaining` : 'Inactive', active ? 'bad' : '');
  updateRow('Trigger threshold', `${Number(s.closed_threshold_seconds || 2).toFixed(1)} seconds`);
  const modelReady = !!s.face_model_available;
  updateRow('FaceLandmarker', modelReady ? (s.face_model_detected ? 'Face tracked' : 'No face in model') : 'Unavailable', modelReady ? 'ok' : 'bad');
  updateRow('Model blink score', modelReady && s.blink_probability != null ? `${Math.round(Number(s.blink_probability) * 100)}%` : 'Unavailable');
  updateRow('Yawns this session', modelReady ? String(s.yawn_count ?? 0) : 'Unavailable', modelReady && Number(s.yawn_count) > 0 ? 'warn' : '');
  updateRow('Yawning now', modelReady ? (s.yawning ? 'Confirmed' : 'No') : 'Unavailable', s.yawning ? 'warn' : '');
  updateRow('Head nods this session', modelReady ? String(s.head_nod_count ?? 0) : 'Unavailable', modelReady && Number(s.head_nod_count) > 0 ? 'warn' : '');
  updateRow('Head pose', !modelReady ? 'Unavailable' : s.face_model_calibrating ? 'Calibrating neutral' : s.head_nod ? `Head down · ${duration(s.head_down_seconds)}` : 'Neutral range', s.head_nod ? 'warn' : '');
  updateRow('Head turn from neutral', !modelReady ? 'Unavailable' : s.distracted ? `${Math.abs(Number(s.yaw_deviation_degrees || 0)).toFixed(0)}° · looking aside` : 'No sustained turn', s.distraction_alert ? 'bad' : s.distracted ? 'warn' : '');
  updateRow('Look-away episodes', modelReady ? String(s.distraction_count ?? 0) : 'Unavailable', s.distraction_alert ? 'bad' : '');
  updateRow('ESP32 serial port', s.serial_port_open ? `Open · ${s.serial_port}` : `Closed · ${s.serial_port}`, s.serial_port_open ? 'ok' : 'bad');
  updateRow('Monitoring time', duration(s.uptime_seconds));
  $('#camera-value').textContent = s.camera_connected ? 'Online' : 'Offline';
  $('#camera-foot').textContent = s.camera_connected ? 'Frame source connected' : `Configured index ${s.camera_index}`;
  $('#serial-value').textContent = s.serial_port_open ? 'Open' : 'Closed';
  $('#serial-foot').textContent = `${s.serial_port} · ${s.baud_rate} baud`;
  $('#yawns-value').textContent = modelReady ? String(s.yawn_count ?? 0) : 'N/A';
  $('#yawns-foot').textContent = modelReady ? `${s.yawning ? 'Yawn detected now' : 'No current yawn'} · MAR ${s.mouth_aspect_ratio ?? '—'}` : 'FaceLandmarker unavailable';
  $('#nods-value').textContent = modelReady ? String(s.head_nod_count ?? 0) : 'N/A';
  $('#nods-foot').textContent = modelReady ? (s.head_nod ? `Head down ${duration(s.head_down_seconds)}` : 'No current head nod') : 'FaceLandmarker unavailable';
  $('#distraction-value').textContent = !modelReady ? 'N/A' : s.distraction_alert ? 'Alert' : s.distracted ? 'Turned' : 'Clear';
  $('#distraction-foot').textContent = modelReady ? `${s.distraction_count ?? 0} look-away episodes · ${s.distraction_seconds ? duration(s.distraction_seconds) : '0.0s'} current` : 'FaceLandmarker unavailable';
  $('#alert-value').textContent = active ? 'Command active' : 'Standby';
  $('#alert-foot').textContent = active ? 'C command cycle is in progress' : 'No current alert command';
}

function updateAnalytics() {
  const s = status;
  $('#analytics-session-value').textContent = duration(s.uptime_seconds);
  $('#analytics-session-foot').textContent = `Monitoring duration ${duration(s.uptime_seconds)}`;
  $('#analytics-eyes-value').textContent = s.eyes === 'CLOSED' ? duration(s.closed_duration) : s.eyes === 'OPEN' ? '0.0s' : 'N/A';
  $('#analytics-eyes-foot').textContent = s.eyes === 'CLOSED' ? 'Current continuous closure' : s.eyes === 'OPEN' ? 'Eyes currently open' : 'Face not detected';
  $('#analytics-yawns-value').textContent = s.face_model_available ? String(s.yawn_count ?? 0) : 'N/A';
  $('#analytics-nods-value').textContent = s.face_model_available ? String(s.head_nod_count ?? 0) : 'N/A';
  $('#analytics-distraction-value').textContent = s.face_model_available ? String(s.distraction_count ?? 0) : 'N/A';
  $('#analytics-yawns-foot').textContent = s.face_model_available ? `${s.yawns_per_minute ?? 0} in the last minute` : 'Model unavailable';
  $('#analytics-nods-foot').textContent = s.face_model_available ? (s.head_nod ? 'Head down now' : 'No current nod') : 'Model unavailable';
  $('#analytics-distraction-foot').textContent = s.face_model_available ? (s.distraction_alert ? 'Sustained head turn now' : 'No sustained head turn') : 'Model unavailable';
  $('#closure-summary').textContent = s.eyes === 'CLOSED' ? `Currently closed for ${duration(s.closed_duration)}.` : s.eyes === 'OPEN' ? 'Eyes are currently classified open.' : 'Eye closure unavailable until a face is detected.';
  $('#alert-summary').textContent = s.alert_active ? `Alert command cycle · ${duration(s.buzzer_remaining)} remaining.` : 'No alert cycle is active.';
  const threshold = Math.max(.1, Number(s.closed_threshold_seconds) || 2);
  const cycle = Math.max(.1, Number(s.buzzer_duration_seconds) || 5);
  $('#closure-progress').style.width = `${s.eyes === 'CLOSED' ? Math.min(100, Number(s.closed_duration || 0) / threshold * 100) : 0}%`;
  $('#alert-progress').style.width = `${s.alert_active ? Math.min(100, Number(s.buzzer_remaining || 0) / cycle * 100) : 0}%`;
  updateRow('Yawn events', s.face_model_available ? String(s.yawn_count ?? 0) : 'Unavailable');
  updateRow('Head nod events', s.face_model_available ? String(s.head_nod_count ?? 0) : 'Unavailable');
  updateRow('Sustained look-away episodes', s.face_model_available ? String(s.distraction_count ?? 0) : 'Unavailable');
  updateRow('Current model face', !s.face_model_available ? 'Model unavailable' : s.face_model_detected ? 'Tracked' : 'Not detected');
  $('#model-summary').textContent = !s.face_model_available ? (s.face_model_error || 'The bundled model could not be loaded.') : s.face_model_calibrating ? 'Face tracked; calibrating a neutral head pose.' : 'Face tracked; nod, yawn, and look-away metrics are active.';
  $('#model-tag').textContent = s.face_model_available ? (s.face_model_calibrating ? 'CALIBRATING' : 'READY') : 'UNAVAILABLE';
}

function updateFleet() {
  const s = status;
  const camera = !!s.camera_connected;
  const serial = !!s.serial_port_open;
  $('#fleet-camera-state').innerHTML = `<i class="dot ${camera ? 'ok' : 'bad'}"></i>${camera ? 'CONNECTED' : 'OFFLINE'}`;
  $('#fleet-serial-state').innerHTML = `<i class="dot ${serial ? 'ok' : 'bad'}"></i>${serial ? 'PORT OPEN' : 'PORT CLOSED'}`;
  const modelReady = !!s.face_model_available;
  $('#fleet-model-state').innerHTML = `<i class="dot ${modelReady ? 'ok' : 'bad'}"></i>${modelReady ? 'READY' : 'UNAVAILABLE'}`;
  updateRow('Driver state', s.driver || 'UNKNOWN');
  updateRow('Serial port', serial ? `Open · ${s.serial_port}` : `Closed · ${s.serial_port}`);
  updateRow('Last command', s.last_command || 'None');
  updateRow('Head nods', modelReady ? String(s.head_nod_count ?? 0) : 'Unavailable');
  updateRow('Yawns', modelReady ? String(s.yawn_count ?? 0) : 'Unavailable');
  updateRow('Look-away episodes', modelReady ? String(s.distraction_count ?? 0) : 'Unavailable');
}

function updateSettings() {
  const s = status;
  updateRow('Camera', s.camera_connected ? 'Connected' : 'Disconnected', s.camera_connected ? 'ok' : 'bad');
  updateRow('ESP32 serial port', s.serial_port_open ? 'Open' : 'Closed', s.serial_port_open ? 'ok' : 'bad');
  updateRow('Monitoring process', s.running ? 'Running' : 'Stopped', s.running ? 'ok' : 'bad');
  updateRow('FaceLandmarker status', s.face_model_available ? 'Ready' : 'Unavailable', s.face_model_available ? 'ok' : 'bad');
}

function render() {
  document.querySelectorAll('.nav-item').forEach(button => button.classList.toggle('active', button.dataset.page === page));
  ({ live: renderLive, analytics: renderAnalytics, fleet: renderFleet, settings: renderSettings }[page] || renderLive)();
}

document.querySelectorAll('.nav-item').forEach(button => button.addEventListener('click', () => {
  page = button.dataset.page;
  render();
}));

async function refresh() {
  try {
    const response = await fetch('/api/status', { cache: 'no-store' });
    if (!response.ok) throw new Error('status unavailable');
    status = await response.json();
    setSystemPill();
    if (!app.querySelector('.page-head')) render();
    else if (page === 'live') updateLive();
    else if (page === 'analytics') updateAnalytics();
    else if (page === 'fleet') updateFleet();
    else updateSettings();
  } catch {
    $('#system-pill').innerHTML = '<i class="dot bad"></i><span>DETECTOR OFFLINE</span>';
    if (!app.querySelector('.page-head')) {
      app.innerHTML = `${pageHead('LOCAL MONITORING', 'Detector unavailable', 'Start the Python monitor to serve actual camera frames and device status.')}<section class="card empty"><strong>Cannot reach the detector</strong>When it is running, open this page at 127.0.0.1:8000.</section>`;
    }
  }
}

refresh();
setInterval(refresh, 800);
setInterval(() => { if (page === 'analytics') refreshAnalyticsHistory(); }, 10000);
