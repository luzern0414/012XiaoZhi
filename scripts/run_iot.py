"""Authenticated local broker for the EchoEar vendor status/control extension."""
from __future__ import annotations
import asyncio
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import yaml
from passlib.apps import custom_app_context
from amqtt.broker import Broker

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'data/runtime'


async def main():
    path=ROOT/'config/local.iot.yaml'
    if not path.exists():
        path.write_text(yaml.safe_dump(dict(username='echoear',password=secrets.token_urlsafe(24))),encoding='utf-8')
    config=yaml.safe_load(path.read_text(encoding='utf-8'))
    password_file=RUNTIME/'iot-passwords'
    password_file.write_text(config['username']+':'+custom_app_context.hash(config['password'])+'\n',encoding='utf-8')
    broker=Broker({'listeners':{'default':{'type':'tcp','bind':'192.168.16.73:1883'}},
        'plugins':{'amqtt.plugins.authentication.FileAuthPlugin':{'password_file':str(password_file)}},
        'timeout_disconnect_delay':2})
    await broker.start()
    state=dict(pid=os.getpid(),runner=str(Path(__file__).resolve()),
               instance_id=sys.argv[1] if len(sys.argv)>1 else 'manual')
    (RUNTIME/'iot-process.json').write_text(json.dumps(state))
    print('EchoEar authenticated MQTT ready on WLAN port 1883',flush=True)
    try:
        while not (RUNTIME/'stop-iot').exists():
            devices=[dict(client_id=s.client_id,ip=s.remote_address,connected=True)
                     for s,_ in broker.sessions.values() if s.transitions.state=='connected'
                     and s.client_id=='echoear-90e5b1d6405c' and s.remote_address=='192.168.16.22']
            target=RUNTIME/'iot-state.json';temporary=target.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(at=__import__('time').time(),devices=devices,
                subscriptions=list(broker.subscriptions))))
            temporary.replace(target)
            await asyncio.sleep(1)
    finally:
        await broker.shutdown()
        (RUNTIME/'iot-state.json').unlink(missing_ok=True)
        (RUNTIME/'iot-process.json').unlink(missing_ok=True)


if __name__=='__main__':
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
