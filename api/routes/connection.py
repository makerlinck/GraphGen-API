from fastapi import APIRouter

from api.schemas.connection import TestConnectionRequest, TestConnectionResponse
from api.services.connection import test_connection

router = APIRouter(prefix="/api/v1", tags=["connections"])


@router.post("/connections/validate", response_model=TestConnectionResponse)
async def validate_connection(req: TestConnectionRequest):
    success, message = test_connection(req.base_url, req.api_key, req.model)
    return TestConnectionResponse(success=success, message=message)
