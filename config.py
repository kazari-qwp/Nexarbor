from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
APPLICATIONS_DIR = PROJECT_ROOT / "applications"
EXPERIMENT_DIR = APPLICATIONS_DIR / "experiment"
DATA_DIR = EXPERIMENT_DIR / "data"
RECORDS_PATH = DATA_DIR / "实验记录01" / "01.csv"
DB_PATH = DATA_DIR / "lab.db"
SYSTEM_PROMPT_PATH = EXPERIMENT_DIR / "prompts" / "report_system.md"
TOOLS_PATH = EXPERIMENT_DIR / "tools" / "tools.json"
ENV_PATH = PROJECT_ROOT / ".env"
