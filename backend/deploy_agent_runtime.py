"""Deploy and manage DocsHound LangGraph Agent on Google Cloud Vertex AI Agent Runtime."""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load local env if available
load_dotenv(Path(__file__).parent / ".env")

import vertexai
from vertexai.preview import reasoning_engines
from app.agent_engine import DocsHoundAgentEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("docshound-deploy")

PROJECT_ID = os.getenv("VERTEX_PROJECT", "agent-clinic-e3-dev")
LOCATION = os.getenv("VERTEX_DEPLOY_LOCATION", "us-central1")
STAGING_BUCKET = os.getenv(
    "VERTEX_STAGING_BUCKET",
    f"gs://{PROJECT_ID}-agent-runtime-staging",
)

DEFAULT_REQUIREMENTS = [
    "google-cloud-aiplatform>=1.164.0",
    "langgraph>=1.2.11,<2",
    "openai>=3.1.0,<4",
    "pydantic>=2.13.4,<3",
    "pydantic-settings>=2.15.0,<3",
    "google-auth>=2.0,<3",
    "httpx>=0.28.1,<1",
    "httpx2>=2.10.0,<3",
    "openinference-instrumentation-langchain>=0.1.70,<0.2",
    "openinference-instrumentation-openai>=0.1.54,<0.2",
    "openinference-semantic-conventions>=0.1.32,<0.2",
    "opentelemetry-api>=1.44.0,<2",
    "opentelemetry-exporter-otlp-proto-http>=1.44.0,<2",
    "opentelemetry-sdk>=1.44.0,<2",
    "python-dotenv>=1.2.2,<2",
]


def _build_and_init() -> tuple[Path, DocsHoundAgentEngine]:
    backend_dir = Path(__file__).resolve().parent

    logger.info("Building docshound-backend package...")
    subprocess.run(["uv", "build"], cwd=backend_dir, check=True)

    logger.info(
        "Initializing Vertex AI with project=%s, location=%s, staging_bucket=%s",
        PROJECT_ID,
        LOCATION,
        STAGING_BUCKET,
    )
    vertexai.init(
        project=PROJECT_ID,
        location=LOCATION,
        staging_bucket=STAGING_BUCKET,
    )

    local_agent = DocsHoundAgentEngine(
        vertex_project=PROJECT_ID,
        vertex_location="global",
        primary_model=os.getenv("VERTEX_PRIMARY_MODEL", "google/gemini-3.7-flash"),
        fallback_model=os.getenv("VERTEX_FALLBACK_MODEL", "google/gemini-3.5-flash"),
    )
    return backend_dir, local_agent


def deploy(
    display_name: str = "docshound-langgraph-agent",
    force_new: bool = False,
) -> reasoning_engines.ReasoningEngine:
    backend_dir, local_agent = _build_and_init()

    # Check for existing reasoning engine with the same display name to update/revise
    if not force_new:
        engines = list(reasoning_engines.ReasoningEngine.list())
        for engine in engines:
            if engine.display_name == display_name:
                logger.info(
                    "Found existing Reasoning Engine %s (%s). Minting new revision...",
                    engine.resource_name,
                    display_name,
                )
                return update(engine.resource_name)

    os.chdir(backend_dir)
    logger.info("Deploying new DocsHound Reasoning Engine to Vertex AI Agent Runtime...")
    remote_agent = reasoning_engines.ReasoningEngine.create(
        local_agent,
        requirements=DEFAULT_REQUIREMENTS,
        display_name=display_name,
        description="DocsHound LangGraph Documentation Gap Agent",
        extra_packages=["app"],
    )

    logger.info("Successfully deployed DocsHound to Agent Runtime!")
    logger.info("Remote Resource Name: %s", remote_agent.resource_name)
    return remote_agent


def update(resource_name: str) -> reasoning_engines.ReasoningEngine:
    backend_dir, local_agent = _build_and_init()
    os.chdir(backend_dir)

    logger.info("Updating Reasoning Engine revision for %s...", resource_name)
    remote_agent = reasoning_engines.ReasoningEngine(resource_name)
    updated_agent = remote_agent.update(
        reasoning_engine=local_agent,
        requirements=DEFAULT_REQUIREMENTS,
        extra_packages=["app"],
    )
    logger.info("Successfully updated Reasoning Engine revision!")
    logger.info("Resource Name: %s", updated_agent.resource_name)
    return updated_agent


def delete_engine(resource_name: str) -> None:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    logger.info("Deleting Reasoning Engine: %s...", resource_name)
    engine = reasoning_engines.ReasoningEngine(resource_name)
    engine.delete()
    logger.info("Successfully deleted Reasoning Engine %s", resource_name)


def list_deployed() -> None:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    logger.info("Listing deployed Reasoning Engines in %s/%s:", PROJECT_ID, LOCATION)
    engines = reasoning_engines.ReasoningEngine.list()
    for engine in engines:
        logger.info(
            " - %s (display_name: %s, created: %s)",
            engine.resource_name,
            engine.display_name,
            engine.create_time,
        )


def query_deployed(resource_name: str, repo: str = "google/adk-python") -> None:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    logger.info("Loading deployed agent %s...", resource_name)
    remote_agent = reasoning_engines.ReasoningEngine(resource_name)
    github_token = os.getenv("GITHUB_TOKEN")
    logger.info("Querying deployed agent with repo=%s...", repo)
    response = remote_agent.query(repo=repo, github_token=github_token)
    logger.info("Remote agent response:\n%s", response)


def main() -> int:
    parser = argparse.ArgumentParser(description="DocsHound Agent Runtime Deployment Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    deploy_parser = subparsers.add_parser(
        "deploy", help="Deploy or update DocsHound on Vertex AI Agent Runtime"
    )
    deploy_parser.add_argument(
        "--display-name",
        default="docshound-langgraph-agent",
        help="Display name for deployed agent",
    )
    deploy_parser.add_argument(
        "--force-new",
        action="store_true",
        help="Force creation of a new Reasoning Engine instead of updating existing",
    )

    update_parser = subparsers.add_parser(
        "update", help="Update an existing Reasoning Engine revision"
    )
    update_parser.add_argument(
        "resource_name", help="Resource name of the Reasoning Engine to update"
    )

    delete_parser = subparsers.add_parser("delete", help="Delete a deployed Reasoning Engine")
    delete_parser.add_argument(
        "resource_name", help="Resource name of the Reasoning Engine to delete"
    )

    list_parser = subparsers.add_parser("list", help="List deployed Reasoning Engines")

    query_parser = subparsers.add_parser("query", help="Query a deployed agent")
    query_parser.add_argument(
        "resource_name", help="Resource name of the deployed Reasoning Engine"
    )
    query_parser.add_argument(
        "--repo", default="google/adk-python", help="Target repository"
    )

    args = parser.parse_args()

    if args.command == "deploy":
        deploy(args.display_name, args.force_new)
    elif args.command == "update":
        update(args.resource_name)
    elif args.command == "delete":
        delete_engine(args.resource_name)
    elif args.command == "list":
        list_deployed()
    elif args.command == "query":
        query_deployed(args.resource_name, args.repo)

    return 0


if __name__ == "__main__":
    sys.exit(main())
