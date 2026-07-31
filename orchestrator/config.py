import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")

POLL_INTERVAL_SECONDS    = float(os.getenv("POLL_INTERVAL_SECONDS", "10"))
GROUPING_WINDOW_SECONDS  = float(os.getenv("GROUPING_WINDOW_SECONDS", "10"))

ERROR_RATE_THRESHOLD   = float(os.getenv("ERROR_RATE_THRESHOLD", "0.15"))
LATENCY_THRESHOLD_MS   = float(os.getenv("LATENCY_THRESHOLD_MS", "800"))
CONNECTIONS_THRESHOLD  = float(os.getenv("CONNECTIONS_THRESHOLD", "18"))

RSS_TREND_LOOKBACK_SECONDS  = float(os.getenv("RSS_TREND_LOOKBACK_SECONDS", "120"))
RSS_TREND_SLOPE_MB_PER_MIN  = float(os.getenv("RSS_TREND_SLOPE_MB_PER_MIN", "5.0"))
RSS_TREND_MIN_MB            = float(os.getenv("RSS_TREND_MIN_MB", "200"))

SIMILARITY_THRESHOLD         = float(os.getenv("SIMILARITY_THRESHOLD", "0.86"))
RECURRENCE_LOOKBACK_SECONDS  = float(os.getenv("RECURRENCE_LOOKBACK_SECONDS", "3600"))

AWS_REGION       = os.getenv("AWS_REGION", "us-east-1")
EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
FAISS_DIM        = int(os.getenv("FAISS_DIM", "1024"))

SUMMARIZER_POLL_INTERVAL_SECONDS = float(os.getenv("SUMMARIZER_POLL_INTERVAL_SECONDS", "10"))
LLM_MODEL_ID     = os.getenv("LLM_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
LLM_MAX_TOKENS   = int(os.getenv("LLM_MAX_TOKENS", "2000"))
CASE_CONTEXT_PADDING_SECONDS = float(os.getenv("CASE_CONTEXT_PADDING_SECONDS", "30"))

MATCHER_POLL_INTERVAL_SECONDS = float(os.getenv("MATCHER_POLL_INTERVAL_SECONDS", "10"))
ACTION_MATCH_TOP_K = int(os.getenv("ACTION_MATCH_TOP_K", "3"))

_DATA_DIR        = os.path.join(os.path.dirname(__file__), "data")
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", os.path.join(_DATA_DIR, "cases.faiss"))
CHECKPOINT_PATH  = os.getenv("CHECKPOINT_PATH", os.path.join(_DATA_DIR, "checkpoint.json"))

SOURCE_TOOL_NAME = os.getenv("SOURCE_TOOL_NAME", "stage1_poller")
