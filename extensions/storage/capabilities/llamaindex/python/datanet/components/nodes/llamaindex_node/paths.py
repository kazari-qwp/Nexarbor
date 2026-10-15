from datanet.core.component_registry import resource_directory
from pathlib import Path
import os
PACKAGE_DIR=resource_directory(__file__)
PROJECT_ROOT=Path(os.environ.get('DATANET_WORKSPACE',Path.cwd())).resolve()
ENV_PATH=PROJECT_ROOT/'.env'
COMPONENTS_DIR=PACKAGE_DIR
NETWORK_PATH=PACKAGE_DIR/'package.json'
DATA_DIR=PROJECT_ROOT/'.datanet'/'examples'
RECORDS_PATH=DATA_DIR/'实验记录01'/'01.csv'
DB_PATH=DATA_DIR/'lab.db'
