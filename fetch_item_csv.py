import requests
import sys

timestamp = sys.argv[1] if len(sys.argv) > 1 else ""
if not timestamp:
    print('Usage: fetch_item_csv.py <timestamp>')
    raise SystemExit(1)

url = f"http://127.0.0.1:5000/export_item_csv?timestamp={timestamp}"
resp = requests.get(url, timeout=10)
print('Status', resp.status_code)
print(resp.headers.get('Content-Disposition'))
print(resp.text[:500])
