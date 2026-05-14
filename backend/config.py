import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# AI API 配置（DeepSeek 为主，OpenAI 兼容协议可切换）
AI_API_KEY = os.getenv("AI_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
AI_BASE_URL = os.getenv("AI_BASE_URL", os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic"))
AI_MODEL = os.getenv("AI_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))

# 数据库
DB_PATH = BASE_DIR / "db" / "knowledge.db"

# ChromaDB
CHROMA_PATH = BASE_DIR / "data" / "chroma"

# 临时文件（视频/音频处理后删除）
TEMP_DIR = BASE_DIR / "temp"

# 下载目录（保留下载功能）
DOWNLOAD_DIR = BASE_DIR / "downloads"

# Whisper（预留，暂不启用）
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_MODELS_DIR = BASE_DIR / "data" / "whisper_models"

# 任务队列
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "2"))

# 确保目录存在
for d in [DB_PATH.parent, CHROMA_PATH, TEMP_DIR, DOWNLOAD_DIR]:
    d.mkdir(parents=True, exist_ok=True)
