import os
from dotenv import load_dotenv
load_dotenv()

REWRITE_CONFIG = {
    "default_prompt": (
        "You are a professional content rewriter. Rewrite the following message "
        "to convey the same information but with completely different wording, "
        "sentence structure, and phrasing. The rewritten version must: "
        "1) Preserve ALL factual information, numbers, names, and data points. "
        "2) Use different vocabulary and sentence patterns. "
        "3) Sound natural and professional. "
        "4) NOT add any commentary, headers, or meta-text — output ONLY the rewritten message. "
        "5) Keep the same language as the original. "
        "6) Maintain similar length (within 20% of original)."
    ),
    "provider_order": ["ollama", "openrouter"],  # fallback chain
    "ollama": {
        "url": "http://127.0.0.1:11434/api/generate",
        "model": os.getenv("OLLAMA_REWRITE_MODEL", "gemma3:1b"),
        "timeout": 120,
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "model": os.getenv("OPENROUTER_REWRITE_MODEL", "google/gemma-3n-e4b-it:free"),
        "timeout": 30,
    },
}
