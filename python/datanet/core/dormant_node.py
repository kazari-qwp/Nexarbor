"""Preserve an installed but disabled component's data without importing its code."""
from copy import deepcopy
from pathlib import Path
from datanet.core.node import Node, NodeResult


class DormantNode(Node):
    def __init__(self, common, type_id, parameters, base, owner):
        super().__init__(*common)
        self.original_type = type_id
        self.original_parameters = deepcopy(parameters)
        self.original_base = Path(base).resolve()
        self.component_owner = owner

    def read(self, request):
        return NodeResult(status='forbidden', errors=['Component is disabled: ' + self.component_owner])

    def write(self, *args, **kwargs):
        return NodeResult(status='forbidden', errors=['Component is disabled: ' + self.component_owner])
