"""DocsHound Agent Engine for Google Cloud Vertex AI Agent Runtime."""

import asyncio
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class DocsHoundAgentEngine:
    """Vertex AI Reasoning Engine / Agent Engine wrapper for DocsHound."""

    def __init__(
        self,
        vertex_project: str = "agent-clinic-e3-dev",
        vertex_location: str = "global",
        primary_model: str = "google/gemini-3.7-flash",
        fallback_model: str = "google/gemini-3.5-flash",
    ) -> None:
        self.vertex_project = vertex_project
        self.vertex_location = vertex_location
        self.primary_model = primary_model
        self.fallback_model = fallback_model

    def set_up(self) -> None:
        """Initialize runtime environment when deployed on Agent Runtime."""
        os.environ["VERTEX_PROJECT"] = self.vertex_project
        os.environ["VERTEX_LOCATION"] = self.vertex_location
        os.environ["VERTEX_PRIMARY_MODEL"] = self.primary_model
        os.environ["VERTEX_FALLBACK_MODEL"] = self.fallback_model

        try:
            from app.tracing import setup_tracing

            setup_tracing()
        except Exception as exc:
            logger.warning("Tracing initialization note: %s", exc)

    def query(
        self,
        repo: str,
        docs_url: str | None = None,
        github_token: str | None = None,
        include_documentation_activity: bool = False,
        limit: int = 50,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute a DocsHound analysis run on the LangGraph workflow."""
        if github_token:
            os.environ["GITHUB_TOKEN"] = github_token

        os.environ["VERTEX_PROJECT"] = self.vertex_project
        os.environ["VERTEX_LOCATION"] = self.vertex_location
        os.environ["VERTEX_PRIMARY_MODEL"] = self.primary_model
        os.environ["VERTEX_FALLBACK_MODEL"] = self.fallback_model

        from app.langgraph_agent import graph

        run_id = f"runtime-{uuid.uuid4().hex[:12]}"
        initial_state = {
            "run_id": run_id,
            "repo": repo,
            "docs_url": docs_url,
            "documentation_source": None,
            "include_documentation_activity": include_documentation_activity,
            "limit": limit,
            "dry_run": dry_run,
            "issues": [],
            "pull_requests": [],
            "clusters": [],
            "docs_sources": [],
            "docs_candidates_inspected": 0,
            "documentation_issues_scraped": 0,
            "documentation_pull_requests_scraped": 0,
            "errors": [],
            "warnings": [],
            "decisions": [],
            "researched": False,
            "analyzed": False,
            "docs_searched": False,
            "drafted": False,
            "stored": False,
        }

        async def _run() -> dict[str, Any]:
            return await graph.ainvoke(initial_state)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, _run())
                result = future.result()
        else:
            result = asyncio.run(_run())

        return {
            "run_id": run_id,
            "repo": repo,
            "status": "completed_with_errors" if result.get("errors") else "completed",
            "clusters": result.get("clusters", []),
            "docs_sources": result.get("docs_sources", []),
            "issues_count": len(result.get("issues", [])),
            "pull_requests_count": len(result.get("pull_requests", [])),
            "docs_candidates_inspected": result.get("docs_candidates_inspected", 0),
            "warnings": result.get("warnings", []),
            "errors": result.get("errors", []),
        }

