"""Live acceptance: genuine model deltas, independent sessions, and cancellation."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
import time
import websockets
from protocol_activation import activate

ROOT=Path(__file__).resolve().parents[1]
URL='ws://127.0.0.1:8000/xiaozhi/v1/'


async def check(name,question,cancel=False):
    async with websockets.connect(URL,additional_headers={'device-id':'stream-check-'+name,
                    'client-id':'stream-acceptance'},open_timeout=10) as ws:
        await ws.send(json.dumps(dict(type='hello',version=1,transport='websocket',
            features={'text_stream':True,'emoji':False},
            audio_params=dict(format='opus',sample_rate=24000,channels=1,frame_duration=60))))
        hello=json.loads(await ws.recv());assert hello['type']=='hello'
        await asyncio.sleep(3)
        await activate(ws)
        await ws.send(json.dumps(dict(type='listen',state='detect',text=question)))
        events=[];began=time.monotonic();first=None;turn=None;stopped=False
        while time.monotonic()-began<75:
            item=await asyncio.wait_for(ws.recv(),30)
            if isinstance(item,bytes):continue
            e=json.loads(item)
            if e.get('type')=='text_stream':
                events.append(e)
                turn=turn or e['request_id'];assert turn==e['request_id']
                if e['state']=='delta' and first is None:
                    first=round(time.monotonic()-began,3)
                    if cancel:await ws.send(json.dumps(dict(type='abort')))
            if e.get('type')=='tts' and e.get('state')=='stop':
                stopped=True;break
        assert stopped and first is not None
        if cancel:
            # A queued send may precede abort handling; none may follow the stop acknowledgement.
            until=time.monotonic()+1
            while time.monotonic()<until:
                try:item=await asyncio.wait_for(ws.recv(),.3)
                except asyncio.TimeoutError:continue
                if isinstance(item,str):
                    e=json.loads(item)
                    assert not (e.get('type')=='text_stream' and e.get('state')=='delta')
        else:
            assert [e['state'] for e in events][0]=='start'
            assert events[-1]['state']=='end'
        result=dict(name=name,request_id=turn,first_delta_seconds=first,
            chunks=sum(e['state']=='delta' for e in events),
            text=''.join(e.get('text','') for e in events if e['state']=='delta'),cancelled=cancel)
        print(json.dumps(result,ensure_ascii=False),flush=True)
        return result


async def main():
    results=await asyncio.gather(check('fruit','请只列举六种水果名称，每种单独一行。'),
                                 check('math','请用一句简短的话回答，三加四等于几？'))
    assert results[0]['request_id']!=results[1]['request_id']
    assert results[0]['chunks']>1
    results.append(await check('cancel','请写一篇三百字的春游故事。',True))
    (ROOT/'data/acceptance/streaming.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: real streaming, separate sessions and cancellation')


if __name__=='__main__':asyncio.run(main())
