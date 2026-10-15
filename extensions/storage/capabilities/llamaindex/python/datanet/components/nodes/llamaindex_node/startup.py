"""Initialize native scientific-library imports before RPC worker threads start."""
import importlib
import importlib.util
import os
from threading import current_thread,main_thread


def initialize(_backend):
    # On Windows this extension can block when its first import happens in a
    # background RPC thread. Do not load optional dependencies for a bare core.
    if os.name=='nt' and current_thread() is main_thread() and importlib.util.find_spec('sentence_transformers'):
        importlib.import_module('llama_index.embeddings.huggingface')


def register(registry):
    registry.initializers.append(initialize)
