from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from `TJ_TCMS_*` environment variables."""

    model_config = SettingsConfigDict(env_prefix="TJ_TCMS_")

    database_url: str = "sqlite:///./tcms.db"
    # Keys the session hashes. Set it in every real deployment.
    secret_key: str = "dev-insecure-change-me"
    # Local http only: drops the Secure flag from the cookies.
    insecure_cookies: bool = False
    session_ttl_hours: int = 24 * 14
    # Where uploaded result attachments are kept (LocalStorage), and the largest one accepted.
    attachments_dir: str = "./attachments"
    attachment_max_bytes: int = 25 * 1024 * 1024
