from pydantic import BaseModel


class TestConnectionRequest(BaseModel):
    model_config = {"extra": "forbid"}

    base_url: str
    api_key: str
    model: str


class TestConnectionResponse(BaseModel):
    model_config = {"extra": "forbid"}

    success: bool
    message: str
