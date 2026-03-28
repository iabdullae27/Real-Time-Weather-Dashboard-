from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OWM_API_KEY: str = "your_openweathermap_api_key_here"
    OWM_BASE_URL: str = "https://api.openweathermap.org/data/2.5"
    CACHE_TTL_SECONDS: int = 300  # cache weather responses for 5 minutes

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()