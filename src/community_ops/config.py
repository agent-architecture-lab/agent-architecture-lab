import os

from pydantic import BaseModel, SecretStr, model_validator


class Settings(BaseModel):
    live_model: bool = False
    openai_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def require_key_for_live_model(self) -> "Settings":
        if self.live_model and self.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY is required when live_model is enabled")
        return self

    @classmethod
    def from_env(cls, *, live_model: bool = False) -> "Settings":
        return cls(live_model=live_model, openai_api_key=os.getenv("OPENAI_API_KEY"))
