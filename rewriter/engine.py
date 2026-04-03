import asyncio
from .providers.ollama_provider import ollama_rewrite
from .providers.openrouter_provider import openrouter_rewrite
from .config import REWRITE_CONFIG


async def rewrite_text(text, prompt=None, provider=None):
    """
    Rewrite text to avoid copyright. Tries providers in fallback order.
    Returns rewritten text on success, original text on total failure.
    """
    if not text or not text.strip():
        return text

    system_prompt = prompt or REWRITE_CONFIG["default_prompt"]

    # If specific provider requested
    if provider:
        providers = [provider]
    else:
        providers = REWRITE_CONFIG["provider_order"]

    for prov in providers:
        try:
            if prov == "ollama":
                result = await ollama_rewrite(text, system_prompt)
            elif prov == "openrouter":
                result = await openrouter_rewrite(text, system_prompt)
            else:
                continue

            if result and not result.startswith("[") and len(result) > 10:
                return result
        except Exception:
            continue

    return text  # fallback: return original
