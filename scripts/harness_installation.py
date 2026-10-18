"""解析本项目使用的 Harness 程序；不启动程序或修改全局环境。"""
import json
import os
from pathlib import Path


def harness_executable():
    if os.environ.get('DATANET_HARNESS_EXE'):
        return Path(os.environ['DATANET_HARNESS_EXE'])
    record=Path(__file__).resolve().parents[1]/'build/harness-installation.json'
    if record.exists():
        executable=Path(json.loads(record.read_text(encoding='utf-8'))['executable'])
        if not executable.is_absolute():raise ValueError('Harness 安装记录必须提供绝对路径')
        return executable
    return Path(os.environ['LOCALAPPDATA'])/'Programs/DeepSeek Harness/DeepSeek Harness.exe'
