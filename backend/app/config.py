from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "家庭故事豆 API"
    api_prefix: str = "/v1"
    database_url: str = "postgresql+psycopg://storybean:storybean@127.0.0.1:5432/storybean"
    redis_url: str = "redis://127.0.0.1:6379/0"
    object_storage_bucket: str = "family-story-bean-dev"
    object_storage_endpoint: str = "http://127.0.0.1:9000"
    pipeline_version: str = "storyboard-v1"
    allow_mock_routes: bool = True
    allow_dev_wechat_login: bool = False
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    auth_signing_key: str = "replace-me-outside-development"
    access_token_ttl_seconds: int = 7200
    web_cors_origins: str = "http://127.0.0.1:4173,http://localhost:4173"
    public_web_base_url: str = "http://127.0.0.1:4173"
    allow_dev_web_otp: bool = False
    web_otp_dev_code: str = ""
    web_otp_ttl_seconds: int = 300
    web_otp_resend_seconds: int = 60
    upload_token_ttl_seconds: int = 900
    max_audio_bytes: int = 524288000
    local_object_storage_path: str = ".data/objects"
    pipeline_accept_new_jobs: bool = True
    pipeline_demo_step_seconds: float = 1.0
    pipeline_stale_after_seconds: int = 120
    pipeline_task_time_limit_seconds: int = 900
    allow_task_fault_injection: bool = False
    asr_provider: str = "mlx_whisper"
    allow_demo_asr: bool = False
    asr_model_path: str = ""
    asr_retry_model_path: str = ""
    asr_language: str = "zh"
    asr_low_confidence_threshold: float = 0.65
    asr_retry_enabled: bool = True
    asr_max_retry_segments: int = 8
    asr_initial_prompt: str = "请忠实转写为简体中文，保留人物名称、自然标点和完整语义。"
    playback_token_ttl_seconds: int = 600
    podcast_tts_provider: str = "auto"
    podcast_tts_fallback_to_system: bool = True
    podcast_script_provider: str = "safe-template"
    podcast_script_model: str = "sound-story-safe-v1"
    podcast_script_endpoint: str = ""
    podcast_script_api_key: str = ""
    podcast_script_timeout_seconds: float = 45.0
    podcast_render_dispatcher: str = "local"
    podcast_render_max_retries: int = 2
    podcast_creation_enabled: bool = True
    podcast_sharing_enabled: bool = True
    podcast_rollout_mode: str = "open"
    podcast_rollout_user_ids: str = ""
    comic_creation_enabled: bool = False
    volcengine_tts_app_id: str = ""
    volcengine_tts_access_token: str = ""
    volcengine_tts_api_key: str = ""
    volcengine_tts_endpoint: str = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    volcengine_tts_resource_id: str = "seed-tts-2.0"
    volcengine_tts_voice: str = "zh_female_xiaohe_uranus_bigtts"
    volcengine_tts_sample_rate: int = 24000
    volcengine_tts_speech_rate: int = -8
    volcengine_tts_timeout_seconds: float = 45.0

    @property
    def web_cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.web_cors_origins.split(",") if origin.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
