"""Keep a complete answer visible after firmware changes its audio state."""
from __future__ import annotations
import asyncio
import json


class DisplaySocket:
    def __init__(self, socket, owner, delay=.25):
        self.socket, self.owner, self.delay = socket, owner, delay
        self.turn = None
        self.text = ''
        self.repaint = None

    def __getattr__(self, name):
        return getattr(self.socket, name)

    def __aiter__(self):
        return self.socket.__aiter__()

    async def send(self, message, *args, **kwargs):
        await self.socket.send(message, *args, **kwargs)
        if not isinstance(message, str):
            return
        try:
            event = json.loads(message)
        except (ValueError, TypeError):
            return
        if not isinstance(event, dict) or event.get('type') != 'tts':
            return
        owner = self.owner
        turn = (owner.sentence_id, owner.control_generation)
        if self.turn != turn:
            self.turn, self.text = turn, ''
        if event.get('state') == 'sentence_start' and event.get('text'):
            text = event['text']
            # Controls pre-send their complete sentence; TTS repeats its segments.
            complete = getattr(owner, 'control_display_text', None)
            if complete and complete[0] == owner.sentence_id:
                self.text = complete[1]
            else:
                self.text = (self.text + text)[-4000:]
        elif event.get('state') == 'stop' and self.text:
            if self.repaint:
                self.repaint.cancel()
            self.repaint = asyncio.create_task(self._redraw(turn, self.text))

    async def _redraw(self, turn, text):
        await asyncio.sleep(self.delay)
        owner = self.owner
        if owner.control_gate.enabled and turn == (owner.sentence_id, owner.control_generation):
            try:
                # Text only: never restart audio or pretend the microphone stopped.
                await self.socket.send(json.dumps(dict(type='tts', state='sentence_start',
                    text=text, session_id=owner.session_id), ensure_ascii=False))
                capture = getattr(owner, '_capture_answer_screen', None)
                if capture:
                    await capture()
            except Exception:
                pass

    async def finish(self):
        if self.repaint:
            self.repaint.cancel()
            await asyncio.gather(self.repaint, return_exceptions=True)
