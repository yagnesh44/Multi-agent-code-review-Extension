/**
 * Review Panel — shows detailed review findings in a VS Code webview.
 */

import * as vscode from "vscode";
import { ReviewResponse } from "./backendClient";

export class ReviewPanel {
  public static currentPanel: ReviewPanel | undefined;
  private static readonly viewType = "codeReviewResults";

  private readonly _panel: vscode.WebviewPanel;
  private _disposables: vscode.Disposable[] = [];

  public static createOrShow(
    extensionUri: vscode.Uri,
    response?: ReviewResponse
  ) {
    const column = vscode.ViewColumn.Beside;

    if (ReviewPanel.currentPanel) {
      ReviewPanel.currentPanel._panel.reveal(column);
      if (response) {
        ReviewPanel.currentPanel._update(response);
      }
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      ReviewPanel.viewType,
      "AI Code Review Results",
      column,
      { enableScripts: true, retainContextWhenHidden: true }
    );

    ReviewPanel.currentPanel = new ReviewPanel(panel, extensionUri, response);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    _extensionUri: vscode.Uri,
    response?: ReviewResponse
  ) {
    this._panel = panel;
    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
    if (response) {
      this._update(response);
    }
  }

  public dispose() {
    ReviewPanel.currentPanel = undefined;
    this._panel.dispose();
    while (this._disposables.length) {
      const d = this._disposables.pop();
      if (d) { d.dispose(); }
    }
  }

  private _update(response: ReviewResponse) {
    this._panel.webview.html = this._getHtml(response);
  }

  private _getHtml(r: ReviewResponse): string {
    const severityBadge = (sev: string) => {
      const colors: Record<string, string> = {
        critical: "#dc3545",
        high: "#fd7e14",
        medium: "#ffc107",
        low: "#17a2b8",
        info: "#6c757d",
      };
      return `<span style="background:${colors[sev] || "#999"};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">${sev.toUpperCase()}</span>`;
    };

    const findingsHtml = r.findings.length === 0
      ? `<div style="text-align:center;padding:40px;color:#6c757d;">
           <h2>✅ No issues found!</h2>
           <p>Your code looks clean.</p>
         </div>`
      : r.findings
          .map(
            (f, i) => `
        <div style="border:1px solid #333;border-left:4px solid ${
          { critical: "#dc3545", high: "#fd7e14", medium: "#ffc107", low: "#17a2b8", info: "#6c757d" }[f.severity] || "#999"
        };border-radius:6px;padding:12px 16px;margin:8px 0;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <div>
              ${severityBadge(f.severity)}
              <span style="background:#1e3a5f;padding:2px 8px;border-radius:4px;font-size:11px;margin-left:4px;">${f.category}</span>
              <span style="color:#888;font-size:11px;margin-left:8px;">Line ${f.line_start}${f.line_end !== f.line_start ? "-" + f.line_end : ""}</span>
            </div>
            <span style="color:#888;font-size:11px;">${f.agent} | ${(f.confidence * 100).toFixed(0)}% confidence</span>
          </div>
          <h3 style="margin:4px 0;">${f.title}</h3>
          <p style="color:#ccc;margin:4px 0;">${f.description}</p>
          <p style="color:#8bc34a;margin:4px 0;">💡 ${f.suggestion}</p>
          ${
            f.suggested_code
              ? `<details><summary style="cursor:pointer;color:#64b5f6;">Show suggested fix</summary>
                   <pre style="background:#1e1e1e;padding:10px;border-radius:4px;overflow-x:auto;margin-top:6px;"><code>${escapeHtml(f.suggested_code)}</code></pre>
                 </details>`
              : ""
          }
          ${f.cwe_id ? `<span style="color:#888;font-size:11px;">📋 ${f.cwe_id}</span>` : ""}
        </div>`
          )
          .join("");

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Code Review Results</title>
  <style>
    body { font-family: var(--vscode-font-family, 'Segoe UI', sans-serif); padding: 16px; color: #ddd; background: #1e1e1e; }
    h1 { border-bottom: 2px solid #444; padding-bottom: 8px; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 16px 0; }
    .stat-card { background: #252526; border-radius: 8px; padding: 16px; text-align: center; }
    .stat-card .value { font-size: 28px; font-weight: bold; }
    .stat-card .label { font-size: 12px; color: #999; margin-top: 4px; }
    .score-ring { width: 80px; height: 80px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: bold; margin: 0 auto 8px; }
  </style>
</head>
<body>
  <h1>🔍 AI Code Review Results</h1>

  <div class="stats">
    <div class="stat-card">
      <div class="score-ring" style="border: 4px solid ${r.summary.overall_quality_score >= 80 ? "#4caf50" : r.summary.overall_quality_score >= 50 ? "#ffc107" : "#dc3545"};">
        ${r.summary.overall_quality_score}
      </div>
      <div class="label">Quality Score</div>
    </div>
    <div class="stat-card">
      <div class="value">${r.summary.total_issues}</div>
      <div class="label">Total Issues</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#dc3545;">${r.summary.critical}</div>
      <div class="label">Critical</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#fd7e14;">${r.summary.high}</div>
      <div class="label">High</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#ffc107;">${r.summary.medium}</div>
      <div class="label">Medium</div>
    </div>
    <div class="stat-card">
      <div class="value">${r.summary.review_time_seconds.toFixed(1)}s</div>
      <div class="label">Review Time</div>
    </div>
    <div class="stat-card">
      <div class="value">${r.summary.estimated_human_review_minutes.toFixed(0)}m</div>
      <div class="label">Est. Human Time</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#4caf50;">${r.summary.time_savings_percent.toFixed(0)}%</div>
      <div class="label">Time Saved</div>
    </div>
  </div>

  <h2>📊 Code Metrics</h2>
  <div class="stats">
    <div class="stat-card">
      <div class="value">${r.metrics.lines_of_code}</div>
      <div class="label">Lines of Code</div>
    </div>
    <div class="stat-card">
      <div class="value">${r.metrics.cyclomatic_complexity ?? "N/A"}</div>
      <div class="label">Cyclomatic Complexity</div>
    </div>
    <div class="stat-card">
      <div class="value">${r.metrics.cognitive_complexity ?? "N/A"}</div>
      <div class="label">Cognitive Complexity</div>
    </div>
    <div class="stat-card">
      <div class="value">${r.metrics.maintainability_index ?? "N/A"}</div>
      <div class="label">Maintainability Index</div>
    </div>
    <div class="stat-card">
      <div class="value">${r.metrics.function_count}</div>
      <div class="label">Functions</div>
    </div>
    <div class="stat-card">
      <div class="value">${r.metrics.class_count}</div>
      <div class="label">Classes</div>
    </div>
  </div>

  <h2>🔎 Findings (${r.findings.length})</h2>
  <div style="margin-bottom:12px;">
    <em style="color:#888;">Agents used: ${r.agents_used.join(", ")} | Model: ${r.model_used}</em>
  </div>
  ${findingsHtml}
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
