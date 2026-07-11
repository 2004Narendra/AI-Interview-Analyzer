import importlib
import os

os.environ.setdefault("MOCK_MODE", "1")
app_module = importlib.import_module("app")


def test_calculate_match_percentage():
    result = app_module.calculate_match_percentage(["python", "flask", "sql"], ["python", "sql", "docker"])
    assert result["match_percentage"] == 67
    assert "python" in result["matched_keywords"]
    assert "flask" not in result["matched_keywords"]


def test_build_dashboard_stats():
    analyses = [
        {"result": {"score": 7}},
        {"result": {"score": 9}},
        {"result": {"score": 8}},
    ]
    stats = app_module.build_dashboard_stats(analyses)
    assert stats["total_interviews_completed"] == 3
    assert stats["average_score"] == 8.0
    assert stats["overall_score"] == 8.0
    assert stats["progress_percentage"] == 80
    assert stats["skill_breakdown"]


def test_build_dashboard_stats_with_detail_metrics():
    analyses = [{"result": {"score": 8, "communication": 8, "confidence": 7, "grammar": 9, "technical_knowledge": 8}}]
    stats = app_module.build_dashboard_stats(analyses)
    assert stats["performance_breakdown"]["communication"] == 80
    assert stats["performance_breakdown"]["technical_knowledge"] == 80


def test_enrich_feedback_metrics():
    raw = {"score": 8, "strengths": ["clear explanation"], "weaknesses": ["needs confidence"], "improved_answer": "I am confident"}
    enriched = app_module.enrich_feedback_metrics("I have worked with Python and Flask for three years.", raw)
    assert enriched["overall_score"] >= 7
    assert enriched["communication"] >= 0
    assert enriched["technical_knowledge"] >= 0
    assert enriched["strengths"]
    assert enriched["weaknesses"]


def test_build_resume_insights():
    insights = app_module.build_resume_insights(
        "Python Flask SQL Git Docker AWS REST API",
        "I have experience with Python, Flask, and SQL. I worked on REST APIs and Git."
    )
    assert insights["resume_score"] >= 50
    assert "python" in insights["matched_skills"]
    assert "docker" in insights["missing_skills"]
    assert insights["suggestions"]
