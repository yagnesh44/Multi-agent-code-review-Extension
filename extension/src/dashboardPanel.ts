/**
 * Dashboard Panel — shows metrics, charts, and benchmark comparisons.
 * Demonstrates quantified AI vs Human review performance.
 */

import * as vscode from "vscode";
import { ReviewResponse } from "./backendClient";

export class DashboardPanel {
  public static currentPanel: DashboardPanel | undefined;
  private static readonly viewType = "codeReviewDashboard";

  private readonly _panel: vscode.WebviewPanel;
  private _disposables: vscode.Disposable[] = [];

  public static createOrShow(
    extensionUri: vscode.Uri,
    response?: ReviewResponse
  ) {
    const column = vscode.ViewColumn.One;

    if (DashboardPanel.currentPanel) {
      DashboardPanel.currentPanel._panel.reveal(column);
      if (response) {
        DashboardPanel.currentPanel._update(response);
      }
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      DashboardPanel.viewType,
      "AI Review Dashboard",
      column,
      { enableScripts: true, retainContextWhenHidden: true }
    );

    DashboardPanel.currentPanel = new DashboardPanel(panel, extensionUri, response);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    _extensionUri: vscode.Uri,
    response?: ReviewResponse
  ) {
    this._panel = panel;
    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
    this._update(response);
  }

  public dispose() {
    DashboardPanel.currentPanel = undefined;
    this._panel.dispose();
    while (this._disposables.length) {
      const d = this._disposables.pop();
      if (d) { d.dispose(); }
    }
  }

  private _update(response?: ReviewResponse) {
    this._panel.webview.html = this._getHtml(response);
  }

  private _getHtml(r?: ReviewResponse): string {
    // Compute category distribution for chart
    const catCounts: Record<string, number> = {};
    const sevCounts: Record<string, number> = {};
    const agentCounts: Record<string, number> = {};
    if (r) {
      for (const f of r.findings) {
        catCounts[f.category] = (catCounts[f.category] || 0) + 1;
        sevCounts[f.severity] = (sevCounts[f.severity] || 0) + 1;
        agentCounts[f.agent] = (agentCounts[f.agent] || 0) + 1;
      }
    }

    const noData = !r
      ? `<div style="text-align:center;padding:60px;color:#888;">
           <h2>No review data yet</h2>
           <p>Run a code review first using <code>Ctrl+Shift+R</code> or the command palette.</p>
         </div>`
      : "";

    const chartData = r
      ? `
      <h2>📊 Distribution Analysis</h2>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin:20px 0;">
        <div class="chart-card">
          <h3>By Category</h3>
          ${buildBarChart(catCounts, { bug: "#e74c3c", security: "#e67e22", performance: "#f1c40f", style: "#3498db", best_practice: "#9b59b6" })}
        </div>
        <div class="chart-card">
          <h3>By Severity</h3>
          ${buildBarChart(sevCounts, { critical: "#dc3545", high: "#fd7e14", medium: "#ffc107", low: "#17a2b8", info: "#6c757d" })}
        </div>
        <div class="chart-card">
          <h3>By Agent</h3>
          ${buildBarChart(agentCounts, { ast_analyzer: "#2ecc71", bug_detector: "#e74c3c", security_analyzer: "#e67e22", performance_reviewer: "#f1c40f", style_checker: "#3498db" })}
        </div>
      </div>
      `
      : "";

    const comparisonSection = r
      ? `
      <h2>⚡ AI vs Human Review Comparison</h2>
      <table style="width:100%;border-collapse:collapse;margin:16px 0;">
        <thead>
          <tr style="border-bottom:2px solid #444;">
            <th style="text-align:left;padding:10px;">Metric</th>
            <th style="text-align:center;padding:10px;">AI Agent</th>
            <th style="text-align:center;padding:10px;">Human Reviewer (Est.)</th>
            <th style="text-align:center;padding:10px;">Advantage</th>
          </tr>
        </thead>
        <tbody>
          <tr style="border-bottom:1px solid #333;">
            <td style="padding:10px;">Review Time</td>
            <td style="text-align:center;color:#4caf50;font-weight:bold;">${r.summary.review_time_seconds.toFixed(1)} seconds</td>
            <td style="text-align:center;color:#ff9800;">${r.summary.estimated_human_review_minutes.toFixed(1)} minutes</td>
            <td style="text-align:center;color:#4caf50;font-weight:bold;">${r.summary.time_savings_percent.toFixed(0)}% faster</td>
          </tr>
          <tr style="border-bottom:1px solid #333;">
            <td style="padding:10px;">Coverage</td>
            <td style="text-align:center;color:#4caf50;">100% of lines</td>
            <td style="text-align:center;color:#ff9800;">~60-80% (fatigue)</td>
            <td style="text-align:center;color:#4caf50;">Full coverage</td>
          </tr>
          <tr style="border-bottom:1px solid #333;">
            <td style="padding:10px;">Consistency</td>
            <td style="text-align:center;color:#4caf50;">Deterministic rules + AI</td>
            <td style="text-align:center;color:#ff9800;">Varies by reviewer</td>
            <td style="text-align:center;color:#4caf50;">Consistent</td>
          </tr>
          <tr style="border-bottom:1px solid #333;">
            <td style="padding:10px;">Categories Checked</td>
            <td style="text-align:center;color:#4caf50;">${r.agents_used.length} specialized agents</td>
            <td style="text-align:center;color:#ff9800;">1-2 focus areas</td>
            <td style="text-align:center;color:#4caf50;">Broader scope</td>
          </tr>
          <tr style="border-bottom:1px solid #333;">
            <td style="padding:10px;">Availability</td>
            <td style="text-align:center;color:#4caf50;">24/7 instant</td>
            <td style="text-align:center;color:#ff9800;">Business hours, queued</td>
            <td style="text-align:center;color:#4caf50;">Always available</td>
          </tr>
          <tr>
            <td style="padding:10px;">Issues Found</td>
            <td style="text-align:center;font-weight:bold;">${r.summary.total_issues} issues</td>
            <td style="text-align:center;color:#888;">Varies</td>
            <td style="text-align:center;">Quantified with confidence</td>
          </tr>
        </tbody>
      </table>
      `
      : "";

    const confidenceSection = r && r.findings.length > 0
      ? `
      <h2>🎯 Confidence Distribution</h2>
      <div style="display:flex;gap:8px;align-items:flex-end;height:120px;margin:16px 0;padding:0 20px;">
        ${buildConfidenceHistogram(r.findings.map((f) => f.confidence))}
      </div>
      <p style="color:#888;text-align:center;font-size:12px;">Confidence scores of reported findings (higher = more certain)</p>
      `
      : "";

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Review Dashboard</title>
  <style>
    body { font-family: var(--vscode-font-family, 'Segoe UI', sans-serif); padding: 20px; color: #ddd; background: #1e1e1e; }
    h1 { border-bottom: 2px solid #0078d4; padding-bottom: 10px; }
    h2 { margin-top: 30px; color: #0078d4; }
    .chart-card { background: #252526; border-radius: 8px; padding: 16px; }
    .chart-card h3 { margin: 0 0 12px; font-size: 14px; color: #ccc; }
    table { background: #252526; border-radius: 8px; }
    th { color: #0078d4; }
    code { background: #333; padding: 2px 6px; border-radius: 3px; }
  </style>
</head>
<body>
  <h1>📈 AI Code Review Agent — Dashboard</h1>
  ${noData}
  ${r ? `
  <div style="display:grid;grid-template-columns:repeat(4, 1fr);gap:12px;margin:20px 0;">
    <div style="background:#252526;border-radius:8px;padding:20px;text-align:center;">
      <div style="font-size:36px;font-weight:bold;color:${r.summary.overall_quality_score >= 80 ? "#4caf50" : r.summary.overall_quality_score >= 50 ? "#ffc107" : "#dc3545"};">${r.summary.overall_quality_score}</div>
      <div style="color:#999;margin-top:4px;">Quality Score</div>
    </div>
    <div style="background:#252526;border-radius:8px;padding:20px;text-align:center;">
      <div style="font-size:36px;font-weight:bold;">${r.summary.total_issues}</div>
      <div style="color:#999;margin-top:4px;">Issues Found</div>
    </div>
    <div style="background:#252526;border-radius:8px;padding:20px;text-align:center;">
      <div style="font-size:36px;font-weight:bold;color:#4caf50;">${r.summary.review_time_seconds.toFixed(1)}s</div>
      <div style="color:#999;margin-top:4px;">AI Review Time</div>
    </div>
    <div style="background:#252526;border-radius:8px;padding:20px;text-align:center;">
      <div style="font-size:36px;font-weight:bold;color:#4caf50;">${r.summary.time_savings_percent.toFixed(0)}%</div>
      <div style="color:#999;margin-top:4px;">Time Saved vs Human</div>
    </div>
  </div>
  ` : ""}
  ${chartData}
  ${comparisonSection}
  ${confidenceSection}
</body>
</html>`;
  }
}

// ── Chart Helpers ─────────────────────────────────────────────────────────────

function buildBarChart(
  data: Record<string, number>,
  colors: Record<string, string>
): string {
  const max = Math.max(...Object.values(data), 1);
  return Object.entries(data)
    .map(
      ([key, count]) => `
    <div style="display:flex;align-items:center;margin:6px 0;">
      <span style="width:120px;font-size:12px;color:#ccc;text-overflow:ellipsis;overflow:hidden;">${key}</span>
      <div style="flex:1;background:#333;border-radius:4px;height:20px;margin:0 8px;">
        <div style="width:${(count / max) * 100}%;background:${colors[key] || "#0078d4"};height:100%;border-radius:4px;transition:width 0.3s;"></div>
      </div>
      <span style="font-size:12px;font-weight:bold;min-width:20px;">${count}</span>
    </div>`
    )
    .join("");
}

function buildConfidenceHistogram(confidences: number[]): string {
  const buckets = [0, 0, 0, 0, 0]; // 0-20, 20-40, 40-60, 60-80, 80-100
  for (const c of confidences) {
    const idx = Math.min(4, Math.floor(c * 5));
    buckets[idx]++;
  }
  const max = Math.max(...buckets, 1);
  const labels = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"];
  const colors = ["#dc3545", "#fd7e14", "#ffc107", "#17a2b8", "#4caf50"];

  return buckets
    .map(
      (count, i) => `
    <div style="flex:1;text-align:center;">
      <div style="background:${colors[i]};height:${(count / max) * 100}px;border-radius:4px 4px 0 0;min-height:2px;"></div>
      <div style="font-size:10px;color:#999;margin-top:4px;">${labels[i]}</div>
      <div style="font-size:11px;font-weight:bold;">${count}</div>
    </div>`
    )
    .join("");
}
