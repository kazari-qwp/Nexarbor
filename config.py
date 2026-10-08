from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
RECORDS_PATH = DATA_DIR / "实验记录01" / "01.csv"
DB_PATH = DATA_DIR / "lab.db"
AGENTS_DIR = PROJECT_ROOT / "agents"
SYSTEM_PROMPT_PATH = AGENTS_DIR / "prompts" / "report_system.md"
TOOLS_PATH = AGENTS_DIR / "tools" / "tools.json"
ENV_PATH = PROJECT_ROOT / ".env"
