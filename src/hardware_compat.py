"""EchoEar vendor extension compatibility, kept outside upstream code."""
from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path


def install(app_module, runtime):
    from aiohttp import web
    base = app_module.SimpleHttpServer
    runtime = Path(runtime)

    class CompatibleHttpServer(base):
        async def ota(self, request):
            response = await self.ota_handler.handle_post(request)
            if (request.headers.get('device-id','').lower() != '90:e5:b1:d6:40:5c'
                    or request.remote != '192.168.16.22' or response.status != 200):
                return response
            result = json.loads(response.text)
            # The vendor fork stores this object as Settings("httpConfig").
            import yaml
            credentials=yaml.safe_load((runtime.parents[1]/'config/local.iot.yaml').read_text(encoding='utf-8'))
            result['httpConfig'] = {'url': 'http://192.168.16.73:8003',
                'mqtt_url':'192.168.16.73','mqtt_port':1883,
                'mqtt_client_id':'echoear-90e5b1d6405c',
                'mqtt_user_name':credentials['username'], 'mqtt_password':credentials['password']}
            (runtime/'hardware-ota.json').write_text(json.dumps(dict(
                at=time.time(), ip=request.remote, board='echoear',
                firmware='2.0.3.3', ota_received=True)),encoding='utf-8')
            return web.json_response(result)

        async def xconfig(self, request):
            (runtime/'hardware-xconfig.json').write_text(json.dumps(dict(
                at=time.time(), ip=request.remote, path=request.path)),encoding='utf-8')
            return web.json_response({'code':200,'data':{
                'config_functions':'[]', 'config_idle_img':'http://192.168.16.73:8003/hardware/greeting.jpg',
                'config_idle_img_interval':30, 'config_idle_text_align':'center',
                'config_idle_text_color':'#26352f'}})

        async def no_alarm(self, request):
            return web.json_response({'code':200,'data':None})

        async def greeting(self, request):
            (runtime/'hardware-greeting.json').write_text(json.dumps(dict(
                at=time.time(), ip=request.remote, downloaded=True)),encoding='utf-8')
            return web.FileResponse(runtime.parent/'hardware/greeting.jpg')

        async def next_image(self, request):
            return web.json_response({'code':200,'data':'http://192.168.16.73:8003/hardware/greeting.jpg'})

        async def screen_capture(self, request):
            if request.remote != '192.168.16.22':
                raise web.HTTPForbidden()
            reader = await request.multipart()
            field = await reader.next()
            if field is None or field.name != 'file':
                raise web.HTTPBadRequest()
            content = bytearray()
            while chunk := await field.read_chunk():
                content.extend(chunk)
                if len(content) > 1024 * 1024:
                    raise web.HTTPRequestEntityTooLarge(max_size=1024*1024, actual_size=len(content))
            if not content.startswith(b'\xff\xd8'):
                raise web.HTTPBadRequest()
            target = runtime.parent/'hardware/screen-latest.jpg'
            target.write_bytes(content)
            return web.json_response({'ok': True})

        async def start(self):
            config = self.config['server']
            application = web.Application()
            application.add_routes([
                web.get('/xiaozhi/ota/',self.ota_handler.handle_get),
                web.post('/xiaozhi/ota/',self.ota),
                web.options('/xiaozhi/ota/',self.ota_handler.handle_options),
                web.get('/xiaozhi/ota/download/{filename}',self.ota_handler.handle_download),
                web.route('*','/GetXConfig',self.xconfig),
                web.get('/GetNextAlarm',self.no_alarm),
                web.get('/hardware/greeting.jpg',self.greeting),
                web.post('/hardware/screen-capture',self.screen_capture),
                web.get('/GetNextImage',self.next_image),
                web.get('/GetPrevImage',self.next_image),
                web.get('/mcp/vision/explain',self.vision_handler.handle_get),
                web.post('/mcp/vision/explain',self.vision_handler.handle_post),
                web.options('/mcp/vision/explain',self.vision_handler.handle_options),
            ])
            runner=web.AppRunner(application)
            await runner.setup()
            try:
                await web.TCPSite(runner,config.get('ip','0.0.0.0'),int(config.get('http_port',8003))).start()
                await asyncio.Future()
            finally:
                await runner.cleanup()

    app_module.SimpleHttpServer=CompatibleHttpServer
