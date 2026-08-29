import os

# backend/ 目录（config.py 位于 backend/app/core/ 下）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Settings:
    host: str = "127.0.0.1"
    port: int = int(os.environ.get("AGENT_ROOM_PORT", "8899"))
    # LLM 配置（v1.2 决策：OpenAI 兼容端点，MVP 先用环境变量，V2 迁设置页）
    llm_base_url: str = os.environ.get("AGENT_ROOM_LLM_BASE_URL", "")
    llm_api_key: str = os.environ.get("AGENT_ROOM_LLM_API_KEY", "")
    llm_model: str = os.environ.get("AGENT_ROOM_LLM_MODEL", "")
    # 第 5 步编排：任务级熔断（互聊条数超限 → system @人类并暂停任务）
    task_max_chat_turns: int = int(os.environ.get("AGENT_ROOM_TASK_MAX_CHAT_TURNS", "12"))
    subtask_max_retries: int = int(os.environ.get("AGENT_ROOM_SUBTASK_MAX_RETRIES", "2"))
    # 第 5 步向量记忆：注入上下文的 top-k
    memory_top_k: int = int(os.environ.get("AGENT_ROOM_MEMORY_TOP_K", "3"))


settings = Settings()
