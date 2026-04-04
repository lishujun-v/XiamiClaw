"""配置加载模块"""

import os
import yaml
from pathlib import Path

# 配置文件路径
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

# 全局配置缓存
_config = None


def load_config() -> dict:
    """加载配置文件"""
    global _config

    if _config is None:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                _config = yaml.safe_load(f)
        else:
            _config = {}

    return _config


def get_model_config() -> dict:
    """获取当前模型的配置"""
    config = load_config()

    provider = config.get('model_provider', 'custom')
    provider_config = config.get(provider, {})

    return {
        'provider': provider,
        **provider_config
    }


def get_agent_config() -> dict:
    """获取 Agent 配置"""
    config = load_config()
    return config.get('agent', {})


def get_cli_config() -> dict:
    """获取 CLI 配置"""
    config = load_config()
    return config.get('cli', {})


def get_logging_config() -> dict:
    """获取日志配置"""
    config = load_config()
    return config.get('logging', {})


if __name__ == "__main__":
    # 测试配置加载
    print("当前配置:")
    print(f"  model_provider: {load_config().get('model_provider')}")
    print(f"  model_config: {get_model_config()}")
