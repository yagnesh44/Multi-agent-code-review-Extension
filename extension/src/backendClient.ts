/**
 * HTTP client for communicating with the Python backend.
 */

// ── Types mirroring backend schemas ─────────────────────────────────────────

export interface ReviewRequest {
  code: string;
  filename: string;
  language?: string;
  context_before?: string;
  context_after?: string;
  diff_mode?: boolean;
  agents?: string[];
}

export interface ReviewFinding {
  line_start: number;
  line_end: number;
  severity: string;
  category: string;
  title: string;
  description: string;
  suggestion: string;
  suggested_code?: string;
  confidence: number;
  agent: string;
  cwe_id?: string;
  rule_id?: string;
}

export interface ReviewSummary {
  total_issues: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
  overall_quality_score: number;
  review_time_seconds: number;
  estimated_human_review_minutes: number;
  time_savings_percent: number;
}

export interface CodeMetrics {
  lines_of_code: number;
  lines_analyzed: number;
  cyclomatic_complexity?: number;
  cognitive_complexity?: number;
  maintainability_index?: number;
  halstead_volume?: number;
  function_count: number;
  class_count: number;
  max_nesting_depth: number;
}

export interface ReviewResponse {
  findings: ReviewFinding[];
  summary: ReviewSummary;
  metrics: CodeMetrics;
  agents_used: string[];
  failed_agents?: string[];
  partial_review: boolean;
  model_used: string;
}

export interface HealthResponse {
  status: string;
  llm_connected: boolean;
  models_available: string[];
  active_model: string;
}

export interface BenchmarkResult {
  dataset: string;
  samples_evaluated: number;
  precision: number;
  recall: number;
  f1_score: number;
  severity_accuracy: number;
  category_accuracy: number;
  mean_confidence: number;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  avg_review_time_seconds: number;
  estimated_human_time_seconds: number;
  time_savings_percent: number;
  per_category: Record<string, Record<string, number>>;
  details: any[];
}

// ── Client ──────────────────────────────────────────────────────────────────

const DEFAULT_TIMEOUT_MS = 180_000; // 3 minutes for review calls
const HEALTH_TIMEOUT_MS = 10_000;
const MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 2_000;

export class BackendClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  async healthCheck(): Promise<HealthResponse> {
    return this.request<HealthResponse>("GET", "/api/health", undefined, HEALTH_TIMEOUT_MS);
  }

  async reviewCode(request: ReviewRequest): Promise<ReviewResponse> {
    return this.request<ReviewResponse>("POST", "/api/review", request, DEFAULT_TIMEOUT_MS);
  }

  async runBenchmark(dataset: string): Promise<BenchmarkResult> {
    return this.request<BenchmarkResult>("POST", "/api/benchmark", { dataset }, DEFAULT_TIMEOUT_MS);
  }

  async listModels(): Promise<{ models: string[]; active: string }> {
    return this.request("GET", "/api/models", undefined, HEALTH_TIMEOUT_MS);
  }

  private async request<T>(
    method: string,
    path: string,
    body?: any,
    timeoutMs: number = DEFAULT_TIMEOUT_MS,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    let lastError: Error | undefined;

    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);

      try {
        const options: RequestInit = {
          method,
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
        };
        if (body) {
          options.body = JSON.stringify(body);
        }

        const response = await fetch(url, options);

        if (response.ok) {
          return response.json() as Promise<T>;
        }

        // Parse error detail
        const text = await response.text();
        let detail = text;
        try {
          const json = JSON.parse(text);
          detail = json.detail || text;
        } catch {}

        // Retry on transient server errors
        if (attempt < MAX_RETRIES && (response.status === 429 || response.status === 502 || response.status === 503 || response.status === 504)) {
          const delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt - 1);
          lastError = new Error(`Backend error (${response.status}): ${detail}`);
          await new Promise((r) => setTimeout(r, delay));
          continue;
        }

        throw new Error(`Backend error (${response.status}): ${detail}`);
      } catch (err: any) {
        if (err.name === "AbortError") {
          throw new Error("Request timed out. The backend may be overloaded or unreachable.");
        }
        // Retry on network errors (ECONNREFUSED, etc.)
        if (attempt < MAX_RETRIES && (err.message?.includes("ECONNREFUSED") || err.message?.includes("fetch"))) {
          lastError = err;
          const delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt - 1);
          await new Promise((r) => setTimeout(r, delay));
          continue;
        }
        throw err;
      } finally {
        clearTimeout(timer);
      }
    }

    throw lastError ?? new Error("Request failed after retries");
  }
}
