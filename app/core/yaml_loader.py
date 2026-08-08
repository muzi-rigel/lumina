"""YAML 配置文件的公共读取基础设施。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from app.core.errors import ConfigError


def as_mapping(value: object, field: str) -> Mapping[str, object]:
    """校验任意配置节点为字符串键对象。"""

    if not isinstance(value, Mapping):
        raise ConfigError(f"配置项 {field} 必须是对象")
    if not all(isinstance(key, str) for key in value):
        raise ConfigError(f"配置项 {field} 的键必须是字符串")
    return value


def load_yaml(path: Path) -> Mapping[str, object]:
    """读取 YAML 根对象，并统一转换底层异常。"""

    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在：{path}") from exc
    except OSError as exc:
        raise ConfigError(f"无法读取配置文件：{path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML 格式错误：{path}") from exc
    return as_mapping(raw, str(path))
