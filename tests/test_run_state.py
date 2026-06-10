# tests/test_run_state.py
#
# run_state 출력 버퍼 상한/리셋 단위 테스트

import pytest

from flight_front.api import run_state


@pytest.fixture(autouse=True)
def reset_state():
    run_state.set_running(pid=None)
    yield
    run_state.set_done()


class TestRunStateOutput:
    def test_append_and_join(self):
        run_state.append_output("line1\n")
        run_state.append_output("line2\n")
        assert run_state.get()["output"] == "line1\nline2\n"

    def test_output_capped_at_max_lines(self):
        for i in range(run_state._MAX_OUTPUT_LINES + 100):
            run_state.append_output(f"line{i}\n")
        output = run_state.get()["output"]
        lines = output.strip().split("\n")
        assert len(lines) == run_state._MAX_OUTPUT_LINES
        # 가장 오래된 줄이 밀려나고 최신 줄은 유지
        assert lines[0] == "line100"
        assert lines[-1] == f"line{run_state._MAX_OUTPUT_LINES + 99}"

    def test_set_running_clears_output(self):
        run_state.append_output("old run output\n")
        run_state.set_running(pid=123)
        state = run_state.get()
        assert state["output"] == ""
        assert state["status"] == "running"
        assert state["pid"] == 123

    def test_status_transitions(self):
        run_state.set_running(pid=1)
        assert run_state.get()["status"] == "running"
        run_state.set_done()
        state = run_state.get()
        assert state["status"] == "done"
        assert state["pid"] is None

    def test_subscriber_receives_output(self):
        received: list[str] = []
        run_state.subscribe(received.append)
        try:
            run_state.append_output("hello\n")
        finally:
            run_state.unsubscribe(received.append)
        assert "hello\n" in received
