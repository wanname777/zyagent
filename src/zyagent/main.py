from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from zyagent.adapters.models.openai import OpenAICompatibleModelClient
from zyagent.adapters.stores.jsonl import JsonlSessionStore
from zyagent.adapters.tools.bash import BashTool
from zyagent.adapters.tools.files import ReadFileTool, WriteFileTool
from zyagent.application.ports import Effort, ModelSettings
from zyagent.application.service import AgentService
from zyagent.domain.roles import Assistant, ToolCallReviewer


@dataclass(frozen=True)
class AppConfig:
    api_key: str
    base_url: str
    data_path: Path
    workspace: Path
    assistant_model: str
    reviewer_model: str
    compression_model: str
    max_iterations: int = 8
    auto_compress_after: int = 24
    keep_recent_after_compression: int = 12


def build_service(config: AppConfig) -> AgentService:
    model_client = OpenAICompatibleModelClient(
        api_key=config.api_key,
        base_url=config.base_url,
    )
    tools = (
        BashTool(config.workspace),
        ReadFileTool(config.workspace),
        WriteFileTool(config.workspace),
    )
    return AgentService(
        model_client=model_client,
        session_store=JsonlSessionStore(config.data_path),
        assistant=Assistant(
            instruction=(
                "You are zyagent, a careful workspace assistant. "
                "Answer directly, use tools only when they materially help, and never "
                "claim a tool action succeeded without its result. Keep changes scoped "
                "to the user's request."
            ),
            tools=tools,
        ),
        reviewer=ToolCallReviewer(
            instruction=(
                "Review the proposed tool call against the user's request. Reject calls "
                "that are unrelated, access secrets, escape the workspace, perform "
                "destructive actions without explicit authorization, or use surprising "
                "amounts of data. Allow proportionate workspace reads and writes."
            )
        ),
        assistant_settings=ModelSettings(config.assistant_model, Effort.MEDIUM),
        reviewer_settings=ModelSettings(config.reviewer_model, Effort.LOW),
        compression_settings=ModelSettings(config.compression_model, Effort.LOW),
        max_iterations=config.max_iterations,
        auto_compress_after=config.auto_compress_after,
        keep_recent_after_compression=config.keep_recent_after_compression,
    )
