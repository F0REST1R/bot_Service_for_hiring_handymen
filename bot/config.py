from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import List, Union

class Settings(BaseSettings):
    BOT_TOKEN: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DBNAME: str
    REDIS_URL: str = ""
    ADMIN_IDS: Union[str, List[int]] = Field(default=[])
    
    @property
    def DATABASE_URL(self):
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DBNAME}"
    
    @field_validator('ADMIN_IDS', mode='before')
    @classmethod
    def parse_admin_ids(cls, v):
        """Преобразование ADMIN_IDS в список int"""
        if isinstance(v, str):
            # Если строка с запятыми
            if ',' in v:
                return [int(x.strip()) for x in v.split(',')]
            # Если одно число в строке
            return [int(v)]
        elif isinstance(v, int):
            return [v]
        elif isinstance(v, list):
            return [int(x) for x in v]
        return []
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()