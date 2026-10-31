from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:7b-instruct-q4_K_M"  # same model as tiengviet -> shared VRAM residency
    host: str = "127.0.0.1"  # never 0.0.0.0 — container uses host networking
    port: int = 46405
    temperature: float = 0.8  # creative but stable — 0.9 made qwen code-switch to Chinese
    num_predict: int = 80
    num_ctx: int = 2048
    keep_alive: str = "30m"
    line_timeout_s: float = 12.0  # timeout -> canned line, never an error
    # Whole-line budget INCLUDING the wait for the GPU queue (line_timeout_s only
    # covers one HTTP call). Longest uncontended path: retry_budget_s + line_timeout_s.
    line_deadline_s: float = 20.0
    retry_temperature: float = 0.6  # calmer second attempt after a validation reject
    retry_budget_s: float = 6.0  # only retry if the first attempt came back fast enough
    rate_rpm: int = 20  # re-rolling IS the product, be generous
    max_queue: int = 8
    weather_enabled: bool = True
    weather_cache_s: float = 1800.0
    usage_file: str = "/data/usage.jsonl"
    ip_hash_salt: str = "angi"


settings = Settings()
