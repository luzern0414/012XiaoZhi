"""Deterministic voice commands, session gating and verified device operations."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time


@dataclass(frozen=True)
class Command:
    kind: str
    value: int | None = None


@dataclass(frozen=True)
class Outcome:
    text: str
    ok: bool = True
    speech: bool = True


def _number(text):
    text = text.removeprefix('百分之').removesuffix('%')
    if re.fullmatch(r'-?\d{1,4}', text):
        return int(text)
    digits = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
              '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
    if not text or not all(c in digits or c in '十百千' for c in text):
        return None
    total = current = 0
    for char in text:
        if char in digits:
            current = digits[char]
        else:
            total += (current or 1) * {'十': 10, '百': 100, '千': 1000}[char]
            current = 0
    return total + current


def parse_command(text: str) -> Command | None:
    # Full utterances only: negations, quoted commands and discussion cannot execute.
    if not isinstance(text, str) or len(text) > 100:
        return None
    value = re.sub(r'[\s，,。！？!?；;]', '', text)
    value = re.sub(r'^(?:你好小智|小智)?(?:请|帮我|麻烦)?', '', value, count=1)
    exact = {
        '打开语音助手': 'assistant_on', '开启语音助手': 'assistant_on',
        '启动语音助手': 'assistant_on', '关闭语音助手': 'assistant_off',
        '停止语音助手': 'assistant_off', '进入待机': 'assistant_off',
        '语音助手待机': 'assistant_off', '语音助手状态': 'assistant_state',
        '静音': 'mute', '关闭声音': 'mute', '取消静音': 'unmute',
        '恢复声音': 'unmute', '恢复音量': 'unmute',
        '小声一点': 'volume_down', '大声一点': 'volume_up',
        '低音量': 'volume_down',
        '当前音量是多少': 'volume_query', '现在音量多少': 'volume_query',
        '音量是多少': 'volume_query', '查询音量': 'volume_query', '声音多大': 'volume_query',
        '当前亮度是多少': 'brightness_query', '查询亮度': 'brightness_query',
        '设备状态': 'status', '查询设备状态': 'status',
        '网络状态': 'network', '查看网络状态': 'network', '查询网络信息': 'network',
        '读取网络信息': 'network', '现在连的什么网络': 'network',
        '电量多少': 'battery', '还剩多少电': 'battery', '查询电量': 'battery',
        '设备信息': 'system', '读取设备信息': 'system', '固件版本': 'system',
        '重启设备': 'reboot_request', '确认重启设备': 'reboot_confirm',
        '取消重启': 'cancel', '重新配网': 'wifi_setup', '配置网络': 'wifi_setup',
        '关机': 'power_off', '关闭设备': 'power_off', '开机': 'power_on',
        '控制帮助': 'help', '设备控制帮助': 'help',
    }
    if value in exact:
        kind = exact[value]
        if kind in ('volume_down', 'volume_up'):
            return Command('volume_step', -10 if kind == 'volume_down' else 10)
        return Command(kind)
    for label, kind in [('(?:音量|声音)', 'volume_set'), ('(?:屏幕亮度|亮度)', 'brightness_set')]:
        match = re.fullmatch(r'(?:把)?' + label + r'(?:调到|调成|设置为|设为)(.+)', value)
        if match:
            number = _number(match[1])
            return Command(kind, number) if number is not None else None
    match = re.fullmatch(r'(?:把)?(?:音量|声音)(?:调)?(大|小|高|低)一点', value)
    if match:
        return Command('volume_step', 10 if match[1] in ('大', '高') else -10)
    match = re.fullmatch(r'(?:把)?(?:音量|声音)(提高|调高|增加|降低|调低|减小)(?:一点)?', value)
    if match:
        return Command('volume_step', 10 if match[1] in ('提高', '调高', '增加') else -10)
    match = re.fullmatch(r'(?:把)?(提高|调高|增加|降低|调低|减小)(?:音量|声音)(.*)', value)
    if match:
        number = 10 if match[2] in ('', '一点') else _number(match[2])
        if number is not None:
            return Command('volume_step', number if match[1] in ('提高', '调高', '增加') else -number)
    match = re.fullmatch(r'(?:把)?(?:音量|声音)(提高|调高|增加|降低|调低|减小)(.+)', value)
    if match:
        number = _number(match[2])
        if number is not None:
            return Command('volume_step', number if match[1] in ('提高', '调高', '增加') else -number)
    return None


class AssistantGate:
    """Activation never survives a new connection or process restart."""
    def __init__(self, idle_seconds=90):
        self.idle_seconds = idle_seconds
        self.enabled = False
        self.last_activity = 0.0

    def expire(self, now=None):
        now = time.monotonic() if now is None else now
        if self.enabled and now - self.last_activity >= self.idle_seconds:
            self.enabled = False
            return True
        return False

    def route(self, command, now=None):
        now = time.monotonic() if now is None else now
        self.expire(now)
        kind = command.kind if command else None
        if kind == 'assistant_off':
            self.enabled = False
            return 'disable'
        if kind == 'assistant_on':
            self.enabled, self.last_activity = True, now
            return 'enable'
        if kind == 'assistant_state':
            return 'state'
        if not self.enabled:
            return 'ignore'
        self.last_activity = now
        return 'command' if command else 'chat'


def _object(raw):
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise ValueError('Device did not return an object')
    return raw


def _integer(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r'\d{1,3}', value):
        return int(value)
    return None


def _part(data, name):
    value = data.get(name, {})
    return value if isinstance(value, dict) else {}


class DeviceController:
    """Only invoke advertised, explicitly selected tools on the same device session."""
    def __init__(self, tools, call):
        self.tools, self.call = tools, call
        self.previous_volume = None
        self.pending_reboot = None

    def has(self, name):
        return any(t.get('name') == name for t in self.tools().values())

    async def _call(self, name, arguments=None):
        if not self.has(name):
            raise LookupError(name)
        return await self.call(name, arguments or {})

    async def _status(self):
        return _object(await self._call('self.get_device_status'))

    async def _level(self, kind, target=None, step=None, restore=False):
        if target is not None and not 0 <= target <= 100:
            return Outcome('数值需要在 0 到 100 之间，请重新指定。', False)
        if step is not None and not -100 <= step <= 100:
            return Outcome('每次音量调整幅度需要在 0 到 100 之间。', False)
        status = await self._status()
        section, label = ('audio_speaker', '音量') if kind == 'volume' else ('screen', '屏幕亮度')
        current = _integer(_part(status, section).get(kind))
        if current is None or not 0 <= current <= 100:
            return Outcome(f'设备没有返回有效的{label}，本次没有修改。', False)
        if restore:
            if current > 0:
                return Outcome(f'当前没有静音，音量是 {current}%。')
            if self.previous_volume is None:
                return Outcome('没有可恢复的音量记录，请直接说音量调到百分之五十。', False, False)
            target = self.previous_volume
        elif step is not None:
            target = max(0, min(100, current + step))
        if target is None:
            return Outcome(f'当前{label}是 {current}%。', speech=current != 0 or kind != 'volume')
        name = 'self.audio_speaker.set_volume' if kind == 'volume' else 'self.screen.set_brightness'
        if target != current:
            result = await self._call(name, {kind: target})
            if result is False or (isinstance(result, str) and result.strip() == 'false'):
                return Outcome(f'设备拒绝了{label}设置。', False)
            readback = await self._status()
            actual = _integer(_part(readback, section).get(kind))
            if actual != target:
                return Outcome(f'{label}设置尚未确认，设备读回值是 {actual}。', False)
        if kind == 'volume':
            if target == 0 and current > 0:
                self.previous_volume = current
            elif target > 0:
                self.previous_volume = target
        return Outcome(f'{label}已设置为 {target}%。', speech=not (kind == 'volume' and target == 0))

    async def execute(self, command, now=None):
        now = time.monotonic() if now is None else now
        kind = command.kind
        if kind not in ('reboot_request', 'reboot_confirm'):
            self.pending_reboot = None
        try:
            if kind in ('volume_set', 'volume_step', 'volume_query', 'mute', 'unmute'):
                return await self._level('volume',
                    target=command.value if kind == 'volume_set' else (0 if kind == 'mute' else None),
                    step=command.value if kind == 'volume_step' else None, restore=kind == 'unmute')
            if kind in ('brightness_set', 'brightness_query'):
                return await self._level('brightness', target=command.value)
            if kind == 'system':
                data = _object(await self._call('self.get_system_info'))
                version = _part(data, 'application').get('version')
                chip = data.get('chip_model_name')
                parts = [f'固件版本 {str(version)[:32]}' if version else '',
                         f'芯片 {str(chip)[:32]}' if chip else '']
                return Outcome('；'.join(p for p in parts if p) or '设备未返回固件和芯片信息。', bool(version or chip))
            if kind in ('status', 'network', 'battery'):
                data = await self._status()
                parts = []
                if kind in ('status', 'network'):
                    network = _part(data, 'network')
                    for field, label in [('ssid', '网络'), ('ip', 'IP'), ('rssi', '信号强度')]:
                        if network.get(field) is not None:
                            parts.append(f'{label} {str(network[field])[:48]}')
                    signal = {'strong': '强', 'medium': '中等', 'weak': '弱'}.get(network.get('signal'))
                    if signal:
                        parts.append(f'信号{signal}')
                if kind in ('status', 'battery'):
                    battery = _part(data, 'battery')
                    level = _integer(battery.get('level'))
                    if level is not None and 0 <= level <= 100:
                        parts.append(f'电量 {level}%' + ('，正在充电' if battery.get('charging') is True else ''))
                if kind == 'status':
                    volume = _integer(_part(data, 'audio_speaker').get('volume'))
                    if volume is not None and 0 <= volume <= 100:
                        parts.insert(0, f'音量 {volume}%')
                return Outcome('；'.join(parts) + '。' if parts else '设备没有返回这项信息。', bool(parts))
            if kind == 'reboot_request':
                if not self.has('self.reboot'):
                    raise LookupError('self.reboot')
                self.pending_reboot = now + 15
                return Outcome('重启会中断当前连接。请在十五秒内说“确认重启设备”，或说“取消重启”。')
            if kind == 'reboot_confirm':
                deadline, self.pending_reboot = self.pending_reboot, None
                if deadline is None or now >= deadline:
                    return Outcome('没有待确认的重启请求，或确认已过期。', False)
                result = await self._call('self.reboot')
                if result is False or result == 'false':
                    return Outcome('设备拒绝了重启请求。', False, False)
                return Outcome('设备已接受重启请求，重连后语音助手将处于待机。', speech=False)
            if kind == 'cancel':
                return Outcome('已取消待确认的操作。')
            if kind == 'wifi_setup':
                return Outcome('当前固件没有已验证的语音配网接口。请使用设备原厂配网模式；本次没有修改或清空网络。', False)
            if kind == 'power_off':
                return Outcome('当前固件没有已验证的断电关机接口。可以说关闭语音助手进入待机。', False)
            if kind == 'power_on':
                return Outcome('设备已经通电。完全断电后需要按键或重新供电开机。', False)
            if kind == 'help':
                return Outcome('可说：音量调到五十、声音大一点、静音、取消静音、网络状态、设备状态、读取设备信息、重启设备、关闭语音助手。')
            return Outcome('这条设备指令暂不支持。', False)
        except LookupError:
            return Outcome('当前设备没有公布所需控制接口，本次没有执行操作。', False)
        except Exception:
            # Never speak/log arbitrary device payloads, credentials or transport errors.
            return Outcome('设备没有返回有效确认，请保持设备联网后重试。', False)
