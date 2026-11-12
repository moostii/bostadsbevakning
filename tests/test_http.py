import httpx
import pytest

from bevakning.http import USER_AGENT, PoliteClient


class FakeTime:
    def __init__(self):
        self.t = 100.0
        self.sleeps = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(round(s, 3))
        self.t += s


def make(handler, ft):
    client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return PoliteClient(min_interval=1.1, client=client, sleep=ft.sleep, clock=ft.clock)


def test_throttles_per_host():
    ft = FakeTime()
    seen = []

    def handler(req):
        seen.append(req.headers["user-agent"])
        return httpx.Response(200, text="ok")

    pc = make(handler, ft)
    pc.get_text("https://a.example/1")
    pc.get_text("https://b.example/1")   # annan domän: ingen väntan
    pc.get_text("https://a.example/2")   # samma domän direkt efter: väntar 1.1 s
    assert ft.sleeps == [1.1]
    assert seen == [USER_AGENT] * 3


def test_retries_once_on_5xx_then_raises():
    ft = FakeTime()
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)

    pc = make(handler, ft)
    with pytest.raises(httpx.HTTPStatusError):
        pc.get_text("https://a.example/")
    assert len(calls) == 2


def test_no_retry_on_404():
    ft = FakeTime()
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404)

    pc = make(handler, ft)
    with pytest.raises(httpx.HTTPStatusError):
        pc.get_text("https://a.example/")
    assert len(calls) == 1
