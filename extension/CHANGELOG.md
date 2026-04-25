# Changelog

## [1.0.0] - 2026-04-25

### Initial Release

- Multi-agent AI code review (Bug Detector, Security Analyzer, Performance Reviewer, Style Checker)
- AST-based deterministic analysis with complexity metrics
- RAG-enhanced prompts with knowledge base of vulnerability patterns
- LLM verification pass to filter false positives
- Support for multiple LLM providers: Groq (free), Together AI, OpenRouter, Ollama (local), HuggingFace
- Inline VS Code diagnostics with severity-colored squiggly underlines
- Quick Fix code actions with suggested fixes
- Review dashboard with charts and AI vs Human comparison
- Quality score (0-100) normalized by code size
- Review active file, selection, or git changes
- Auto-review on save (optional)
- Benchmark suite with precision/recall/F1 metrics
