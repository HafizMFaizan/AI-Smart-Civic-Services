"""Offline tests for AIAnalyzer. No real API key or network access required."""

import json
from unittest.mock import MagicMock

from app.models.ai_analysis import AIStatus, ComplaintCategory, ComplaintPriority
from app.services.ai_service import MODEL_NAME, AIAnalyzer


def _make_client(response_text: str = None, raise_exception: Exception = None) -> MagicMock:
    client = MagicMock()
    if raise_exception is not None:
        client.models.generate_content.side_effect = raise_exception
    else:
        response = MagicMock()
        response.text = response_text
        client.models.generate_content.return_value = response
    return client


def test_valid_ai_response_returns_success():
    payload = json.dumps(
        {
            "category": "Road",
            "priority": "High",
            "summary": "Pothole needs urgent repair on Main St.",
        }
    )
    service = AIAnalyzer(client=_make_client(response_text=payload))

    result = service.analyze_complaint("Large pothole on Main St causing accidents")

    assert result.category == ComplaintCategory.ROAD
    assert result.priority == ComplaintPriority.HIGH
    assert result.summary == "Pothole needs urgent repair on Main St."
    assert result.model_name == MODEL_NAME
    assert result.ai_status == AIStatus.SUCCESS
    assert result.confidence is None


def test_invalid_category_falls_back():
    payload = json.dumps(
        {"category": "NotACategory", "priority": "High", "summary": "Some summary"}
    )
    service = AIAnalyzer(client=_make_client(response_text=payload))

    result = service.analyze_complaint("Some complaint")

    assert result.ai_status == AIStatus.FAILED
    assert result.category == ComplaintCategory.OTHER
    assert result.priority == ComplaintPriority.MEDIUM
    assert result.confidence is None


def test_invalid_priority_falls_back():
    payload = json.dumps(
        {"category": "Road", "priority": "Severe", "summary": "Some summary"}
    )
    service = AIAnalyzer(client=_make_client(response_text=payload))

    result = service.analyze_complaint("Some complaint")

    assert result.ai_status == AIStatus.FAILED
    assert result.category == ComplaintCategory.OTHER
    assert result.priority == ComplaintPriority.MEDIUM


def test_malformed_json_response_falls_back():
    service = AIAnalyzer(client=_make_client(response_text="not valid json {{{"))

    result = service.analyze_complaint("Some complaint")

    assert result.ai_status == AIStatus.FAILED
    assert result.summary == "AI analysis unavailable. Manual review required."


def test_gemini_api_failure_falls_back():
    service = AIAnalyzer(client=_make_client(raise_exception=ConnectionError("network down")))

    result = service.analyze_complaint("Some complaint")

    assert result.ai_status == AIStatus.FAILED
    assert result.category == ComplaintCategory.OTHER
    assert result.priority == ComplaintPriority.MEDIUM
    assert result.model_name == MODEL_NAME


def test_fallback_result_matches_exact_approved_values():
    service = AIAnalyzer(client=_make_client(raise_exception=RuntimeError("boom")))

    result = service.analyze_complaint("Some complaint")

    assert result.category == ComplaintCategory.OTHER
    assert result.priority == ComplaintPriority.MEDIUM
    assert result.summary == "AI analysis unavailable. Manual review required."
    assert result.model_name == MODEL_NAME
    assert result.ai_status == AIStatus.FAILED
    assert result.confidence is None


def test_confidence_is_none_when_no_defensible_value_exists():
    payload = json.dumps(
        {
            "category": "Water",
            "priority": "Low",
            "summary": "Minor leak reported near residential area.",
        }
    )
    service = AIAnalyzer(client=_make_client(response_text=payload))

    result = service.analyze_complaint("Minor water leak")

    assert result.confidence is None


def test_no_client_configured_falls_back():
    service = AIAnalyzer(client=_make_client(response_text="{}"))
    service._client = None

    result = service.analyze_complaint("Some complaint")

    assert result.ai_status == AIStatus.FAILED
