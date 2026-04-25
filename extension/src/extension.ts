/**
 * AI Code Review Agent — VS Code Extension entry point
 *
 * Registers commands, diagnostics, code actions, and the webview dashboard.
 * Communicates with the Python backend via HTTP.
 */

import * as vscode from "vscode";
import { BackendClient, ReviewResponse, ReviewFinding } from "./backendClient";
import { ReviewPanel } from "./reviewPanel";
import { DashboardPanel } from "./dashboardPanel";

let client: BackendClient;
let diagnosticCollection: vscode.DiagnosticCollection;
let statusBarItem: vscode.StatusBarItem;
let lastReviewResponse: ReviewResponse | undefined;
let reviewInProgress = false;  // backpressure guard

export function activate(context: vscode.ExtensionContext) {
  console.log("AI Code Review Agent is now active");

  // Initialize
  const config = vscode.workspace.getConfiguration("codeReviewAgent");
  const backendUrl = config.get<string>("backendUrl", "http://127.0.0.1:19280");
  client = new BackendClient(backendUrl);

  diagnosticCollection =
    vscode.languages.createDiagnosticCollection("ai-code-review");
  context.subscriptions.push(diagnosticCollection);

  // Status bar
  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    100
  );
  statusBarItem.command = "codeReviewAgent.showDashboard";
  statusBarItem.text = "$(search-fuzzy) AI Review";
  statusBarItem.tooltip = "AI Code Review Agent — Click to open dashboard";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // ── Commands ──────────────────────────────────────────────────────────

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewAgent.reviewFile",
      () => reviewCurrentFile(context)
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewAgent.reviewSelection",
      () => reviewSelection(context)
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewAgent.reviewGitChanges",
      () => reviewGitChanges(context)
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewAgent.showDashboard",
      () => DashboardPanel.createOrShow(context.extensionUri, lastReviewResponse)
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewAgent.runBenchmark",
      () => runBenchmark()
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewAgent.clearDiagnostics",
      () => {
        diagnosticCollection.clear();
        lastReviewResponse = undefined;
        vscode.window.showInformationMessage("AI Review: Diagnostics cleared.");
      }
    )
  );

  // ── Code Action Provider ──────────────────────────────────────────────
  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider(
      { scheme: "file" },
      new ReviewCodeActionProvider(),
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }
    )
  );

  // ── Auto-review on save ───────────────────────────────────────────────
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const autoReview = vscode.workspace
        .getConfiguration("codeReviewAgent")
        .get<boolean>("autoReviewOnSave", false);
      if (autoReview) {
        reviewDocument(doc, context);
      }
    })
  );

  // Check backend health on activation
  checkBackendHealth();
}

export function deactivate() {
  diagnosticCollection?.dispose();
  statusBarItem?.dispose();
}

// ── Review functions ────────────────────────────────────────────────────────

async function reviewCurrentFile(context: vscode.ExtensionContext) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("No active editor to review.");
    return;
  }
  await reviewDocument(editor.document, context);
}

async function reviewSelection(context: vscode.ExtensionContext) {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.selection.isEmpty) {
    vscode.window.showWarningMessage("No text selected to review.");
    return;
  }
  const code = editor.document.getText(editor.selection);
  const filename = editor.document.fileName;
  const startLine = editor.selection.start.line;

  await performReview(code, filename, context, startLine);
}

async function reviewGitChanges(context: vscode.ExtensionContext) {
  // Get git diff of staged/unstaged changes
  const gitExtension = vscode.extensions.getExtension("vscode.git");
  if (!gitExtension) {
    vscode.window.showWarningMessage("Git extension not available.");
    return;
  }

  const git = gitExtension.exports.getAPI(1);
  const repo = git.repositories[0];
  if (!repo) {
    vscode.window.showWarningMessage("No Git repository found.");
    return;
  }

  const diff = await repo.diff(true); // staged changes
  const unstaged = await repo.diff(false);
  const fullDiff = diff || unstaged;

  if (!fullDiff) {
    vscode.window.showInformationMessage("No Git changes to review.");
    return;
  }

  await performReview(fullDiff, "git-changes.diff", context, 0, true);
}

async function reviewDocument(
  document: vscode.TextDocument,
  context: vscode.ExtensionContext
) {
  const code = document.getText();
  const filename = document.fileName;
  await performReview(code, filename, context);
}

async function performReview(
  code: string,
  filename: string,
  context: vscode.ExtensionContext,
  lineOffset: number = 0,
  diffMode: boolean = false
) {
  if (reviewInProgress) {
    vscode.window.showWarningMessage("AI Review: A review is already in progress. Please wait.");
    return;
  }
  reviewInProgress = true;

  const config = vscode.workspace.getConfiguration("codeReviewAgent");
  const agents = config.get<string[]>("agents");

  statusBarItem.text = "$(loading~spin) Reviewing…";
  statusBarItem.tooltip = "AI Code Review in progress…";

  try {
    const response = await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "AI Code Review",
        cancellable: true,
      },
      async (progress, token) => {
        progress.report({ message: "Sending code to review agents…" });

        // Wrap in a promise that rejects on cancellation
        return new Promise<ReviewResponse>((resolve, reject) => {
          token.onCancellationRequested(() => reject(new Error("Review cancelled by user")));
          client.reviewCode({
            code,
            filename: filename.split(/[/\\]/).pop() || filename,
            diff_mode: diffMode,
            agents: agents,
          }).then(resolve, reject);
        });
      }
    );

    lastReviewResponse = response;

    // Update diagnostics
    const uri = vscode.Uri.file(filename);
    const diagnostics = response.findings
      .filter((f) => filterBySeverity(f, config.get<string>("minSeverity", "info")))
      .map((f) => findingToDiagnostic(f, lineOffset));
    diagnosticCollection.set(uri, diagnostics);

    // Update status bar
    const icon = response.summary.critical > 0 ? "$(error)" :
                 response.summary.high > 0 ? "$(warning)" : "$(check)";
    statusBarItem.text = `${icon} ${response.summary.total_issues} issues | Score: ${response.summary.overall_quality_score}`;
    statusBarItem.tooltip =
      `Quality: ${response.summary.overall_quality_score}/100\n` +
      `Critical: ${response.summary.critical} | High: ${response.summary.high}\n` +
      `Medium: ${response.summary.medium} | Low: ${response.summary.low}\n` +
      `Review time: ${response.summary.review_time_seconds.toFixed(1)}s\n` +
      ((response as any).partial_review ? "⚠ Partial review (some agents failed)\n" : "") +
      `Click to open dashboard`;

    // Show review panel
    ReviewPanel.createOrShow(context.extensionUri, response);

    // Summary notification
    const partial = (response as any).partial_review ? " (partial)" : "";
    const msg = `AI Review${partial}: ${response.summary.total_issues} issues found ` +
      `(Score: ${response.summary.overall_quality_score}/100, ` +
      `${response.summary.review_time_seconds.toFixed(1)}s)`;
    if (response.summary.critical > 0) {
      vscode.window.showErrorMessage(msg, "Show Details").then((action) => {
        if (action) {
          DashboardPanel.createOrShow(context.extensionUri, response);
        }
      });
    } else {
      vscode.window.showInformationMessage(msg);
    }
  } catch (err: any) {
    statusBarItem.text = "$(error) AI Review Failed";
    const message = err.message || String(err);

    if (message.includes("cancelled")) {
      statusBarItem.text = "$(search-fuzzy) AI Review";
      vscode.window.showInformationMessage("AI Review: Cancelled.");
    } else if (message.includes("ECONNREFUSED") || message.includes("fetch") || message.includes("unreachable")) {
      vscode.window.showErrorMessage(
        "AI Review: Cannot connect to backend. Is the server running? " +
        "Start it with: cd backend && python -m uvicorn app.main:app --port 19280"
      );
    } else if (message.includes("timed out")) {
      vscode.window.showErrorMessage(
        "AI Review: Request timed out. Try reviewing a smaller file or fewer agents."
      );
    } else if (message.includes("429")) {
      vscode.window.showWarningMessage(
        "AI Review: Rate limited. Please wait a moment and try again."
      );
    } else {
      vscode.window.showErrorMessage(`AI Review failed: ${message}`);
    }
  } finally {
    reviewInProgress = false;
  }
}

// ── Benchmark ─────────────────────────────────────────────────────────────────

async function runBenchmark() {
  const datasets = ["python_bugs", "security_vulns"];
  const pick = await vscode.window.showQuickPick(datasets, {
    placeHolder: "Select benchmark dataset",
  });
  if (!pick) { return; }

  try {
    const result = await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Running Benchmark",
        cancellable: false,
      },
      async (progress) => {
        progress.report({ message: `Evaluating ${pick} dataset…` });
        return await client.runBenchmark(pick);
      }
    );

    const msg =
      `Benchmark Results (${pick}):\n` +
      `Precision: ${(result.precision * 100).toFixed(1)}% | ` +
      `Recall: ${(result.recall * 100).toFixed(1)}% | ` +
      `F1: ${(result.f1_score * 100).toFixed(1)}%\n` +
      `Time savings: ${result.time_savings_percent.toFixed(0)}%`;
    vscode.window.showInformationMessage(msg);
  } catch (err: any) {
    vscode.window.showErrorMessage(`Benchmark failed: ${err.message}`);
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function findingToDiagnostic(
  finding: ReviewFinding,
  lineOffset: number = 0
): vscode.Diagnostic {
  const startLine = Math.max(0, finding.line_start - 1 + lineOffset);
  const endLine = Math.max(0, finding.line_end - 1 + lineOffset);
  const range = new vscode.Range(startLine, 0, endLine, 1000);

  const severityMap: Record<string, vscode.DiagnosticSeverity> = {
    critical: vscode.DiagnosticSeverity.Error,
    high: vscode.DiagnosticSeverity.Error,
    medium: vscode.DiagnosticSeverity.Warning,
    low: vscode.DiagnosticSeverity.Information,
    info: vscode.DiagnosticSeverity.Hint,
  };

  const diag = new vscode.Diagnostic(
    range,
    `[${finding.severity.toUpperCase()}] ${finding.title}\n${finding.description}`,
    severityMap[finding.severity] ?? vscode.DiagnosticSeverity.Warning
  );

  diag.source = `AI Review (${finding.agent})`;
  diag.code = finding.rule_id || finding.cwe_id || finding.category;

  // Store suggestion for code actions
  if (finding.suggested_code) {
    (diag as any)._suggestedCode = finding.suggested_code;
    (diag as any)._suggestion = finding.suggestion;
  }

  return diag;
}

function filterBySeverity(finding: ReviewFinding, minSeverity: string): boolean {
  const order = ["critical", "high", "medium", "low", "info"];
  const findingIdx = order.indexOf(finding.severity);
  const minIdx = order.indexOf(minSeverity);
  return findingIdx <= minIdx;
}

async function checkBackendHealth() {
  try {
    const health = await client.healthCheck();
    if (!health.llm_connected) {
      vscode.window.showWarningMessage(
        "AI Review: LLM backend is not connected. Check your HuggingFace token and model availability."
      );
    }
  } catch {
    // Silently ignore — user will see error when they try to review
  }
}

// ── Code Action Provider ──────────────────────────────────────────────────────

class ReviewCodeActionProvider implements vscode.CodeActionProvider {
  provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range,
    context: vscode.CodeActionContext
  ): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];

    for (const diag of context.diagnostics) {
      if (diag.source?.startsWith("AI Review")) {
        const suggestedCode = (diag as any)._suggestedCode;
        const suggestion = (diag as any)._suggestion;

        if (suggestedCode) {
          const fix = new vscode.CodeAction(
            `Fix: ${suggestion || "Apply suggested fix"}`,
            vscode.CodeActionKind.QuickFix
          );
          fix.diagnostics = [diag];
          fix.edit = new vscode.WorkspaceEdit();
          fix.edit.replace(document.uri, diag.range, suggestedCode);
          fix.isPreferred = true;
          actions.push(fix);
        }
      }
    }

    return actions;
  }
}
