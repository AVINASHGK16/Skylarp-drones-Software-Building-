"""
BI Agent Service for Monday.com BI Agent.
Interacts with Google Gemini API using google-genai SDK to answer executive
business questions and generate leadership reports based strictly on
pre-computed business metrics from analytics_engine.py.

This module NEVER calculates business KPIs directly.
"""

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from google import genai
import pandas as pd

# Load environment variables
load_dotenv()

# Logger configuration
logger = logging.getLogger(__name__)

# Import generate_dashboard_metrics without calculation duplication
try:
    from services.analytics_engine import generate_dashboard_metrics
except ImportError:
    from backend.services.analytics_engine import generate_dashboard_metrics


class BIAgent:
    """
    AI Business Intelligence Agent advising executives and founders.
    Uses Google Gemini models to interpret analytics_engine KPIs.
    """

    DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """
        Initialize the BI Agent with Google GenAI SDK.

        Args:
            api_key: Optional Gemini API key. If not provided, it is loaded
                     from the GEMINI_API_KEY environment variable.
            model: Optional Gemini model identifier. If not provided, it is dynamically
                   resolved from available API models or environment configuration.

        Raises:
            ValueError: If GEMINI_API_KEY is not set or provided.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set and no API key was provided."
            )

        self.client = genai.Client(api_key=self.api_key)
        self.model = self._resolve_model(model)
        logger.info("BIAgent initialized successfully with resolved model '%s'.", self.model)

    def _resolve_model(self, requested_model: str | None = None) -> str:
        """
        Dynamically discover and select a valid, supported Gemini model
        for generateContent from the client API list if requested_model is not explicitly set.
        """
        if requested_model and requested_model.strip():
            return requested_model.strip()

        env_model = os.getenv("GEMINI_MODEL")
        if env_model and env_model.strip():
            return env_model.strip()

        # Try dynamically listing available models from Google GenAI API for this API key
        try:
            available_models = []
            models_pager = self.client.models.list()
            for m in models_pager:
                m_name = getattr(m, "name", "") or ""
                actions = (
                    getattr(m, "supported_actions", [])
                    or getattr(m, "supported_generation_methods", [])
                    or []
                )

                clean_name = m_name.split("/")[-1] if "/" in m_name else m_name
                supports_generate = False
                if not actions:
                    supports_generate = "gemini" in clean_name.lower()
                else:
                    supports_generate = any(
                        "generatecontent" in str(act).lower() for act in actions
                    )

                if supports_generate and "gemini" in clean_name.lower():
                    available_models.append(clean_name)

            if available_models:
                logger.info("Discovered available Gemini models for API key: %s", available_models)
                for preferred in [
                    "gemini-2.0-flash",
                    "gemini-1.5-flash",
                    "gemini-1.5-pro",
                    "gemini-2.0-flash-exp",
                    "gemini-pro",
                ]:
                    for model_candidate in available_models:
                        if preferred in model_candidate.lower():
                            logger.info("Dynamically selected preferred Gemini model: '%s'", model_candidate)
                            return model_candidate

                selected = available_models[0]
                logger.info("Dynamically selected first available Gemini model: '%s'", selected)
                return selected

        except Exception as e:
            logger.warning(
                "Failed to list models dynamically from Gemini API (%s). Defaulting to candidate fallback.", e
            )

        return self.DEFAULT_MODEL

    def _generate_content_with_fallback(self, prompt: str) -> Any:
        """
        Attempt to generate content using the resolved model.
        If a 404 NOT_FOUND error occurs for a specific model alias, try fallback candidates dynamically.
        """
        candidate_models = [self.model]
        for fallback in [
            "gemini-2.0-flash",
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-pro",
        ]:
            if fallback not in candidate_models and fallback.lower() != self.model.lower():
                candidate_models.append(fallback)

        last_error = None
        for model_to_try in candidate_models:
            try:
                logger.info("Calling generate_content with Gemini model: '%s'", model_to_try)
                response = self.client.models.generate_content(
                    model=model_to_try,
                    contents=prompt,
                )
                if model_to_try != self.model:
                    logger.info(
                        "Updated active BIAgent model from '%s' to working model '%s'",
                        self.model,
                        model_to_try,
                    )
                    self.model = model_to_try
                return response
            except Exception as e:
                err_str = str(e)
                last_error = e
                if "404" in err_str or "NOT_FOUND" in err_str or "not found" in err_str.lower():
                    logger.warning(
                        "Gemini model '%s' returned 404/NOT_FOUND. Retrying with next candidate...",
                        model_to_try,
                    )
                    continue
                else:
                    raise e

        if last_error:
            raise last_error

    def _build_context(
        self,
        dashboard_metrics: dict[str, Any],
        quality_report: dict[str, Any] | None = None,
    ) -> str:
        """
        Build a structured, readable context string from pre-computed metrics
        and quality caveats for the LLM prompt.

        Args:
            dashboard_metrics: Dictionary generated by analytics_engine.generate_dashboard_metrics().
            quality_report: Optional data quality report dictionary.

        Returns:
            str: Formatted context text string.
        """
        caveats = []
        if quality_report and isinstance(quality_report, dict):
            caveats = quality_report.get("caveats", [])

        context_blocks = [
            "=== BUSINESS ANALYTICS METRICS CONTEXT ===",
            f"Pipeline Summary:\n{json.dumps(dashboard_metrics.get('pipeline_summary', {}), indent=2)}",
            f"Revenue by Sector:\n{json.dumps(dashboard_metrics.get('revenue_by_sector', {}), indent=2)}",
            f"Revenue by Stage:\n{json.dumps(dashboard_metrics.get('revenue_by_stage', {}), indent=2)}",
            f"Monthly Pipeline:\n{json.dumps(dashboard_metrics.get('monthly_pipeline', {}), indent=2)}",
            f"Work Order Summary:\n{json.dumps(dashboard_metrics.get('work_order_summary', {}), indent=2)}",
            f"Billing Summary:\n{json.dumps(dashboard_metrics.get('billing_summary', {}), indent=2)}",
            f"Top Customers:\n{json.dumps(dashboard_metrics.get('top_customers', []), indent=2)}",
            f"Execution Metrics:\n{json.dumps(dashboard_metrics.get('execution_metrics', {}), indent=2)}",
            f"Data Quality Caveats:\n{json.dumps(caveats, indent=2)}",
        ]

        return "\n\n".join(context_blocks)

    def _extract_response_text(self, response: Any) -> str | None:
        """
        Safely extract text content from a Gemini API response.
        Handles safety filter blocks, empty text, or partial response objects.

        Args:
            response: Response object returned by genai.Client.models.generate_content().

        Returns:
            str | None: Cleaned text string or None if unavailable.
        """
        if not response:
            return None

        # 1. Attempt standard property access
        try:
            text = response.text
            if text and text.strip():
                return text.strip()
        except Exception as e:
            logger.warning("Standard response.text property access threw warning/error: %s", e)

        # 2. Inspect candidate parts directly if response.text raised exception or was empty
        try:
            candidates = getattr(response, "candidates", None)
            if candidates and len(candidates) > 0:
                first_candidate = candidates[0]
                finish_reason = getattr(first_candidate, "finish_reason", None)
                if finish_reason:
                    logger.warning("Gemini candidate finish_reason: %s", finish_reason)

                content = getattr(first_candidate, "content", None)
                if content and getattr(content, "parts", None):
                    parts = content.parts
                    extracted = "".join(
                        getattr(p, "text", "") for p in parts if getattr(p, "text", None)
                    ).strip()
                    if extracted:
                        return extracted
        except Exception as inner_e:
            logger.warning("Error while inspecting candidate parts: %s", inner_e)

        return None

    def answer_question(
        self,
        question: str,
        deals_df: pd.DataFrame,
        wo_df: pd.DataFrame,
        quality_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Answer strategic business question from executive users based on metrics.

        Args:
            question: The user's executive question.
            deals_df: Cleaned Deals DataFrame.
            wo_df: Cleaned Work Orders DataFrame.
            quality_report: Optional quality report dictionary.

        Returns:
            dict: Structured response containing answer text, dashboard metrics, and caveats.
        """
        logger.info("BIAgent processing user question: '%s'", question)

        # 1. Fetch pre-computed metrics from analytics_engine (NEVER recalculate here)
        dashboard_metrics = generate_dashboard_metrics(deals_df, wo_df)
        notes = quality_report.get("caveats", []) if quality_report else []

        # 2. Construct LLM context prompt
        context_str = self._build_context(dashboard_metrics, quality_report)

        system_prompt = (
            "You are a senior Business Intelligence analyst advising founders and executives. "
            "Your objective is to answer strategic business questions accurately using ONLY the "
            "provided pre-computed analytics context.\n\n"
            "Guidelines:\n"
            "1. Explain strategic reasoning clearly and concisely.\n"
            "2. Highlight trends, growth drivers, operational risks, and key commercial opportunities.\n"
            "3. Explicitly reference specific numeric metrics from the context.\n"
            "4. Mention relevant data quality caveats when pertinent to the question.\n"
            "5. NEVER invent, fabricate, or extrapolate numbers not explicitly present in the metrics.\n"
            "6. If the user's question is ambiguous, provide a high-level answer first and then ask ONE concise clarifying question."
        )

        full_prompt = (
            f"{system_prompt}\n\n"
            f"EXECUTIVE QUESTION:\n{question}\n\n"
            f"ANALYTICS METRICS CONTEXT:\n{context_str}\n\n"
            "Please provide your professional analysis:"
        )

        # 3. Request content generation from Google Gemini API with robust model fallback
        answer_text = None
        try:
            response = self._generate_content_with_fallback(full_prompt)
            answer_text = self._extract_response_text(response)
            if answer_text:
                logger.info("Successfully generated Gemini AI response for user question.")
            else:
                logger.warning("Gemini API returned an empty or safety-filtered response.")
                answer_text = (
                    "The AI response was unavailable or blocked by safety filters. "
                    "Please rephrase your question or consult the executive dashboard metrics directly."
                )

        except Exception as e:
            logger.exception("Error calling Gemini API in BIAgent.answer_question: %s", e)
            answer_text = (
                f"AI Service Error: Unable to complete request with Gemini API ({e}). "
                "Please verify system credentials and network connectivity."
            )

        return {
            "answer": answer_text,
            "dashboard_metrics": dashboard_metrics,
            "data_quality_notes": notes,
        }

    def generate_leadership_report(
        self,
        deals_df: pd.DataFrame,
        wo_df: pd.DataFrame,
        quality_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generate a comprehensive executive leadership report formatted in Markdown.

        Args:
            deals_df: Cleaned Deals DataFrame.
            wo_df: Cleaned Work Orders DataFrame.
            quality_report: Optional quality report dictionary.

        Returns:
            dict: Dictionary containing Markdown report text and timestamp.
        """
        logger.info("BIAgent generating executive leadership report.")

        # 1. Fetch pre-computed metrics
        dashboard_metrics = generate_dashboard_metrics(deals_df, wo_df)
        context_str = self._build_context(dashboard_metrics, quality_report)

        system_prompt = (
            "You are a Chief Business Officer preparing an executive leadership report for "
            "founders and board members based on company metrics.\n\n"
            "CRITICAL INSTRUCTION:\n"
            "Your response MUST be formatted in Markdown and MUST contain the following EXACT header sections:\n\n"
            "# Executive Summary\n\n"
            "# Sales Pipeline Health\n\n"
            "# Revenue Insights\n\n"
            "# Operational Performance\n\n"
            "# Billing Overview\n\n"
            "# Key Risks\n\n"
            "# Recommended Actions\n\n"
            "# Data Quality Notes\n\n"
            "Guidelines:\n"
            "- Ground every insight strictly in the provided numeric metrics.\n"
            "- Make recommendations practical, high-impact, and directly tied to metrics.\n"
            "- Do not fabricate numbers or speculate beyond the data."
        )

        full_prompt = (
            f"{system_prompt}\n\n"
            f"Generate a comprehensive executive leadership report based on this metrics context:\n\n"
            f"{context_str}"
        )

        report_text = None
        try:
            response = self._generate_content_with_fallback(full_prompt)
            report_text = self._extract_response_text(response)
            if report_text:
                logger.info("Successfully generated executive leadership report with Gemini API.")
            else:
                logger.warning("Gemini API returned an empty or safety-filtered report response.")
                report_text = (
                    "# Executive Leadership Report\n\n"
                    "*The report generation response was empty or blocked by safety filters. "
                    "Please try again or refer to the pre-computed metrics dashboard.*"
                )

        except Exception as e:
            logger.exception("Error generating leadership report with Gemini API: %s", e)
            report_text = (
                "# Executive Report Generation Error\n\n"
                f"Unable to generate report due to Gemini API Error ({e})."
            )

        iso_now = datetime.now(timezone.utc).isoformat()
        return {
            "report": report_text,
            "generated_at": iso_now,
        }
