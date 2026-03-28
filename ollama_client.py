import json
import urllib.request
import asyncio

async def generate_with_ollama(prompt, model="qwen2.5:1.5b", system_prompt=None):
    """Generates a response from the local Ollama instance asynchronously."""
    url = "http://127.0.0.1:11434/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    if system_prompt:
        payload["system"] = system_prompt
        
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

    def _make_request():
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get('response', '').strip()
        except Exception as e:
            return f"[Ollama Error: {e}]"

    return await asyncio.to_thread(_make_request)
