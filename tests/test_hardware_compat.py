import asyncio
import json
from types import SimpleNamespace
from aiohttp import web
from src.hardware_compat import install
import pytest


def test_screen_snapshot_is_local_device_only_and_bounded(tmp_path):
    runtime=tmp_path/'data/runtime';runtime.mkdir(parents=True)
    (tmp_path/'data/hardware').mkdir()
    app=SimpleNamespace(SimpleHttpServer=type('Base', (), {}))
    install(app,runtime)
    handler=app.SimpleHttpServer()
    async def run():
        with pytest.raises(web.HTTPForbidden):
            await handler.screen_capture(SimpleNamespace(remote='192.168.16.99'))
        async def upload(data):
            chunks=iter([data, b''])
            async def read_chunk():
                return next(chunks)
            field=SimpleNamespace(name='file', read_chunk=read_chunk)
            async def next_field():
                return field
            async def multipart():
                return SimpleNamespace(next=next_field)
            return await handler.screen_capture(SimpleNamespace(remote='192.168.16.22', multipart=multipart))
        with pytest.raises(web.HTTPBadRequest):
            await upload(b'not a jpeg')
        with pytest.raises(web.HTTPRequestEntityTooLarge):
            await upload(b'\xff\xd8'+b'x'*(1024*1024))
        response=await upload(b'\xff\xd8test\xff\xd9')
        assert response.status == 200
        assert (tmp_path/'data/hardware/screen-latest.jpg').read_bytes()==b'\xff\xd8test\xff\xd9'
    asyncio.run(run())


def test_public_device_header_cannot_retrieve_iot_credentials(tmp_path):
    runtime=tmp_path/'data/runtime';runtime.mkdir(parents=True)
    config=tmp_path/'config';config.mkdir()
    (config/'local.iot.yaml').write_text('username: echoear\npassword: test-only-secret\n')
    class Base:
        pass
    app=SimpleNamespace(SimpleHttpServer=Base)
    install(app,runtime)
    handler=app.SimpleHttpServer()
    async def upstream(request):
        return web.json_response({'websocket':{'url':'ws://local:8000/'}})
    handler.ota_handler=SimpleNamespace(handle_post=upstream)
    async def run():
        spoof=SimpleNamespace(headers={'device-id':'90:e5:b1:d6:40:5c'},remote='192.168.16.99')
        response=await handler.ota(spoof)
        assert 'httpConfig' not in json.loads(response.text)
        assert 'test-only-secret' not in response.text
        genuine=SimpleNamespace(headers=spoof.headers,remote='192.168.16.22')
        response=await handler.ota(genuine)
        assert json.loads(response.text)['httpConfig']['mqtt_user_name']=='echoear'
        assert (runtime/'hardware-ota.json').exists()
    asyncio.run(run())
