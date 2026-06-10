# flight_front/api/run_state.py
import threading
from collections import deque
from typing import Callable

# 장시간 수집 시 메모리 무한 증가 방지 — 최근 N줄만 유지 (WebSocket replay 상한)
_MAX_OUTPUT_LINES = 2000

_lock = threading.Lock()
_state: dict = {"status": "idle", "pid": None}
_output: deque[str] = deque(maxlen=_MAX_OUTPUT_LINES)

# WebSocket 구독자 목록: output 새 라인이 생길 때 호출할 콜백
_subscribers: list[Callable[[str], None]] = []
_sub_lock = threading.Lock()


def get() -> dict:
    with _lock:
        return {**_state, "output": "".join(_output)}


def subscribe(cb: Callable[[str], None]):
    with _sub_lock:
        _subscribers.append(cb)


def unsubscribe(cb: Callable[[str], None]):
    with _sub_lock:
        if cb in _subscribers:
            _subscribers.remove(cb)


def _notify(msg: str):
    with _sub_lock:
        cbs = list(_subscribers)
    for cb in cbs:
        try:
            cb(msg)
        except Exception:
            pass


def set_running(pid: int | None = None):
    with _lock:
        _state["status"] = "running"
        _state["pid"] = pid
        _output.clear()
    _notify("__status__:running")


def append_output(text: str):
    with _lock:
        _output.append(text)
    _notify(text)


def set_done():
    with _lock:
        _state["status"] = "done"
        _state["pid"] = None
    _notify("__status__:done")


def set_error():
    with _lock:
        _state["status"] = "error"
        _state["pid"] = None
    _notify("__status__:error")
