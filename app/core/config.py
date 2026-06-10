from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FOODTRUCK"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "foodtruck"
    jwt_secret: str = "dev-foodtruck-secret"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 10080
    otp_client_token: str = "dev-otp-client-token"
    otp_expiry_seconds: int = 300
    otp_max_attempts: int = 5
    allowed_origins: str = "*"
    map_data_dir: str = "map_data"
    vector_mbtiles_path: str = "map_data/tiles/india-southern-zone-shortbread.mbtiles"
    routing_graph_dir: str = "map_data/graphs/india-southern-zone"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins(self) -> List[str]:
        if self.allowed_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def vector_mbtiles(self) -> Path:
        return Path(self.vector_mbtiles_path)

    @property
    def routing_graph(self) -> Path:
        return Path(self.routing_graph_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
