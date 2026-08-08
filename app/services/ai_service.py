"""AIAnalyzer: the only module allowed to talk to Gemini.

All Gemini-specific code (client construction, prompt/schema, response
parsing) is isolated here. Callers only ever see AIAnalysisResult.
"""

import json
import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.models.ai_analysis import (
    AIAnalysisResult,
    AIStatus,
    ComplaintCategory,
    ComplaintPriority,
)

# Loads GEMINI_API_KEY from a local .env file for development; does not
# override real environment variables and never logs the value.
load_dotenv()

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash"
FALLBACK_SUMMARY = "AI analysis unavailable. Manual review required."
MAX_SUMMARY_LENGTH = 500

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": [category.value for category in ComplaintCategory],
        },
        "priority": {
            "type": "string",
            "enum": [priority.value for priority in ComplaintPriority],
        },
        "summary": {"type": "string"},
    },
    "required": ["category", "priority", "summary"],
}

_SYSTEM_INSTRUCTION = (
    "You are a civic complaint triage assistant. Given a citizen complaint "
    "description, classify its category and priority, and produce a short "
    "actionable summary for the responsible service team. Respond only "
    "with the requested JSON structure."
)


class AIAnalyzerError(Exception):
    """Internal failure while calling or interpreting the Gemini API.

    Always caught inside AIAnalyzer; never escapes to callers.
    """


class AIAnalyzer:
    """Handles all Gemini interactions and returns validated results.

    Gemini does not provide a scientifically calibrated confidence score,
    so `confidence` is never requested from the model or invented here —
    it is always None until a defensible source for it exists.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        client: Optional[genai.Client] = None,
    ) -> None:
        self._model_name = MODEL_NAME
        if client is not None:
            self._client = client
        else:
            resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
            self._client = genai.Client(api_key=resolved_key) if resolved_key else None

    def analyze_complaint(
        self,
        description: str,
        context: Optional[dict[str, Any]] = None,
    ) -> AIAnalysisResult:
        """Classify, prioritize, and summarize a complaint.

        Never raises. Returns a fallback result on any API failure or
        malformed/invalid response.
        """
        if self._client is None:
            logger.warning("AIAnalyzer: no Gemini client configured; using fallback result.")
            return self._fallback_result()

        try:
            raw_response = self._call_gemini(description, context)
        except Exception:
            logger.exception("AIAnalyzer: Gemini API call failed.")
            return self._fallback_result()

        try:
            return self._parse_and_validate(raw_response)
        except AIAnalyzerError:
            logger.exception("AIAnalyzer: Gemini response failed validation.")
            return self._fallback_result()

    def _call_gemini(self, description: str, context: Optional[dict[str, Any]]) -> str:
        prompt = self._build_prompt(description, context)
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
            ),
        )
        text = getattr(response, "text", None)
        if not text:
            raise AIAnalyzerError("Empty response from Gemini.")
        return text

    @staticmethod
    def _build_prompt(description: str, context: Optional[dict[str, Any]]) -> str:
        prompt = f"Complaint description:\n{description.strip()}"
        if context:
            prompt += f"\n\nAdditional context:\n{json.dumps(context)}"
        return prompt

    def _parse_and_validate(self, raw_response: str) -> AIAnalysisResult:
        try:
            data = json.loads(raw_response)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AIAnalyzerError("Malformed JSON from Gemini.") from exc

        if not isinstance(data, dict):
            raise AIAnalyzerError("Gemini response was not a JSON object.")

        category = self._validate_category(data.get("category"))
        priority = self._validate_priority(data.get("priority"))
        summary = self._validate_summary(data.get("summary"))

        return AIAnalysisResult(
            category=category,
            priority=priority,
            summary=summary,
            model_name=self._model_name,
            ai_status=AIStatus.SUCCESS,
            confidence=None,
        )

    @staticmethod
    def _validate_category(value: Any) -> ComplaintCategory:
        try:
            return ComplaintCategory(value)
        except ValueError as exc:
            raise AIAnalyzerError(f"Invalid category: {value!r}") from exc

    @staticmethod
    def _validate_priority(value: Any) -> ComplaintPriority:
        try:
            return ComplaintPriority(value)
        except ValueError as exc:
            raise AIAnalyzerError(f"Invalid priority: {value!r}") from exc

    @staticmethod
    def _validate_summary(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise AIAnalyzerError("Invalid or empty summary.")
        return value.strip()[:MAX_SUMMARY_LENGTH]

    def _fallback_result(self) -> AIAnalysisResult:
        return AIAnalysisResult(
            category=ComplaintCategory.OTHER,
            priority=ComplaintPriority.MEDIUM,
            summary=FALLBACK_SUMMARY,
            model_name=self._model_name,
            ai_status=AIStatus.FAILED,
            confidence=None,
        )
