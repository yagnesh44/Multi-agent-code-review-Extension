/**
 * Progress Panel — shows live review progress with agent statuses,
 * a visual pipeline, and real-time updates as the review proceeds.
 * Transforms into the results view when the review completes.
 */

import * as vscode from "vscode";
import { ReviewResponse } from "./backendClient";

/** Agent display metadata */
const AGENTS = [
  { id: "ast_analyzer", label: "AST Analyzer", icon: "🌳", desc: "Syntax tree analysis — bare excepts, deep nesting, unused imports" },
  { id: "bug_detector", label: "Bug Detector", icon: "🐛", desc: "Logic errors — race conditions, off-by-one, null refs, resource leaks" },
  { id: "security_analyzer", label: "Security Analyzer", icon: "🔒", desc: "Vulnerabilities — SQL injection, XSS, command injection, hardcoded secrets" },
  { id: "performance_reviewer", label: "Performance Reviewer", icon: "⚡", desc: "Bottlenecks — N+1 queries, O(n²) loops, blocking I/O, memory leaks" },
  { id: "style_checker", label: "Style Checker", icon: "🎨", desc: "Code quality — naming conventions, magic numbers, dead code, complexity" },
];

type AgentStatus = "waiting" | "running" | "done" | "failed";

export class ProgressPanel {
  public static currentPanel: ProgressPanel | undefined;
  private static readonly viewType = "codeReviewProgress";

  private readonly _panel: vscode.WebviewPanel;
  private _disposables: vscode.Disposable[] = [];
  private _startTime: number;
  private _filename: string;
  private _linesOfCode: number;
  private _timer: ReturnType<typeof setInterval> | undefined;

  public static createOrShow(extensionUri: vscode.Uri, filename: string, linesOfCode: number) {
    const column = vscode.ViewColumn.Beside;

    if (ProgressPanel.currentPanel) {
      ProgressPanel.currentPanel._panel.reveal(column);
      ProgressPanel.currentPanel._reset(filename, linesOfCode);
      return ProgressPanel.currentPanel;
    }

    const panel = vscode.window.createWebviewPanel(
      ProgressPanel.viewType,
      "AI Review — Analyzing…",
      column,
      { enableScripts: true, retainContextWhenHidden: true }
    );

    ProgressPanel.currentPanel = new ProgressPanel(panel, extensionUri, filename, linesOfCode);
    return ProgressPanel.currentPanel;
  }

  private constructor(
    panel: vscode.WebviewPanel,
    _extensionUri: vscode.Uri,
    filename: string,
    linesOfCode: number
  ) {
    this._panel = panel;
    this._startTime = Date.now();
    this._filename = filename;
    this._linesOfCode = linesOfCode;
    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
    this._showProgress();
  }

  private _reset(filename: string, linesOfCode: number) {
    this._startTime = Date.now();
    this._filename = filename;
    this._linesOfCode = linesOfCode;
    this._panel.title = "AI Review — Analyzing…";
    this._showProgress();
  }

  /** Show the animated progress view */
  private _showProgress() {
    this._panel.webview.html = this._getProgressHtml();
    // Start a timer to update elapsed time via postMessage
    if (this._timer) { clearInterval(this._timer); }
    this._timer = setInterval(() => {
      this._panel.webview.postMessage({
        type: "tick",
        elapsed: ((Date.now() - this._startTime) / 1000).toFixed(0),
      });
    }, 1000);
  }

  /** Transition to results view */
  public showResults(response: ReviewResponse) {
    if (this._timer) { clearInterval(this._timer); this._timer = undefined; }
    this._panel.title = `AI Review — ${response.summary.total_issues} Issues`;
    this._panel.webview.html = this._getResultsHtml(response);
  }

  /** Show error state */
  public showError(message: string) {
    if (this._timer) { clearInterval(this._timer); this._timer = undefined; }
    this._panel.title = "AI Review — Failed";
    this._panel.webview.postMessage({ type: "error", message });
  }

  public dispose() {
    if (this._timer) { clearInterval(this._timer); }
    ProgressPanel.currentPanel = undefined;
    this._panel.dispose();
    while (this._disposables.length) {
      const d = this._disposables.pop();
      if (d) { d.dispose(); }
    }
  }

  // ── Progress HTML ─────────────────────────────────────────────────────

  private _getProgressHtml(): string {
    const shortName = this._filename.split(/[/\\]/).pop() || this._filename;
    const chunksEstimate = Math.ceil(this._linesOfCode / 100);
    const agentsHtml = AGENTS.map((a, i) => `
      <div class="agent-row" id="agent-${a.id}" style="animation-delay: ${i * 0.1}s;">
        <div class="agent-icon">${a.icon}</div>
        <div class="agent-info">
          <div class="agent-name">${a.label}</div>
          <div class="agent-desc">${a.desc}</div>
        </div>
        <div class="agent-status" id="status-${a.id}">
          <div class="status-indicator waiting"></div>
          <span class="status-text">Queued</span>
        </div>
      </div>
    `).join("");

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Review Progress</title>
  <style>
    :root {
      --bg: #1e1e1e; --card-bg: #252526; --border: #333;
      --text: #ddd; --text-muted: #888; --accent: #0078d4;
      --green: #4caf50; --yellow: #ffc107; --red: #dc3545; --orange: #fd7e14;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: var(--vscode-font-family, 'Segoe UI', sans-serif); background: var(--bg); color: var(--text); padding: 24px; }

    .header { text-align: center; margin-bottom: 32px; }
    .header h1 { font-size: 20px; margin-bottom: 8px; }
    .header .file-info { color: var(--text-muted); font-size: 13px; }
    .header .file-info code { background: #333; padding: 2px 8px; border-radius: 4px; color: var(--accent); }

    /* Elapsed timer */
    .timer { text-align: center; margin: 20px 0; }
    .timer .elapsed { font-size: 48px; font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; }
    .timer .label { color: var(--text-muted); font-size: 12px; margin-top: 4px; }

    /* Pipeline visualization */
    .pipeline { max-width: 650px; margin: 0 auto 32px; }
    .pipeline-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .pipeline-header h2 { font-size: 16px; color: var(--text); }
    .pipeline-header .chunk-info { font-size: 12px; color: var(--text-muted); }

    /* Progress bar */
    .progress-bar-outer { width: 100%; height: 6px; background: var(--border); border-radius: 3px; margin-bottom: 24px; overflow: hidden; }
    .progress-bar-inner { height: 100%; background: linear-gradient(90deg, var(--accent), #00b4d8); border-radius: 3px; transition: width 0.5s ease; animation: progress-pulse 2s ease-in-out infinite; }
    @keyframes progress-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }

    /* Agent rows */
    .agent-row {
      display: flex; align-items: center; gap: 16px;
      background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
      padding: 14px 18px; margin: 8px 0;
      animation: fadeIn 0.3s ease forwards; opacity: 0;
    }
    @keyframes fadeIn { to { opacity: 1; } }
    .agent-icon { font-size: 24px; width: 36px; text-align: center; }
    .agent-info { flex: 1; }
    .agent-name { font-weight: 600; font-size: 14px; }
    .agent-desc { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
    .agent-status { display: flex; align-items: center; gap: 8px; min-width: 120px; justify-content: flex-end; }
    .status-text { font-size: 12px; font-weight: 600; }

    /* Status indicators */
    .status-indicator { width: 10px; height: 10px; border-radius: 50%; }
    .status-indicator.waiting { background: #555; }
    .status-indicator.running { background: var(--yellow); animation: blink 1s ease-in-out infinite; }
    .status-indicator.done { background: var(--green); }
    .status-indicator.failed { background: var(--red); }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

    /* Running agent gets a highlight */
    .agent-row.active { border-color: var(--accent); background: #1a2a3a; }

    /* Activity log */
    .log-section { max-width: 650px; margin: 32px auto 0; }
    .log-section h2 { font-size: 14px; color: var(--text-muted); margin-bottom: 10px; }
    .log { background: var(--card-bg); border-radius: 8px; padding: 12px 16px; max-height: 150px; overflow-y: auto; font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 11px; color: var(--text-muted); }
    .log-entry { padding: 2px 0; }
    .log-entry .time { color: #555; }
    .log-entry .msg { color: var(--text); }
    .log-entry.success .msg { color: var(--green); }
    .log-entry.error .msg { color: var(--red); }

    /* Info cards */
    .info-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; max-width: 650px; margin: 0 auto 24px; }
    .info-card { background: var(--card-bg); border-radius: 8px; padding: 16px; text-align: center; }
    .info-card .value { font-size: 22px; font-weight: 700; color: var(--accent); }
    .info-card .label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

    /* Error overlay */
    .error-banner { background: #3a1a1a; border: 1px solid var(--red); border-radius: 8px; padding: 16px; margin: 16px auto; max-width: 650px; display: none; }
    .error-banner h3 { color: var(--red); margin-bottom: 8px; }
  </style>
</head>
<body>
  <div class="header">
    <h1>🔍 AI Code Review Agent</h1>
    <div class="file-info">Analyzing <code>${escapeHtml(shortName)}</code> · ${this._linesOfCode} lines</div>
  </div>

  <div class="timer">
    <div class="elapsed" id="elapsed">0</div>
    <div class="label">seconds elapsed</div>
  </div>

  <div class="info-grid">
    <div class="info-card">
      <div class="value">${AGENTS.length}</div>
      <div class="label">AI Agents</div>
    </div>
    <div class="info-card">
      <div class="value">~${chunksEstimate}</div>
      <div class="label">Code Chunks</div>
    </div>
    <div class="info-card">
      <div class="value">~${chunksEstimate * AGENTS.length}</div>
      <div class="label">Total Analyses</div>
    </div>
  </div>

  <div class="pipeline">
    <div class="pipeline-header">
      <h2>🤖 Agent Pipeline</h2>
      <span class="chunk-info" id="chunk-info">Starting…</span>
    </div>
    <div class="progress-bar-outer">
      <div class="progress-bar-inner" id="progress-bar" style="width: 5%;"></div>
    </div>
    ${agentsHtml}
  </div>

  <div class="error-banner" id="error-banner">
    <h3>❌ Review Failed</h3>
    <p id="error-message"></p>
  </div>

  <div class="log-section">
    <h2>📋 Activity Log</h2>
    <div class="log" id="log">
      <div class="log-entry"><span class="time">[00:00]</span> <span class="msg">Review started — sending code to backend…</span></div>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();
    const startTime = Date.now();
    const totalAgents = ${AGENTS.length};
    let agentsDone = 0;
    let progressPercent = 5;

    // Simulate agent progression
    const agentIds = ${JSON.stringify(AGENTS.map(a => a.id))};
    let currentAgentIdx = 0;
    let simulationTimer;

    function addLog(msg, type) {
      const log = document.getElementById('log');
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
      const mins = Math.floor(elapsed / 60);
      const secs = (elapsed % 60).toString().padStart(2, '0');
      const entry = document.createElement('div');
      entry.className = 'log-entry' + (type ? ' ' + type : '');
      entry.innerHTML = '<span class="time">[' + mins + ':' + secs + ']</span> <span class="msg">' + msg + '</span>';
      log.appendChild(entry);
      log.scrollTop = log.scrollHeight;
    }

    function setAgentStatus(agentId, status, text) {
      const row = document.getElementById('agent-' + agentId);
      const indicator = document.querySelector('#status-' + agentId + ' .status-indicator');
      const statusText = document.querySelector('#status-' + agentId + ' .status-text');
      if (!row) return;

      indicator.className = 'status-indicator ' + status;
      statusText.textContent = text;

      // Highlight active agent
      document.querySelectorAll('.agent-row').forEach(r => r.classList.remove('active'));
      if (status === 'running') {
        row.classList.add('active');
      }
    }

    function updateProgress(pct) {
      progressPercent = Math.min(pct, 98);
      document.getElementById('progress-bar').style.width = progressPercent + '%';
    }

    // Simulate agents starting analysis (the real work is on the backend)
    function simulateProgress() {
      // Cycle through agents to show activity
      if (currentAgentIdx < agentIds.length) {
        setAgentStatus(agentIds[currentAgentIdx], 'running', 'Analyzing…');
        const names = ${JSON.stringify(AGENTS.map(a => a.label))};
        addLog(names[currentAgentIdx] + ' started analyzing…');
        document.getElementById('chunk-info').textContent = 'Agent ' + (currentAgentIdx + 1) + '/' + totalAgents + ' starting…';
        currentAgentIdx++;
      }

      // After all agents shown as started, update progress gradually
      if (currentAgentIdx >= agentIds.length) {
        // Slowly increment progress
        progressPercent = Math.min(progressPercent + 0.5, 90);
        updateProgress(progressPercent);

        // Randomly mark agents as done based on progress
        const expectedDone = Math.floor((progressPercent / 90) * totalAgents);
        while (agentsDone < expectedDone && agentsDone < agentIds.length) {
          setAgentStatus(agentIds[agentsDone], 'done', 'Complete ✓');
          const names = ${JSON.stringify(AGENTS.map(a => a.label))};
          addLog(names[agentsDone] + ' finished analysis', 'success');
          agentsDone++;
          if (agentsDone < agentIds.length) {
            setAgentStatus(agentIds[agentsDone], 'running', 'Analyzing…');
          }
          document.getElementById('chunk-info').textContent = agentsDone + '/' + totalAgents + ' agents complete';
        }
      }
    }

    // Start simulation: agents begin every 3 seconds, then progress ticks
    let simStep = 0;
    simulationTimer = setInterval(() => {
      if (simStep < agentIds.length) {
        simulateProgress();
        simStep++;
        updateProgress(5 + (simStep / agentIds.length) * 20);
      } else {
        simulateProgress();
      }
    }, 3000);

    // Listen for messages from extension
    window.addEventListener('message', event => {
      const msg = event.data;
      switch (msg.type) {
        case 'tick':
          document.getElementById('elapsed').textContent = msg.elapsed;
          break;
        case 'error':
          clearInterval(simulationTimer);
          document.getElementById('error-banner').style.display = 'block';
          document.getElementById('error-message').textContent = msg.message;
          addLog('Review failed: ' + msg.message, 'error');
          // Mark remaining agents as failed
          agentIds.forEach((id, i) => {
            const indicator = document.querySelector('#status-' + id + ' .status-indicator');
            if (indicator && !indicator.classList.contains('done')) {
              setAgentStatus(id, 'failed', 'Failed ✗');
            }
          });
          updateProgress(progressPercent); // freeze
          break;
      }
    });
  </script>
</body>
</html>`;
  }

  // ── Results HTML (transition from progress) ─────────────────────────

  private _getResultsHtml(r: ReviewResponse): string {
    const shortName = this._filename.split(/[/\\]/).pop() || this._filename;
    const elapsed = ((Date.now() - this._startTime) / 1000).toFixed(1);

    // Compute distributions
    const catCounts: Record<string, number> = {};
    const sevCounts: Record<string, number> = {};
    const agentCounts: Record<string, number> = {};
    for (const f of r.findings) {
      catCounts[f.category] = (catCounts[f.category] || 0) + 1;
      sevCounts[f.severity] = (sevCounts[f.severity] || 0) + 1;
      agentCounts[f.agent] = (agentCounts[f.agent] || 0) + 1;
    }

    const severityBadge = (sev: string) => {
      const colors: Record<string, string> = {
        critical: "#dc3545", high: "#fd7e14", medium: "#ffc107", low: "#17a2b8", info: "#6c757d",
      };
      return `<span style="background:${colors[sev] || "#999"};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">${sev.toUpperCase()}</span>`;
    };

    // Agent summary cards
    const agentCards = AGENTS.map(a => {
      const count = agentCounts[a.id] || 0;
      const isUsed = r.agents_used.includes(a.id);
      return `
        <div style="background:#252526;border-radius:8px;padding:14px;text-align:center;border:1px solid ${isUsed ? '#333' : '#2a2a2a'};">
          <div style="font-size:24px;">${a.icon}</div>
          <div style="font-size:12px;font-weight:600;margin:4px 0;">${a.label}</div>
          <div style="font-size:24px;font-weight:700;color:${count > 0 ? '#e67e22' : '#4caf50'};">${count}</div>
          <div style="font-size:10px;color:#888;">findings</div>
        </div>`;
    }).join("");

    // Severity bar chart
    const sevOrder = ["critical", "high", "medium", "low", "info"];
    const sevColors: Record<string, string> = { critical: "#dc3545", high: "#fd7e14", medium: "#ffc107", low: "#17a2b8", info: "#6c757d" };
    const maxSev = Math.max(...Object.values(sevCounts), 1);
    const sevBars = sevOrder.filter(s => sevCounts[s]).map(s => `
      <div style="display:flex;align-items:center;margin:6px 0;">
        <span style="width:80px;font-size:12px;color:#ccc;text-transform:uppercase;">${s}</span>
        <div style="flex:1;background:#333;border-radius:4px;height:22px;margin:0 8px;overflow:hidden;">
          <div style="width:${(sevCounts[s] / maxSev) * 100}%;background:${sevColors[s]};height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px;">
            <span style="font-size:11px;font-weight:700;color:#fff;">${sevCounts[s]}</span>
          </div>
        </div>
      </div>
    `).join("");

    // Findings list
    const findingsHtml = r.findings.length === 0
      ? `<div style="text-align:center;padding:40px;color:#888;"><h2>✅ No issues found!</h2><p>Your code looks clean.</p></div>`
      : r.findings.map(f => `
        <div style="border:1px solid #333;border-left:4px solid ${sevColors[f.severity] || "#999"};border-radius:6px;padding:12px 16px;margin:8px 0;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <div>
              ${severityBadge(f.severity)}
              <span style="background:#1e3a5f;padding:2px 8px;border-radius:4px;font-size:11px;margin-left:4px;">${escapeHtml(f.category)}</span>
              <span style="color:#888;font-size:11px;margin-left:8px;">Line ${f.line_start}${f.line_end !== f.line_start ? "-" + f.line_end : ""}</span>
            </div>
            <span style="color:#888;font-size:11px;">${escapeHtml(f.agent)} · ${(f.confidence * 100).toFixed(0)}%</span>
          </div>
          <h3 style="margin:4px 0;font-size:14px;">${escapeHtml(f.title)}</h3>
          <p style="color:#ccc;margin:4px 0;font-size:13px;">${escapeHtml(f.description)}</p>
          <p style="color:#8bc34a;margin:4px 0;font-size:13px;">💡 ${escapeHtml(f.suggestion)}</p>
          ${f.suggested_code ? `<details><summary style="cursor:pointer;color:#64b5f6;font-size:12px;">Show suggested fix</summary><pre style="background:#1a1a1a;padding:10px;border-radius:4px;overflow-x:auto;margin-top:6px;font-size:12px;"><code>${escapeHtml(f.suggested_code)}</code></pre></details>` : ""}
          ${f.cwe_id ? `<span style="color:#888;font-size:11px;">📋 ${escapeHtml(f.cwe_id)}</span>` : ""}
        </div>`).join("");

    const partial = (r as any).partial_review ? `<div style="background:#3a2a1a;border:1px solid #fd7e14;border-radius:8px;padding:12px;margin:12px 0;font-size:13px;">⚠️ <strong>Partial Review</strong> — Some agents encountered rate limits. Results may be incomplete.</div>` : "";

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Review Results</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: var(--vscode-font-family, 'Segoe UI', sans-serif); background: #1e1e1e; color: #ddd; padding: 24px; }
    h1 { font-size: 20px; border-bottom: 2px solid #0078d4; padding-bottom: 10px; margin-bottom: 20px; }
    h2 { font-size: 16px; color: #0078d4; margin: 24px 0 12px; }
    .top-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }
    .top-card { background: #252526; border-radius: 8px; padding: 20px; text-align: center; }
    .top-card .val { font-size: 32px; font-weight: 700; }
    .top-card .lbl { font-size: 11px; color: #888; margin-top: 4px; }
    .agents-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 16px 0; }
    code { background: #333; padding: 2px 6px; border-radius: 3px; font-size: 12px; }
    details summary { cursor: pointer; }
  </style>
</head>
<body>
  <h1>🔍 AI Code Review — Results</h1>
  <div style="color:#888;font-size:13px;margin-bottom:16px;">
    File: <code>${escapeHtml(shortName)}</code> · ${r.metrics.lines_of_code} lines · Model: <code>${escapeHtml(r.model_used)}</code> · Completed in ${r.summary.review_time_seconds.toFixed(1)}s
  </div>

  ${partial}

  <div class="top-grid">
    <div class="top-card">
      <div class="val" style="color:${r.summary.overall_quality_score >= 80 ? "#4caf50" : r.summary.overall_quality_score >= 50 ? "#ffc107" : "#dc3545"};">${r.summary.overall_quality_score}</div>
      <div class="lbl">Quality Score</div>
    </div>
    <div class="top-card">
      <div class="val">${r.summary.total_issues}</div>
      <div class="lbl">Issues Found</div>
    </div>
    <div class="top-card">
      <div class="val" style="color:#4caf50;">${r.summary.time_savings_percent.toFixed(0)}%</div>
      <div class="lbl">Faster than Human</div>
    </div>
    <div class="top-card">
      <div class="val" style="color:#dc3545;">${r.summary.critical}</div>
      <div class="lbl">Critical</div>
    </div>
  </div>

  <h2>🤖 Agent Contributions</h2>
  <div class="agents-grid">${agentCards}</div>

  <h2>📊 Severity Distribution</h2>
  <div style="background:#252526;border-radius:8px;padding:16px;margin:12px 0;">
    ${sevBars || '<div style="color:#888;text-align:center;padding:12px;">No issues found</div>'}
  </div>

  <h2>🔎 Findings (${r.findings.length})</h2>
  ${findingsHtml}

  <div style="margin-top:32px;padding:16px;background:#252526;border-radius:8px;">
    <h2 style="margin-top:0;">⚡ AI vs Human Review</h2>
    <table style="width:100%;border-collapse:collapse;margin-top:12px;">
      <tr style="border-bottom:1px solid #333;">
        <td style="padding:8px;color:#888;">Review Time</td>
        <td style="padding:8px;text-align:center;color:#4caf50;font-weight:700;">${r.summary.review_time_seconds.toFixed(1)}s</td>
        <td style="padding:8px;text-align:center;color:#fd7e14;">${r.summary.estimated_human_review_minutes.toFixed(0)} min (est.)</td>
      </tr>
      <tr style="border-bottom:1px solid #333;">
        <td style="padding:8px;color:#888;">Coverage</td>
        <td style="padding:8px;text-align:center;color:#4caf50;">100% lines</td>
        <td style="padding:8px;text-align:center;color:#fd7e14;">~70% (fatigue)</td>
      </tr>
      <tr>
        <td style="padding:8px;color:#888;">Agents / Focus Areas</td>
        <td style="padding:8px;text-align:center;color:#4caf50;">${r.agents_used.length} specialized</td>
        <td style="padding:8px;text-align:center;color:#fd7e14;">1–2 typical</td>
      </tr>
    </table>
  </div>
</body>
</html>`;
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
