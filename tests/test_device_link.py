import asyncio
from src.device_link import DeviceLink


def test_discovery_pagination_rpc_and_no_blocking_receive():
    async def run():
        sent = []
        async def send(payload):
            sent.append(payload)
            method = payload.get('method')
            if method == 'initialize':
                result = {'serverInfo': {'name': 'test-device', 'version': '1'}}
            elif method == 'tools/list':
                assert payload['params']['withUserTools'] is True
                if not payload['params'].get('cursor'):
                    result = {'tools': [{'name': 'self.get_device_status', 'inputSchema': {}}], 'nextCursor': 'page2'}
                else:
                    result = {'tools': [{'name': 'self.audio_speaker.set_volume', 'inputSchema': {
                        'properties': {'volume': {'type': 'integer', 'minimum': 0, 'maximum': 100}}, 'required': ['volume']}}]}
            elif method == 'tools/call':
                result = {'content': [{'type': 'text', 'text': 'true'}]}
            else:
                return
            # A separate receive task resolves the request; send() itself never waits on it.
            asyncio.get_running_loop().call_soon(link.receive, {'id': payload['id'], 'result': result})
        link = DeviceLink(send)
        link.start()
        await link.wait_ready()
        assert len(link.tools) == 2
        assert await link.call_tool('self.audio_speaker.set_volume', {'volume': 50}) == 'true'
        before = len(sent)
        for args in ({'volume': True}, {'volume': 200}, {'url': 'bad'}):
            try:
                await link.call_tool('self.audio_speaker.set_volume', args)
                assert False, 'Invalid arguments must be rejected before transmission'
            except ValueError:
                pass
        assert len(sent) == before
        await link.close()
        assert not link.pending
    asyncio.run(run())


def test_cancelled_rpc_is_cleaned_and_late_reply_does_not_restart_it():
    async def run():
        sent = []
        async def send(payload):
            sent.append(payload)
        link = DeviceLink(send)
        link.tools = {'self.reboot': {'name': 'self.reboot', 'inputSchema': {}}}
        link.ready.set()
        task = asyncio.create_task(link.call_tool('self.reboot', {}))
        await asyncio.sleep(0)
        call_id = sent[-1]['id']
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert not link.pending
        link.receive({'id': call_id, 'result': {'content': [{'text': 'true'}]}})
        assert task.cancelled()
        await link.close()
    asyncio.run(run())
