import json
import urllib.request
import asyncio
from ..config import REWRITE_CONFIG


async def ollama_rewrite(text, system_prompt):
    cfg = REWRITE_CONFIG["ollama"]
    payload = {
        "model": cfg["model"],
        "prompt": text,
        "system": system_prompt,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(cfg["url"], data=data, headers={"Content-Type": "application/json"})

    def _request():
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("response", "").strip()

    return await asyncio.to_thread(_request)
