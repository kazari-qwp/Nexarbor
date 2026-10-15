from pathlib import Path
import os
from datanet.core.component_registry import NodeCodec,register_node
from datanet.core.execution import register_execution_codec
from datanet.core.agent_node import AgentNode
from .configuration import encode_execution,validate_config

def register():
    from .package import load_agent_package
    register_execution_codec(encode_execution,validate_config,load_agent_package)
