# LinkedIn Post Draft

(Attach architecture.png as the post image)

---

I built a multi-agent AI code review system as a VS Code extension — powered entirely by open-source LLMs at zero cost.

⚙️ Architecture:

The backend (Python + FastAPI) runs 5 specialized agents concurrently via asyncio:

• AST Analyzer — fully deterministic using Python's ast module. Catches eval(), hardcoded secrets, mutable defaults, unused imports, deep nesting, cyclomatic complexity. No LLM needed, zero hallucination risk.
• Security Analyzer — LLM-powered with RAG context. ChromaDB stores 100+ vulnerability patterns (SQLi, XSS, path traversal, SSRF). Embeddings via sentence-transformers all-MiniLM-L6-v2 running locally.
• Bug Detector — logic errors, null derefs, type issues. Structured JSON with line numbers + confidence scores.
• Performance Reviewer — N+1 queries, O(n²) patterns, missing caching.
• Style Checker — naming conventions, function length, code organization.

🧠 Key engineering challenges solved:

Cross-domain contamination — without guardrails, the Perf agent reports SQL injection and Security flags O(n²) loops. Fixed with content-based domain filtering: each agent has a keyword frozenset, and _is_in_domain() rejects out-of-scope findings.

False positives — after agents return findings, an LLM verification pass re-checks each one against surrounding code (±3 lines context). 30s timeout with graceful fallback.

Deduplication — ±3 line overlap detection with specialist priority (ast=10 > security=8 > bug=7 > perf=6 > style=5). The right agent always wins.

Rate limits — Groq free tier gives 30 req/min. Solved with staggered agent starts (3s delay), exponential backoff for 429s, and a threading lock on model selection.

📊 Results on a 200-line showcase file with 15+ intentional issues:
→ 14 findings detected, quality score 77.8/100, 0 failed agents
→ Caught: eval() injection, hardcoded credentials, O(n²) loops, deep nesting, mutable defaults, sensitive data logging

🛠️ Stack:
• Python 3.12 + FastAPI + asyncio
• VS Code Extension API (TypeScript)
• Groq free tier — llama-3.3-70b-versatile (also supports Together AI, OpenRouter, Ollama for local inference)
• ChromaDB + sentence-transformers for RAG (fully local)

The extension surfaces findings as native VS Code diagnostics with Quick Fix suggestions, plus a dashboard with charts and quality scoring.

🔗 GitHub: https://github.com/JaiMehta04/CodeReviewAgent

#AgenticAI #CodeReview #OpenSource #LLM #Python #FastAPI #VSCode #SystemDesign #DevTools #SoftwareEngineering

---
