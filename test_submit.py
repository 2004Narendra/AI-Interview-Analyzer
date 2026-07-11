import json
from app import analyze_with_openrouter

answer = """
I’m a Python developer with 3 years’ experience building Flask apps and SQL databases. I successfully improved performance on a data pipeline by 20%, which involved optimizing queries and refactoring code. I thrive in cross-functional teams, collaborating effectively with designers, product managers, and other developers to deliver high-quality software solutions.
"""

res = analyze_with_openrouter(answer)

if isinstance(res, dict):
    print(json.dumps(res, indent=2))
else:
    print(res)
