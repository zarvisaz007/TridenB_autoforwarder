# TridenB Rewriter Engine

Self-contained AI text rewriting module for the TridenB Autoforwarder.

## Purpose
Rewrites forwarded messages so destination channels don't receive copyright strikes.
The original meaning, data, and structure are preserved — only the wording changes.

## Provider Fallback Chain
1. **Ollama** (local) — fast, free, private. Default model: `gemma3:1b`
2. **OpenRouter** (cloud) — fallback if Ollama is down. Default model: `google/gemma-3n-e4b-it:free`

## Configuration
Set in `.env` at the project root:
- `OLLAMA_REWRITE_MODEL` — Ollama model name (default: `gemma3:1b`)
- `OPENROUTER_API_KEY` — required for OpenRouter fallback
- `OPENROUTER_REWRITE_MODEL` — OpenRouter model (default: `google/gemma-3n-e4b-it:free`)

Edit `rewriter/config.py` to change the default rewrite prompt or provider order.

## Usage
```python
from rewriter import rewrite_text

rewritten = await rewrite_text("Original message here")
rewritten = await rewrite_text("Original", prompt="Custom instruction", provider="ollama")
```

## Adding a New Provider
1. Create `rewriter/providers/your_provider.py` with an async function
2. Import it in `rewriter/engine.py`
3. Add it to the provider order in `rewriter/config.py`
