"""Background verification worker for async trust/citation scoring."""
from src.pipeline.answer_pipeline import PipelineContext
from web.backend.task_registry import get_task_registry
from web.backend.ws_manager import get_ws_manager


async def _broadcast(message_id: str, payload: dict) -> None:
    ws = get_ws_manager()
    await ws.broadcast(message_id, payload)


def run_verification_task(
    pipeline,
    message_id: str,
    ctx: PipelineContext,
    response: str,
    enable_consistency: bool = False,
    n_consistency_samples: int = 2,
) -> None:
    """Run in FastAPI BackgroundTasks."""
    registry = get_task_registry()

    try:
        registry.set_running(message_id)
        result = pipeline.run_verification(
            ctx=ctx,
            response=response,
            enable_consistency=enable_consistency,
            n_consistency_samples=n_consistency_samples,
        )

        payload = {
            "type": "verification_complete",
            "message_id": message_id,
            "citation_verification": result.get("citation_verification"),
            "consistency": result.get("consistency"),
            "trust": result.get("trust"),
            "validity_warnings": result.get("validity_warnings") or [],
            "regeneration_attempts": 0,
        }
        registry.set_done(message_id, payload)

        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_broadcast(message_id, payload))
        except RuntimeError:
            asyncio.run(_broadcast(message_id, payload))
    except Exception as e:
        registry.set_error(message_id, str(e))
        err_payload = {
            "type": "verification_error",
            "message_id": message_id,
            "error": str(e),
        }
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_broadcast(message_id, err_payload))
        except RuntimeError:
            asyncio.run(_broadcast(message_id, err_payload))
