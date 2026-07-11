from dotenv import load_dotenv
import os, json, urllib.request, urllib.error

load_dotenv()
key = os.getenv('OPENROUTER_API_KEY')
print('KEY_LOADED', bool(key))

url = 'https://openrouter.ai/api/v1/chat/completions'
payload = {
    'model': 'openai/gpt-4o',
    'max_tokens': 512,
    'temperature': 0.2,
    'messages': [
        {'role': 'user', 'content': 'Hello from test'}
    ]
}

data = json.dumps(payload).encode()
req = urllib.request.Request(url, data=data, headers={
    'Authorization': f'Bearer {key}',
    'Content-Type': 'application/json'
})

try:
    with urllib.request.urlopen(req, timeout=20) as r:
        print('STATUS', r.status)
        print(r.read().decode()[:1000])
except urllib.error.HTTPError as e:
    print('HTTP_ERROR', e.code)
    try:
        print(e.read().decode())
    except Exception:
        pass
except Exception as e:
    print('ERROR', e)
