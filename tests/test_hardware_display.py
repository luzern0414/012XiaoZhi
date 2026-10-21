import asyncio
import json
from types import SimpleNamespace

from src.hardware_display import DisplaySocket


def test_final_complete_answer_redraws_without_restarting_audio():
    async def run():
        sent=[]
        async def send(message):
            sent.append(json.loads(message))
        owner=SimpleNamespace(sentence_id='turn', control_generation=1,
            control_gate=SimpleNamespace(enabled=True), session_id='session',
            control_display_text=('turn', '当前音量是 70%。'))
        socket=DisplaySocket(SimpleNamespace(send=send), owner, delay=0)
        for state,text in [('start',None),('sentence_start','当前音量是 70%。'),
                ('sentence_start','当前音量是 70%'),('stop',None)]:
            await socket.send(json.dumps(dict(type='tts',state=state,text=text)))
        await asyncio.sleep(.01)
        assert sent[-1] == dict(type='tts',state='sentence_start',text='当前音量是 70%。',session_id='session')
        assert sum(e['state']=='start' for e in sent)==1
        await socket.finish()
    asyncio.run(run())


def test_repeated_model_fragments_are_not_removed_from_the_answer():
    async def run():
        sent=[]
        async def send(message):
            sent.append(json.loads(message))
        owner=SimpleNamespace(sentence_id='turn',control_generation=1,
            control_gate=SimpleNamespace(enabled=True),session_id='session')
        socket=DisplaySocket(SimpleNamespace(send=send),owner,delay=0)
        for state,text in [('sentence_start','你好'),('sentence_start','你好'),('stop',None)]:
            await socket.send(json.dumps(dict(type='tts',state=state,text=text)))
        await asyncio.sleep(.01)
        assert sent[-1]['text']=='你好你好'
        await socket.finish()
    asyncio.run(run())


def test_fragmented_answer_is_complete_and_old_turn_cannot_repaint_after_close():
    async def run():
        sent=[]
        async def send(message):
            sent.append(json.loads(message))
        owner=SimpleNamespace(sentence_id='turn',control_generation=1,
            control_gate=SimpleNamespace(enabled=True),session_id='session')
        socket=DisplaySocket(SimpleNamespace(send=send),owner,delay=.01)
        for state,text in [('sentence_start','一加一'),('sentence_start','等于二。'),('stop',None)]:
            await socket.send(json.dumps(dict(type='tts',state=state,text=text)))
        await asyncio.sleep(.03)
        assert sent[-1]['text']=='一加一等于二。'
        await socket.send(json.dumps(dict(type='tts',state='stop')))
        owner.control_generation=3
        count=len(sent)
        await asyncio.sleep(.03)
        assert len(sent)==count
        await socket.finish()
    asyncio.run(run())
