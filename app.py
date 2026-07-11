from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
from functools import wraps
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, flash, make_response, redirect, render_template, request, send_file, send_from_directory, session, url_for, jsonify
from werkzeug.utils import secure_filename

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
MOCK_MODE = os.getenv("MOCK_MODE", "0") in ("1", "true", "True")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
LOGIN_ENABLED = os.getenv("LOGIN_ENABLED", "0") in ("1", "true", "True")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "password")

if not api_key and not MOCK_MODE:
    raise RuntimeError(
        "OPENROUTER_API_KEY is not set and MOCK_MODE is not enabled. Add it to .env or enable mock mode."
    )

app = Flask(__name__, template_folder="templates")
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "app.db"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openai/gpt-4o"
DEFAULT_MOCK_QUESTIONS = [
    "Tell me about a project that demonstrates your strongest technical skill.",
    "Describe a time you handled conflict or disagreement in a team.",
    "Why should we hire you for this role?",
    "What are your biggest strengths and how do they match this job?",
    "Walk me through a challenging problem you solved recently.",
    "How do you prioritize work when deadlines are tight?",
    "Describe your experience with Python, Flask, or SQL.",
    "How do you approach learning a new technology?",
    "What would you do if you had to explain a technical concept to a non-technical stakeholder?",
    "Tell me about a time you improved a process or system.",
    "What motivates you in your current role?",
    "How do you collaborate with teammates when requirements change?",
]

# Simple coding question bank
DEFAULT_CODING_QUESTIONS = [
    {
        "id": "add_two",
        "title": "Add Two Numbers",
        "description": "Write a Python function `add_two(a, b)` that returns the sum of two numbers.",
        "function": "add_two",
        "tests": [
            {"args": [2, 3], "expected": 5},
            {"args": [-1, 1], "expected": 0},
            {"args": [0, 0], "expected": 0},
        ],
    },
    {
        "id": "factorial",
        "title": "Factorial",
        "description": "Write `fact(n)` returning factorial of n (n>=0).",
        "function": "fact",
        "tests": [
            {"args": [0], "expected": 1},
            {"args": [4], "expected": 24},
        ],
    },
]

@app.context_processor
def inject_datetime():
    return {"datetime": datetime}


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TEXT NOT NULL,
            answer TEXT NOT NULL,
            result TEXT NOT NULL,
            interview_type TEXT NOT NULL DEFAULT 'single',
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.commit()
    conn.close()
    ensure_default_user()
    migrate_analyses_json()


def ensure_default_user() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USER,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)",
            (ADMIN_USER, hash_password(ADMIN_PASS), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    conn.close()


def migrate_analyses_json() -> None:
    """If an `analyses.json` file exists, import any entries into the analyses table.
    Imported entries are assigned to the admin user. This runs once at startup.
    """
    try:
        path = ROOT_DIR / "analyses.json"
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return

    if not isinstance(data, list):
        return

    conn = get_db()
    cur = conn.cursor()
    # get admin user id
    cur.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USER,))
    row = cur.fetchone()
    admin_id = row[0] if row else None

    for entry in data:
        ts = entry.get("timestamp")
        ans = entry.get("answer")
        res = entry.get("result")
        if not ts or not ans:
            continue
        # avoid duplicates by timestamp+answer
        existing = cur.execute("SELECT id FROM analyses WHERE timestamp = ? AND answer = ?", (ts, ans)).fetchone()
        if existing:
            continue
        cur.execute(
            "INSERT INTO analyses (user_id, timestamp, answer, result, interview_type, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (
                admin_id,
                ts,
                ans,
                json.dumps(res, ensure_ascii=False),
                entry.get("interview_type", "single"),
                json.dumps(entry.get("metadata", {}), ensure_ascii=False),
            ),
        )
    conn.commit()
    conn.close()


def hash_password(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if LOGIN_ENABLED and not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)

    return wrapper


def current_user_id() -> int | None:
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return int(user_id)


def current_user_name() -> str:
    if session.get("username"):
        return str(session.get("username"))
    return "Guest"


def analyze_with_openrouter(answer: str) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://your-site-url.example.com",
        "X-Title": "AI Interview Analyser",
    }

    if MOCK_MODE:
        return {
            "score": 7,
            "strengths": ["Relevant experience", "Clear communication"],
            "weaknesses": ["Lacks metrics", "Could show more technical depth"],
            "improved_answer": "(mock) " + answer,
        }

    payload = {
        "model": OPENROUTER_MODEL,
        "max_tokens": 512,
        "temperature": 0.2,
        "messages": [
            {
                "role": "user",
                "content": f"""
You are an expert interviewer and feedback coach.
Task: Evaluate the candidate answer below and respond STRICTLY with a single JSON object matching this schema (no extra text, no markdown):
{{
  "score": 0-10,
  "strengths": ["..."],
  "weaknesses": ["..."],
  "improved_answer": "..."
}}
If you cannot produce valid JSON, return an empty object: {{}}.
Candidate Answer:
{answer}
""",
            }
        ],
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=20)
    response.raise_for_status()
    data = response.json()

    try:
        text = data["choices"][0]["message"]["content"]
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": f"OpenRouter parse error: {exc}", "raw": data}

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"score": 5, "strengths": ["Clear structure"], "weaknesses": ["Needs more detail"], "improved_answer": text}


def save_analysis(answer: str, result: dict[str, Any], interview_type: str = "single", metadata: dict[str, Any] | None = None) -> None:
    conn = get_db()
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "answer": answer,
        "result": result,
        "interview_type": interview_type,
        "metadata": metadata or {},
    }
    conn.execute(
        "INSERT INTO analyses (user_id, timestamp, answer, result, interview_type, metadata) VALUES (?, ?, ?, ?, ?, ?)",
        (
            current_user_id(),
            entry["timestamp"],
            entry["answer"],
            json.dumps(entry["result"], ensure_ascii=False),
            interview_type,
            json.dumps(entry["metadata"], ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


def get_user_analyses(user_id: int | None = None) -> list[dict[str, Any]]:
    conn = get_db()
    user_id = user_id if user_id is not None else current_user_id()
    rows = conn.execute(
        "SELECT * FROM analyses WHERE (? IS NULL OR user_id = ?) ORDER BY id DESC",
        (user_id, user_id),
    ).fetchall()
    conn.close()
    analyses: list[dict[str, Any]] = []
    for row in rows:
        result = json.loads(row["result"]) if row["result"] else {}
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        analyses.append(
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "answer": row["answer"],
                "result": result,
                "interview_type": row["interview_type"],
                "metadata": metadata,
            }
        )
    return analyses


def build_dashboard_stats(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [int(entry.get("result", {}).get("score", 0)) for entry in analyses if isinstance(entry.get("result", {}), dict) and str(entry.get("result", {}).get("score", "")).isdigit()]
    if scores:
        avg_score = round(sum(scores) / len(scores), 1)
        overall_score = round(sum(scores) / len(scores), 1)
    else:
        avg_score = 0.0
        overall_score = 0.0

    metric_names = ["communication", "confidence", "grammar", "technical_knowledge"]
    metric_values: dict[str, list[float]] = {name: [] for name in metric_names}
    for entry in analyses:
        result = entry.get("result") or {}
        if not isinstance(result, dict):
            continue
        for name in metric_names:
            value = result.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metric_values[name].append(float(value))

    performance_breakdown = {}
    for name in metric_names:
        values = metric_values[name]
        if values:
            avg_value = round(sum(values) / len(values), 1)
        else:
            avg_value = round(overall_score, 1) if scores else 0.0
        performance_breakdown[name] = max(0, min(100, int(avg_value * 10)))

    progress_percentage = int(min(100, max(0, round(overall_score * 10))))
    skill_breakdown = [
        {"name": "Communication", "score": performance_breakdown.get("communication", 0)},
        {"name": "Confidence", "score": performance_breakdown.get("confidence", 0)},
        {"name": "Grammar", "score": performance_breakdown.get("grammar", 0)},
        {"name": "Technical", "score": performance_breakdown.get("technical_knowledge", 0)},
    ]
    return {
        "overall_score": overall_score,
        "progress_percentage": progress_percentage,
        "skill_breakdown": skill_breakdown,
        "performance_breakdown": performance_breakdown,
        "total_interviews_completed": len(analyses),
        "average_score": avg_score,
    }


def build_chart_data(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    score_points = []
    weakness_counter: dict[str, int] = {}
    for index, entry in enumerate(reversed(analyses), start=1):
        result = entry.get("result") or {}
        if isinstance(result, dict) and str(result.get("score", "")).isdigit():
            score_points.append({"label": f"#{index}", "score": int(result.get("score", 0))})
        for weakness in result.get("weaknesses", []) if isinstance(result, dict) else []:
            weak_label = str(weakness).strip()
            if weak_label:
                weakness_counter[weak_label] = weakness_counter.get(weak_label, 0) + 1
    weakness_summary = [{"label": label, "count": count} for label, count in sorted(weakness_counter.items(), key=lambda item: item[1], reverse=True)[:6]]
    return {"score_points": score_points, "weakness_summary": weakness_summary}


def enrich_feedback_metrics(answer: str, result: dict[str, Any]) -> dict[str, Any]:
    text = (answer or "").lower()
    strengths = list(result.get("strengths", [])) if isinstance(result, dict) else []
    weaknesses = list(result.get("weaknesses", [])) if isinstance(result, dict) else []
    score = int(result.get("score", 0)) if isinstance(result, dict) and str(result.get("score", "")).isdigit() else 0
    communication = min(10, max(4, score + (1 if len(text.split()) > 15 else 0)))
    confidence = min(10, max(4, score + (1 if any(word in text for word in ["i", "my", "experience", "worked", "developed"]) else 0)))
    technical_knowledge = min(10, max(4, score + (1 if any(word in text for word in ["python", "flask", "sql", "api", "docker", "aws", "git"]) else 0)))
    grammar = min(10, max(4, score + (1 if "." in answer else 0)))
    if not strengths:
        strengths = ["Clear explanation"]
    if not weaknesses:
        weaknesses = ["Needs more specific examples"]
    return {
        "overall_score": round((communication + confidence + technical_knowledge + grammar) / 4, 1),
        "communication": communication,
        "confidence": confidence,
        "technical_knowledge": technical_knowledge,
        "grammar": grammar,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "improved_answer": result.get("improved_answer", "") or "Add a concise example and measurable impact.",
    }


def build_resume_insights(resume_text: str, answer_text: str) -> dict[str, Any]:
    resume_text = (resume_text or "").lower()
    answer_text = (answer_text or "").lower()
    keywords = [word for word in re.findall(r"[a-z0-9#+./-]+", resume_text) if len(word) > 2]
    answer_keywords = [word for word in re.findall(r"[a-z0-9#+./-]+", answer_text) if len(word) > 2]
    matched = sorted({word for word in answer_keywords if word in resume_text} - {"the", "and", "for", "with", "that", "this", "have", "from", "into", "your", "about", "will", "they", "their", "were"})
    missing = sorted({word for word in ["python", "flask", "sql", "git", "docker", "aws", "rest", "api"] if word not in resume_text})
    if not missing:
        missing = ["docker", "aws"]
    resume_score = min(100, max(50, 60 + (len(matched) * 5) - (len(missing) * 3)))
    suggestions = []
    if "flask" not in resume_text and "flask" in answer_text:
        suggestions.append("Mention your Flask project and describe the architecture clearly.")
    if "sql" not in resume_text and "sql" in answer_text:
        suggestions.append("Add a concrete SQL example with a query or schema improvement.")
    if "docker" in missing:
        suggestions.append("Include Docker or containerization experience if available.")
    if not suggestions:
        suggestions.append("Add measurable achievements and quantify the impact of your work.")
    return {
        "resume_score": resume_score,
        "matched_skills": matched[:8],
        "missing_skills": missing[:8],
        "suggestions": suggestions[:4],
    }


def calculate_match_percentage(resume_keywords: list[str], job_keywords: list[str]) -> dict[str, Any]:
    resume = {k.lower().strip() for k in resume_keywords if k and k.strip()}
    job = {k.lower().strip() for k in job_keywords if k and k.strip()}
    matched_keywords = sorted(resume.intersection(job))
    missing_keywords = sorted(job.difference(resume))
    match_percentage = int(round((len(matched_keywords) / len(job)) * 100)) if job else 0
    if match_percentage >= 80:
        summary = "Strong match for the role"
    elif match_percentage >= 50:
        summary = "Moderate match — add a few targeted examples"
    else:
        summary = "Needs more targeted experience and evidence"
    return {
        "match_percentage": match_percentage,
        "summary": summary,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "suggested_improvements": [f"Add evidence for {keyword}" for keyword in missing_keywords[:5]],
    }


def extract_keywords(text: str) -> list[str]:
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    words = [word for word in text.split() if len(word) > 2 and word not in {
        "the", "and", "for", "with", "that", "this", "have", "from", "into", "your", "about", "will", "they", "their", "were",
    }]
    return words


def get_resume_text(uploaded_file) -> str:
    if not uploaded_file or not uploaded_file.filename:
        return ""
    filename = secure_filename(uploaded_file.filename).lower()
    if filename.endswith(".pdf"):
        try:
            from PyPDF2 import PdfReader
        except Exception:
            return ""
        try:
            reader = PdfReader(uploaded_file.stream)
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)
        except Exception:
            return ""
    try:
        return uploaded_file.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def run_coding_solution(code: str) -> tuple[bool, str, Any]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, f"Syntax error: {exc}", None

    allowed_nodes = {ast.FunctionDef, ast.Return, ast.Assign, ast.Expr, ast.Name, ast.Constant, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Load, ast.Call, ast.arguments, ast.arg, ast.If, ast.For, ast.While, ast.Compare, ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq, ast.BoolOp, ast.And, ast.Or, ast.Not, ast.Assert}
    for node in ast.walk(tree):
        if type(node) not in allowed_nodes:
            return False, f"Unsupported code pattern: {type(node).__name__}", None

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(code)
        temp_path = handle.name
    try:
        completed = subprocess.run(
            [sys.executable, temp_path, "2", "3"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(ROOT_DIR),
            env={**os.environ, "PYTHONPATH": str(ROOT_DIR)},
        )
        if completed.returncode != 0:
            return False, completed.stderr or completed.stdout or "Execution failed", None
        return True, completed.stdout.strip(), completed.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "Execution timed out", None
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


def run_coding_tests(code: str, function_name: str, tests: list[dict]) -> tuple[bool, str, dict]:
    """Run provided code against tests safely and return (passed, message, details).
    This function performs AST checks to disallow dangerous constructs and then runs
    the code in a subprocess with a small harness that executes the tests and prints JSON.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, f"Syntax error: {exc}", {}

    banned_nodes = {ast.Import, ast.ImportFrom, ast.Attribute, ast.Subscript, ast.Global, ast.Nonlocal, ast.Lambda, ast.ClassDef, ast.Try, ast.With, ast.AsyncFunctionDef}
    for node in ast.walk(tree):
        if type(node) in banned_nodes:
            return False, f"Disallowed code pattern: {type(node).__name__}", {}
        # ban use of certain names
        if isinstance(node, ast.Name):
            if node.id in {"open", "exec", "eval", "compile", "__import__", "os", "subprocess", "sys", "socket", "shutil", "ctypes", "multiprocessing", "threading"}:
                return False, f"Use of disallowed name: {node.id}", {}
        if isinstance(node, ast.Call):
            # attempt to extract called name
            func = node.func
            fname = None
            if isinstance(func, ast.Name):
                fname = func.id
            elif isinstance(func, ast.Attribute) and isinstance(func.attr, str):
                fname = func.attr
            if fname and fname in {"open", "exec", "eval", "compile", "__import__", "popen", "system"}:
                return False, f"Call to disallowed function: {fname}", {}

    harness = f"\n\nif __name__ == '__main__':\n    import json, traceback\n    tests = {json.dumps(tests)}\n    outputs = []\n    try:\n        for t in tests:\n            args = t.get('args', [])\n            res = {function_name}(*args)\n            outputs.append(res)\n        print(json.dumps({'outputs': outputs}))\n    except Exception as e:\n        print(json.dumps({'error': str(e), 'trace': traceback.format_exc()}))\n        raise SystemExit(1)\n"

    full_code = code + "\n" + harness
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(full_code)
        temp_path = handle.name
    try:
        completed = subprocess.run([
            sys.executable, temp_path
        ], capture_output=True, text=True, timeout=8, cwd=str(ROOT_DIR), env={**os.environ, "PYTHONPATH": str(ROOT_DIR)})
        out = completed.stdout.strip()
        if completed.returncode != 0:
            # try to parse JSON error
            try:
                parsed = json.loads(out or completed.stderr)
                return False, "Runtime error", parsed
            except Exception:
                return False, completed.stderr or out or "Execution failed", {}
        try:
            parsed = json.loads(out)
        except Exception:
            return False, "Failed to parse test output", {"raw": out}
        if 'error' in parsed:
            return False, "Test raised exception", parsed
        outputs = parsed.get('outputs', [])
        # compare outputs to expected
        passed_all = True
        details = {'results': []}
        for idx, case in enumerate(tests):
            expected = case.get('expected')
            actual = outputs[idx] if idx < len(outputs) else None
            ok = actual == expected
            if not ok:
                passed_all = False
            details['results'].append({'args': case.get('args'), 'expected': expected, 'actual': actual, 'passed': ok})
        return passed_all, "Passed" if passed_all else "Some tests failed", details
    except subprocess.TimeoutExpired:
        return False, "Execution timed out", {}
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


def build_report_pdf(result: dict[str, Any], answer: str) -> BytesIO:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"reportlab is not available: {exc}") from exc

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("AI Interview Report")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(40, 760, "AI Interview Report")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(40, 730, f"Score: {result.get('score', 'n/a')}/10")
    strengths = ", ".join(result.get("strengths", [])) or "-"
    weaknesses = ", ".join(result.get("weaknesses", [])) or "-"
    improved_answer = result.get("improved_answer", "") or answer
    text_parts = [
        "Answer:",
        answer[:1200],
        "",
        "Strengths:",
        strengths,
        "",
        "Weaknesses:",
        weaknesses,
        "",
        "Improved Answer:",
        improved_answer[:2000],
    ]
    y = 700
    for part in text_parts:
        if y < 60:
            pdf.showPage()
            y = 760
        pdf.drawString(40, y, part[:120])
        y -= 14
    pdf.save()
    buffer.seek(0)
    return buffer


@app.route('/static/<path:filename>')
def send_static(filename):
    return send_from_directory('static', filename)


@app.route("/")
def home():
    analyses = get_user_analyses()
    dashboard_stats = build_dashboard_stats(analyses)
    return render_template(
        "index.html",
        result=None,
        answer="",
        LOGIN_ENABLED=LOGIN_ENABLED,
        dashboard_stats=dashboard_stats,
        analyses=analyses,
        current_user=current_user_name(),
    )


@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    answer = request.form.get("answer", "").strip()
    if not answer:
        analyses = get_user_analyses()
        dashboard_stats = build_dashboard_stats(analyses)
        return render_template(
            "index.html",
            result="Please enter an answer to analyze.",
            answer="",
            LOGIN_ENABLED=LOGIN_ENABLED,
            dashboard_stats=dashboard_stats,
            analyses=analyses,
            current_user=current_user_name(),
        )

    output = analyze_with_openrouter(answer)
    if isinstance(output, dict):
        enriched = enrich_feedback_metrics(answer, output)
        save_analysis(answer, enriched, interview_type="single")
        session["latest_result"] = enriched
        session["latest_answer"] = answer
        output = enriched
    analyses = get_user_analyses()
    dashboard_stats = build_dashboard_stats(analyses)
    return render_template(
        "index.html",
        result=output,
        answer=answer,
        LOGIN_ENABLED=LOGIN_ENABLED,
        dashboard_stats=dashboard_stats,
        analyses=analyses,
        current_user=current_user_name(),
    )


@app.route("/mock-interview", methods=["GET", "POST"])
@login_required
def mock_interview():
    # The page is now served and the answers are handled via AJAX at /mock-interview/answer
    session.setdefault("mock_state", {"index": 0, "answers": []})
    state = session.get("mock_state")
    index = state.get("index", 0)
    return render_template("mock_interview.html", question=DEFAULT_MOCK_QUESTIONS[index], completed=False, LOGIN_ENABLED=LOGIN_ENABLED)



@app.route("/mock-interview/answer", methods=["POST"])
@login_required
def mock_interview_answer():
    data = request.get_json() or {}
    answer = (data.get("answer") or "").strip()
    if not answer:
        return jsonify({"error": "Answer required"}), 400
    state = session.get("mock_state", {"index": 0, "answers": []})
    state.setdefault("answers", []).append(answer)
    next_index = state.get("index", 0) + 1
    # If finished, generate report
    if next_index >= len(DEFAULT_MOCK_QUESTIONS):
        answers = state.get("answers", [])
        combined_answer = " | ".join(answers)
        raw_report = analyze_with_openrouter(combined_answer)
        if isinstance(raw_report, dict):
            report = enrich_feedback_metrics(combined_answer, raw_report)
        else:
            report = {
                "overall_score": 7.0,
                "communication": 7,
                "confidence": 7,
                "technical_knowledge": 7,
                "grammar": 7,
                "strengths": ["Consistent communication"],
                "weaknesses": ["Could provide more examples"],
                "improved_answer": combined_answer,
            }
        report.setdefault("score", int(round(report.get("overall_score", 0))))
        save_analysis(combined_answer, report, interview_type="mock", metadata={"questions": DEFAULT_MOCK_QUESTIONS})
        session.pop("mock_state", None)
        session["latest_result"] = report
        return jsonify({"completed": True, "report": report})

    # otherwise, advance state and return next question
    state["index"] = next_index
    session["mock_state"] = state
    return jsonify({"completed": False, "question": DEFAULT_MOCK_QUESTIONS[next_index]})



@app.route('/mock-interview/reset', methods=['POST'])
@login_required
def mock_interview_reset():
    session['mock_state'] = {'index': 0, 'answers': []}
    return ('', 204)


@app.route("/resume-analysis", methods=["GET", "POST"])
@login_required
def resume_analysis():
    resume_result = None
    if request.method == "POST":
        uploaded = request.files.get("resume")
        answer = request.form.get("answer", "").strip()
        resume_text = get_resume_text(uploaded)
        keywords = extract_keywords(resume_text)
        answer_keywords = extract_keywords(answer)
        overlap = sorted(set(keywords).intersection(set(answer_keywords)))
        resume_result = build_resume_insights(resume_text, answer)
        resume_result.update({
            "resume_text": resume_text[:4000],
            "matched_skills": resume_result.get("matched_skills", [])[:10],
            "suggested_missing_skills": resume_result.get("missing_skills", [])[:10],
        })
        save_analysis(answer, {"score": 6, "strengths": overlap[:3] or ["Resume reviewed"], "weaknesses": ["Missing targeted keywords"], "improved_answer": "Tailor your answer to the resume skills and add measurable examples."}, interview_type="resume", metadata={"resume_text": resume_text[:500]})
        session["latest_resume_result"] = resume_result
    analyses = get_user_analyses()
    dashboard_stats = build_dashboard_stats(analyses)
    return render_template(
        "index.html",
        result=session.get("latest_result"),
        answer=session.get("latest_answer", ""),
        LOGIN_ENABLED=LOGIN_ENABLED,
        dashboard_stats=dashboard_stats,
        analyses=analyses,
        current_user=current_user_name(),
        resume_result=resume_result,
    )


@app.route("/job-match", methods=["GET", "POST"])
@login_required
def job_match():
    match_result = None
    if request.method == "POST":
        resume_text = request.form.get("resume_text", "")
        job_description = request.form.get("job_description", "")
        resume_keywords = extract_keywords(resume_text)
        job_keywords = extract_keywords(job_description)
        match_result = calculate_match_percentage(resume_keywords, job_keywords)
        match_result["missing_keywords"] = match_result.get("missing_keywords", [])[:10]
        match_result["suggested_improvements"] = [
            f"Add evidence for {skill}" for skill in match_result.get("missing_keywords", [])[:5]
        ]
        session["latest_job_match"] = match_result
    analyses = get_user_analyses()
    dashboard_stats = build_dashboard_stats(analyses)
    return render_template(
        "index.html",
        result=session.get("latest_result"),
        answer=session.get("latest_answer", ""),
        LOGIN_ENABLED=LOGIN_ENABLED,
        dashboard_stats=dashboard_stats,
        analyses=analyses,
        current_user=current_user_name(),
        match_result=match_result,
    )


@app.route("/coding-interview", methods=["GET", "POST"])
@login_required
def coding_interview():
    coding_result = None
    selected_q = None
    if request.method == "POST":
        code = request.form.get("code", "")
        qid = request.form.get("question_id")
        selected_q = next((q for q in DEFAULT_CODING_QUESTIONS if q["id"] == qid), None)
        if code.strip() and selected_q is not None:
            passed, msg, details = run_coding_tests(code, selected_q["function"], selected_q["tests"])
            coding_result = {
                "question": selected_q["description"],
                "code": code,
                "passed": passed,
                "feedback": msg,
                "details": details,
            }
            session["latest_coding_result"] = coding_result
    analyses = get_user_analyses()
    dashboard_stats = build_dashboard_stats(analyses)
    return render_template(
        "index.html",
        result=session.get("latest_result"),
        answer=session.get("latest_answer", ""),
        LOGIN_ENABLED=LOGIN_ENABLED,
        dashboard_stats=dashboard_stats,
        analyses=analyses,
        current_user=current_user_name(),
        coding_result=coding_result,
        coding_questions=DEFAULT_CODING_QUESTIONS,
    )


@app.route("/history")
@login_required
def history():
    analyses = get_user_analyses()
    chart_data = build_chart_data(analyses)
    return render_template(
        "history.html",
        analyses=analyses,
        LOGIN_ENABLED=LOGIN_ENABLED,
        current_user=current_user_name(),
        chart_data=chart_data,
    )



@app.route("/api/dashboard-data")
@login_required
def api_dashboard_data():
    analyses = get_user_analyses()
    dashboard_stats = build_dashboard_stats(analyses)
    chart_data = build_chart_data(analyses)
    return jsonify({
        "dashboard_stats": dashboard_stats,
        "chart_data": chart_data,
    })


@app.route("/export")
@login_required
def export_analyses():
    analyses = get_user_analyses()
    payload = json.dumps(analyses, ensure_ascii=False, indent=2)
    resp = make_response(payload)
    resp.headers["Content-Type"] = "application/json"
    resp.headers["Content-Disposition"] = "attachment; filename=analyses.json"
    return resp


@app.route("/export_csv")
@login_required
def export_csv():
    analyses = get_user_analyses()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "answer", "score", "strengths", "weaknesses", "improved_answer"])
    for item in analyses:
        result = item.get("result") or {}
        writer.writerow([
            item.get("timestamp", ""),
            item.get("answer", ""),
            result.get("score", ""),
            "; ".join(result.get("strengths", [])),
            "; ".join(result.get("weaknesses", [])),
            result.get("improved_answer", ""),
        ])
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=analyses.csv"
    return resp


@app.route("/history/delete", methods=["POST"])
@login_required
def delete_history_item():
    timestamp = request.form.get("timestamp")
    if not timestamp:
        return redirect(url_for("history"))
    conn = get_db()
    conn.execute("DELETE FROM analyses WHERE timestamp = ? AND (? IS NULL OR user_id = ?)", (timestamp, current_user_id(), current_user_id()))
    conn.commit()
    conn.close()
    return redirect(url_for("history"))


@app.route("/export_item_csv")
@login_required
def export_item_csv():
    timestamp = request.args.get("timestamp")
    if not timestamp:
        return redirect(url_for("history"))
    analyses = get_user_analyses()
    item = next((entry for entry in analyses if entry.get("timestamp") == timestamp), None)
    if not item:
        return redirect(url_for("history"))
    result = item.get("result") or {}
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "answer", "score", "strengths", "weaknesses", "improved_answer"])
    writer.writerow([
        item.get("timestamp", ""),
        item.get("answer", ""),
        result.get("score", ""),
        "; ".join(result.get("strengths", [])),
        "; ".join(result.get("weaknesses", [])),
        result.get("improved_answer", ""),
    ])
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="analysis_{timestamp}.csv"'
    return resp


@app.route("/history/clear", methods=["POST"])
@login_required
def clear_history():
    conn = get_db()
    conn.execute("DELETE FROM analyses WHERE (? IS NULL OR user_id = ?)", (current_user_id(), current_user_id()))
    conn.commit()
    conn.close()
    return redirect(url_for("history"))


@app.route("/generate-report")
@login_required
def generate_report():
    timestamp = request.args.get("timestamp")
    analyses = get_user_analyses()
    entry = next((item for item in analyses if item.get("timestamp") == timestamp), None)
    if not entry:
        entry = {"result": session.get("latest_result", {}), "answer": session.get("latest_answer", "")}
    try:
        pdf_buffer = build_report_pdf(entry.get("result") or {}, entry.get("answer") or "")
    except Exception as exc:
        flash(str(exc), "danger")
        return redirect(url_for("history"))
    return send_file(pdf_buffer, as_attachment=True, download_name="interview_report.pdf", mimetype="application/pdf")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        mode = request.form.get("mode", "login")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if mode == "register":
            if not username or not password:
                flash("Username and password are required.", "warning")
            elif user is not None:
                flash("That username already exists.", "danger")
            else:
                conn = get_db()
                conn.execute(
                    "INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)",
                    (username, hash_password(password), datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                conn.close()
                flash("Account created. Please log in.", "success")
                return redirect(url_for("login"))
        elif user is not None and user["password"] == hash_password(password):
            session["logged_in"] = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Logged in successfully", "success")
            next_url = request.args.get("next") or url_for("home")
            return redirect(next_url)
        else:
            flash("Invalid credentials", "danger")
    return render_template("login.html", LOGIN_ENABLED=LOGIN_ENABLED)


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    session.pop("user_id", None)
    session.pop("username", None)
    flash("Logged out", "info")
    return redirect(url_for("home"))


init_db()


if __name__ == "__main__":
    app.run(debug=True)