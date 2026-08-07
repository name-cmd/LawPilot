"""Background verification worker for async trust/citation scoring."""
import asyncio
from typing import Optional

from src.pipeline.answer_pipeline import PipelineContext
from web.backend.task_registry import get_task_registry
from web.backend.ws_manager import get_ws_manager

# 主事件循环引用：worker 在 FastAPI 后台线程池执行（同步函数），
# 而 WebSocket 连接绑定主事件循环 —— 跨循环直接 send_text 会抛
# "attached to a different loop"，导致核验结果永远送不到前端（表现为一直"核验中"）。
# 因此服务启动时绑定主循环，广播统一用 run_coroutine_threadsafe 调度回主循环执行。
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def bind_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """服务启动（lifespan）时调用，保存主事件循环引用。"""
    global _main_loop
    _main_loop = loop


async def _broadcast(message_id: str, payload: dict) -> None:
    ws = get_ws_manager()
    await ws.broadcast(message_id, payload)


def _schedule_broadcast(message_id: str, payload: dict) -> None:
    """把广播调度到主事件循环执行（线程安全；结果错误只打印，不再向上抛）。"""
    if _main_loop is not None and _main_loop.is_running():
        try:
            fut = asyncio.run_coroutine_threadsafe(
                _broadcast(message_id, payload), _main_loop
            )
            # 诊断：广播任务在主循环执行的结果（失败不向上抛，只打印）
            try:
                fut.result(timeout=5)
            except Exception as e:
                print(f"[verification] 广播执行失败 {message_id}：{e}", flush=True)
            else:
                print(f"[verification] 广播成功 {message_id} type={payload.get('type')}", flush=True)
            return
        except Exception as e:  # 调度本身失败（极少见）退化为直接运行
            print(f"[verification] 广播调度失败：{e}", flush=True)
    # 兜底：无主循环引用时直接运行（跨循环仍可能失败，但保留旧行为）
    try:
        asyncio.run(_broadcast(message_id, payload))
    except Exception as e:
        print(f"[verification] 广播失败：{e}", flush=True)


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
        print(f"[verification] 任务启动 {message_id}", flush=True)
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
        _schedule_broadcast(message_id, payload)
    except Exception as e:
        registry.set_error(message_id, str(e))
        err_payload = {
            "type": "verification_error",
            "message_id": message_id,
            "error": str(e),
        }
        _schedule_broadcast(message_id, err_payload)
