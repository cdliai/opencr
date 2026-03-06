from fastapi import APIRouter
from fastapi.responses import JSONResponse
from ocr_pipeline.config import settings
from ocr_pipeline.models.schemas import HealthResponse
from ocr_pipeline.services.startup import model_readiness


router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
async def health_check():

    status = "ready" if model_readiness.ready else "waiting"
    
    resp = HealthResponse(
        status=status,
        pipeline_version=settings.pipeline_version,
        model_server_url=settings.model_server_url,
        model_name=settings.model_name,
        model_status=model_readiness.status,
        input_dir=str(settings.input_dir),
        output_dir=str(settings.output_dir),
    )
    if not model_readiness.ready:
        return JSONResponse(content=resp.model_dump(), status_code=503)

    return resp
