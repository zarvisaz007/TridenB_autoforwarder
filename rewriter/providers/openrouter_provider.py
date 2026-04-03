import json
import urllib.request
import asyncio
from ..config import REWRITE_CONFIG


async def openrouter_rewrite(text, system_prompt):
    cfg = REWRITE_CONFIG["openrouter"]
    if not cfg["api_key"]:
        raise ValueError("OPENROUTER_API_KEY not set")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]
    payload = {"model": cfg["model"], "messages": messages}
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
        "HTTP-Referer": "https://github.com/zarvisaz007/TridenB_autoforwarderBETA-V2",
        "X-Title": "TridenB Rewriter",
    }
    req = urllib.request.Request(cfg["url"], data=data, headers=headers)

    def _request():
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()

    return await asyncio.to_thread(_request)
