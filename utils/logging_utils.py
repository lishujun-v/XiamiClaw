"""项目统一日志工具。"""

from __future__ import annotations

import json
import logging
import threading
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from utils.config import get_logging_config


PROJECT_LOGGER_NAME = "xiamiclaw"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_LOGGER_CACHE: dict[tuple[str, str], logging.Logger] = {}
_CACHE_LOCK = threading.RLock()


def _sanitize_filename(value: str) -> str:
    normalized = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
    return normalized or "agent"


class AgentLoggerAdapter(logging.LoggerAdapter):
    """为日志追加 agent/workspace 上下文。"""

    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("agent_name", self.extra.get("agent_name", "unknown"))
        extra.setdefault("workspace", self.extra.get("workspace", ""))
        return msg, kwargs


class DailySizeRotatingFileHandler(logging.Handler):
    """按天和文件大小轮转的文件日志 Handler。"""

    terminator = "\n"

    def __init__(self, log_dir: str | Path, agent_name: str, max_bytes: int = DEFAULT_MAX_BYTES):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.agent_name = _sanitize_filename(agent_name)
        self.max_bytes = max(1, int(max_bytes))
        self._lock = threading.RLock()
        self._stream = None
        self._current_date: Optional[str] = None
        self._current_index: int = 0
        self._current_path: Optional[Path] = None

    def _now(self) -> datetime:
        return datetime.now()

    def _filename_for(self, date_str: str, index: int) -> str:
        suffix = "" if index == 0 else f"_{index:02d}"
        return f"{self.agent_name}_{date_str}{suffix}.log"

    def _path_for(self, date_str: str, index: int) -> Path:
        return self.log_dir / self._filename_for(date_str, index)

    def _select_path(self, date_str: str, incoming_bytes: int) -> tuple[Path, int]:
        index = 0
        while True:
            candidate = self._path_for(date_str, index)
            if not candidate.exists():
                return candidate, index
            if candidate.stat().st_size + incoming_bytes <= self.max_bytes:
                return candidate, index
            index += 1

    def _open_stream(self, incoming_bytes: int):
        date_str = self._now().strftime("%Y-%m-%d")
        path, index = self._select_path(date_str, incoming_bytes)
        if self._stream:
            self._stream.close()
        self._current_date = date_str
        self._current_index = index
        self._current_path = path
        self._stream = open(path, "a", encoding="utf-8")

    def _should_reopen(self, incoming_bytes: int) -> bool:
        if self._stream is None or self._current_path is None or self._current_date is None:
            return True

        current_date = self._now().strftime("%Y-%m-%d")
        if current_date != self._current_date:
            return True

        try:
            current_size = self._current_path.stat().st_size
        except FileNotFoundError:
            return True

        return current_size + incoming_bytes > self.max_bytes

    def emit(self, record: logging.LogRecord):
        try:
            message = self.format(record)
            payload = f"{message}{self.terminator}"
            incoming_bytes = len(payload.encode("utf-8"))
            with self._lock:
                if self._should_reopen(incoming_bytes):
                    self._open_stream(incoming_bytes)
                if not self._stream:
                    return
                self._stream.write(payload)
                self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self):
        with self._lock:
            if self._stream:
                self._stream.close()
                self._stream = None
        super().close()


def get_logger(name: str) -> logging.Logger:
    """获取项目 logger。"""
    logger = logging.getLogger(f"{PROJECT_LOGGER_NAME}.{name}")
    return logger


def get_agent_logger(agent_name: str, workspace: str, component: str = "app") -> AgentLoggerAdapter:
    """获取 agent 级别 logger。"""
    config = get_logging_config()
    level_name = str(config.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    log_dir_name = config.get("directory_name", "logs")
    max_bytes = int(config.get("max_file_size_mb", 5)) * 1024 * 1024

    workspace_path = Path(workspace).resolve()
    workspace_digest = hashlib.md5(str(workspace_path).encode("utf-8")).hexdigest()[:8]
    base_name = f"{PROJECT_LOGGER_NAME}.agent.{_sanitize_filename(agent_name)}.{workspace_digest}"
    cache_key = (base_name, str(workspace_path))

    with _CACHE_LOCK:
        base_logger = _LOGGER_CACHE.get(cache_key)
        if base_logger is None:
            base_logger = logging.getLogger(base_name)
            base_logger.setLevel(level)
            base_logger.propagate = False

            if not base_logger.handlers:
                handler = DailySizeRotatingFileHandler(
                    log_dir=workspace_path / log_dir_name,
                    agent_name=agent_name,
                    max_bytes=max_bytes,
                )
                formatter = logging.Formatter(
                    fmt="%(asctime)s | %(levelname)s | %(agent_name)s | %(name)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
                handler.setFormatter(formatter)
                handler.setLevel(level)
                base_logger.addHandler(handler)

            _LOGGER_CACHE[cache_key] = base_logger

    component_logger = logging.getLogger(f"{base_name}.{component}")
    component_logger.setLevel(level)
    return AgentLoggerAdapter(
        component_logger,
        {"agent_name": agent_name, "workspace": str(workspace_path)},
    )


logging.getLogger(PROJECT_LOGGER_NAME).addHandler(logging.NullHandler())


def truncate_for_log(value: Any, limit: int = 300) -> str:
    """将复杂对象压缩为单行日志预览。"""
    if value is None:
        return ""

    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)

    normalized = " ".join(text.splitlines())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "...(truncated)"


def summarize_for_log(value: Any, preview_limit: int = 160) -> str:
    """输出带长度的日志摘要，便于快速判断内容规模。"""
    if value is None:
        return "len=0 preview="

    if isinstance(value, str):
        raw = value
    else:
        try:
            raw = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            raw = str(value)

    normalized = " ".join(raw.splitlines())
    preview = truncate_for_log(normalized, preview_limit)
    return f"len={len(normalized)} preview={preview}"


def summarize_tool_result(success: bool, content: Any = None, error: Any = None, preview_limit: int = 160) -> str:
    """格式化工具执行结果摘要。"""
    if success:
        return f"content={summarize_for_log(content, preview_limit=preview_limit)}"
    return f"error={summarize_for_log(error, preview_limit=preview_limit)}"


def format_trace_message(stage: str, **fields: Any) -> str:
    """生成统一的执行轨迹日志。"""
    parts = [f"TRACE {stage}"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={truncate_for_log(value, 240)}")
    return " | ".join(parts)
