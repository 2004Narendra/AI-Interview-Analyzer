import requests

url = "http://127.0.0.1:5000/analyze"
answer = "I’m a Python developer with 3 years’ experience building Flask apps and SQL databases."
resp = requests.post(url, data={"answer": answer}, timeout=10)
print('Status:', resp.status_code)
print(resp.text[:1000])
