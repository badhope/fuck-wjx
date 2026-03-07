"""运行时流程控制 - 暂停、停止、重试等状态管理"""
import logging
import threading
import time
from typing import Any, Optional

from wjx.core.task_context import TaskContext
from wjx.utils.event_bus import bus as _event_bus, EVENT_TARGET_REACHED
from wjx.utils.logging.log_utils import log_suppressed_exception


def _is_fast_mode(ctx: TaskContext) -> bool:
    """极速模式：时长控制/随机IP关闭且时间间隔为0时自动启用。"""
    return ctx.is_fast_mode()


def _timed_mode_active(ctx: TaskContext) -> bool:
    return bool(ctx.timed_mode_enabled)


def _handle_submission_failure(
    ctx: TaskContext,
    stop_signal: Optional[threading.Event],
    thread_name: Optional[str] = None,
) -> bool:
    """
    递增失败计数；当开启失败止损时超过阈值会触发停止。
    返回 True 表示已触发强制停止。
    """
    with ctx.lock:
        ctx.cur_fail += 1
        if ctx.stop_on_fail_enabled:
            print(f"已失败{ctx.cur_fail}次, 失败次数达到{int(ctx.fail_threshold)}次将强制停止")
        else:
            print(f"已失败{ctx.cur_fail}次（失败止损已关闭）")
    if thread_name:
        try:
            ctx.increment_thread_fail(thread_name, status_text="失败重试")
        except Exception:
            logging.debug("更新线程失败计数失败", exc_info=True)
    if ctx.stop_on_fail_enabled and ctx.cur_fail >= ctx.fail_threshold:
        logging.critical("失败次数过多，强制停止，请检查配置是否正确")
        if stop_signal:
            stop_signal.set()
        return True
    return False


def _wait_if_paused(gui_instance: Optional[Any], stop_signal: Optional[threading.Event]) -> None:
    try:
        if gui_instance and hasattr(gui_instance, "wait_if_paused"):
            gui_instance.wait_if_paused(stop_signal)
    except Exception as exc:
        log_suppressed_exception("runtime_control._wait_if_paused", exc)


def _trigger_target_reached_stop(
    ctx: TaskContext,
    stop_signal: Optional[threading.Event],
    gui_instance: Optional[Any] = None,
) -> None:
    """达到目标份数时触发全局立即停止。"""
    with ctx._target_reached_stop_lock:
        if ctx._target_reached_stop_triggered:
            if stop_signal:
                stop_signal.set()
            return
        ctx._target_reached_stop_triggered = True

    if stop_signal:
        stop_signal.set()

    # 通过 EventBus 通知上层
    _event_bus.emit(EVENT_TARGET_REACHED, ctx=ctx)

    # 兼容旧式 gui_instance 回调（过渡期保留）
    def _notify():
        try:
            if gui_instance and hasattr(gui_instance, "force_stop_immediately"):
                gui_instance.force_stop_immediately(reason="任务完成")
        except Exception:
            logging.debug("达到目标份数时触发强制停止失败", exc_info=True)

    dispatcher = getattr(gui_instance, "_post_to_ui_thread_async", None) if gui_instance else None
    if callable(dispatcher):
        try:
            dispatcher(_notify)
            return
        except Exception:
            logging.debug("派发任务完成事件到主线程失败", exc_info=True)
    dispatcher = getattr(gui_instance, "_post_to_ui_thread", None) if gui_instance else None
    if callable(dispatcher):
        try:
            dispatcher(_notify)
            return
        except Exception:
            logging.debug("派发任务完成事件到主线程失败", exc_info=True)
    _notify()


def _sleep_with_stop(stop_signal: Optional[threading.Event], seconds: float) -> bool:
    """带停止信号的睡眠，返回 True 表示被中断。"""
    if seconds <= 0:
        return False
    if stop_signal:
        interrupted = stop_signal.wait(seconds)
        return bool(interrupted and stop_signal.is_set())
    time.sleep(seconds)
    return False
