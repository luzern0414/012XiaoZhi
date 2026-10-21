from src.streaming import StreamRelay
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from contextvars import ContextVar
import asyncio
import pytest


def test_transient_overload_retries_only_before_any_output():
    from src.streaming import retry_before_output
    calls=[]
    def provider():
        calls.append(1)
        if len(calls)==1:
            raise RuntimeError('Our servers are currently overloaded. Please try again later.')
        yield '回答'
    assert list(retry_before_output(provider,lambda:True,pause=lambda:None)) == ['回答']
    assert len(calls)==2
    calls.clear()
    def partial():
        calls.append(1)
        yield '已经输出'
        raise RuntimeError('Our servers are currently overloaded')
    with pytest.raises(RuntimeError):
        list(retry_before_output(partial,lambda:True,pause=lambda:None))
    assert len(calls)==1


def test_retry_stops_when_closed_and_never_retries_auth_errors():
    from src.streaming import retry_before_output
    enabled=[True]
    calls=[]
    def provider():
        calls.append(1)
        raise RuntimeError('server overloaded')
        yield
    assert list(retry_before_output(provider,lambda:enabled[0],pause=lambda:enabled.__setitem__(0,False))) == []
    assert len(calls)==1
    def denied():
        calls.append(1)
        raise RuntimeError('invalid API key')
        yield
    with pytest.raises(RuntimeError):
        list(retry_before_output(denied,lambda:True,pause=lambda:None))
    assert len(calls)==2


def test_chat_intent_before_close_cannot_submit_as_new_turn_after_stt_wait():
    from src.streaming import TurnExecutor
    called = []
    class Owner:
        def chat(self, text):
            called.append(text)
    async def run():
        owner = Owner()
        owner.control_gate = SimpleNamespace(enabled=True)
        owner.control_generation = 1
        owner.control_worker = threading.local()
        owner.control_turn = ContextVar('test_chat_generation', default=None)
        entered, release = asyncio.Event(), asyncio.Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            turns = TurnExecutor(executor, owner)
            async def old_request():
                owner.control_turn.set(owner.control_generation)
                entered.set()
                await release.wait()  # upstream sends STT after the intent gate
                await asyncio.wrap_future(turns.submit(owner.chat, 'old question'))
            task = asyncio.create_task(old_request())
            await entered.wait()
            owner.control_generation = 3  # another task closes and reopens
            release.set()
            await task
        assert called == []
    asyncio.run(run())


def test_stale_hardware_generation_cannot_resume_after_reenable():
    from src.streaming import guarded_source
    state = [True, 1]
    consumed = []
    def provider():
        for item in ['a', 'b']:
            consumed.append(item)
            yield item
    stream = guarded_source(provider, lambda: state == [True, 1])
    assert next(stream) == 'a'
    state[:] = [True, 3]  # closed and opened again before the old worker wakes
    assert list(stream) == []
    assert consumed == ['a']


def test_disabled_session_does_not_create_a_provider_request():
    from src.streaming import guarded_source
    def provider():
        raise AssertionError('A disabled session must not call the model')
    assert list(guarded_source(provider, lambda: False)) == []


def test_chat_queued_before_close_cannot_run_after_reenable():
    from src.streaming import TurnExecutor
    entered, release = threading.Event(), threading.Event()
    owner = SimpleNamespace(control_gate=SimpleNamespace(enabled=True),
        control_generation=1, control_worker=threading.local())
    called = []
    class Owner:
        def chat(self, text):
            called.append(text)
    actual_owner = Owner()
    actual_owner.__dict__.update(owner.__dict__)
    with ThreadPoolExecutor(max_workers=1) as executor:
        def occupy():
            entered.set()
            release.wait(2)
        executor.submit(occupy)
        assert entered.wait(1)
        turns = TurnExecutor(executor, actual_owner)
        queued = turns.submit(actual_owner.chat, 'old request')
        actual_owner.control_generation = 3
        release.set()
        queued.result(timeout=2)
    assert not called


def test_worker_retains_generation_through_memory_wait():
    from src.streaming import TurnExecutor
    class Owner:
        def chat(self, text):
            original = self.control_worker.generation
            self.control_generation += 2
            assert self.control_worker.generation == original
            return original
    owner = Owner()
    owner.control_gate = SimpleNamespace(enabled=True)
    owner.control_generation = 1
    owner.control_worker = threading.local()
    with ThreadPoolExecutor(max_workers=1) as executor:
        turns = TurnExecutor(executor, owner)
        assert turns.submit(owner.chat, 'request').result(timeout=2) == 1


def test_chunks_are_delivered_before_provider_finishes():
    events = []
    relay = StreamRelay(events.append, lambda: True, 'turn-1')
    def provider():
        yield '你'
        assert [e['text'] for e in events if e['state'] == 'delta'] == ['你']
        yield '好'
    assert list(relay.forward(provider())) == ['你', '好']
    assert [e['state'] for e in events] == ['start', 'delta', 'delta', 'end']
    assert all(e['request_id'] == 'turn-1' for e in events)


def test_cancelled_turn_stops_consumption_and_cannot_finish_new_turn():
    events, active = [], [True]
    relay = StreamRelay(events.append, lambda: active[0], 'old')
    stream = relay.forward(iter(['a', 'b', 'c']))
    assert next(stream) == 'a'
    active[0] = False
    assert list(stream) == []
    assert [e['state'] for e in events] == ['start', 'delta']


def test_two_connections_have_separate_events():
    left, right = [], []
    a = StreamRelay(left.append, lambda: True, 'a').forward(iter(['甲', '乙']))
    b = StreamRelay(right.append, lambda: True, 'b').forward(iter(['丙']))
    next(a)
    list(b)
    list(a)
    assert ''.join(e.get('text', '') for e in left) == '甲乙'
    assert ''.join(e.get('text', '') for e in right) == '丙'


def test_provider_failure_signals_error_and_propagates():
    import pytest
    events = []
    def broken():
        yield 'a'
        raise RuntimeError('private-provider-detail')
    with pytest.raises(RuntimeError):
        list(StreamRelay(events.append, lambda: True, 'x').forward(broken()))
    assert events[-1]['state'] == 'error'
    assert 'private-provider-detail' not in str(events)
