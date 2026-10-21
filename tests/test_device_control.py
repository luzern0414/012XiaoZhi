import asyncio
import json
import pytest

from src.device_control import AssistantGate, DeviceController, parse_command


@pytest.mark.parametrize('text,kind,value', [
    ('小智，请打开语音助手。', 'assistant_on', None),
    ('关闭语音助手', 'assistant_off', None),
    ('进入待机', 'assistant_off', None),
    ('音量调到百分之五十', 'volume_set', 50),
    ('把声音设置为30%', 'volume_set', 30),
    ('声音大一点', 'volume_step', 10),
    ('小声一点。', 'volume_step', -10),
    ('大声一点', 'volume_step', 10),
    ('调低音量', 'volume_step', -10),
    ('低音量。', 'volume_step', -10),
    ('请把音量调小一点', 'volume_step', -10),
    ('音量调低一点', 'volume_step', -10),
    ('把声音调高', 'volume_step', 10),
    ('调低音量二十', 'volume_step', -20),
    ('把音量降低二十', 'volume_step', -20),
    ('静音', 'mute', None),
    ('取消静音', 'unmute', None),
    ('当前音量是多少', 'volume_query', None),
    ('屏幕亮度调到六十', 'brightness_set', 60),
    ('网络状态', 'network', None),
    ('读取设备信息', 'system', None),
    ('重新配网', 'wifi_setup', None),
    ('关机', 'power_off', None),
    ('确认重启设备', 'reboot_confirm', None),
])
def test_explicit_commands(text, kind, value):
    command = parse_command(text)
    assert command.kind == kind
    assert command.value == value


@pytest.mark.parametrize('text', [
    '不要打开语音助手', '为什么要关闭语音助手', '他说音量调到五十',
    '写一篇关于重启设备的故事', '如果我说打开语音助手会怎样',
    '“打开语音助手”', '音量大一点是什么含义', '请不要关机',
    '不要小声一点', '为什么不能调低音量', '他说调低音量',
])
def test_discussion_and_negation_are_not_commands(text):
    assert parse_command(text) is None


def test_default_standby_expiration_and_reconnect():
    gate = AssistantGate(idle_seconds=90)
    assert gate.route(None, 0) == 'ignore'
    assert gate.route(parse_command('打开语音助手'), 1) == 'enable'
    assert gate.route(None, 80) == 'chat'
    assert gate.route(None, 171) == 'ignore'
    assert not gate.enabled
    assert AssistantGate().route(None, 172) == 'ignore'


def test_close_immediately_blocks_chat_and_commands():
    gate = AssistantGate()
    gate.route(parse_command('打开语音助手'), 1)
    assert gate.route(parse_command('关闭语音助手'), 2) == 'disable'
    assert gate.route(parse_command('声音大一点'), 3) == 'ignore'


class Device:
    def __init__(self, change=True):
        self.volume = 42
        self.change = change
        self.calls = []
        self.tools = {name: {'name': name, 'inputSchema': {}} for name in (
            'self.get_device_status', 'self.audio_speaker.set_volume',
            'self.screen.set_brightness', 'self.get_system_info', 'self.reboot')}

    async def call(self, name, args):
        self.calls.append((name, args))
        if name == 'self.get_device_status':
            return json.dumps({'audio_speaker': {'volume': self.volume},
                'network': {'ssid': 'Test WiFi', 'signal': 'strong', 'password': 'NEVER-READ'},
                'battery': {'level': 81, 'charging': True}})
        if name == 'self.audio_speaker.set_volume' and self.change:
            self.volume = args['volume']
        if name == 'self.get_system_info':
            return json.dumps({'application': {'version': '2.0.3.3'},
                'chip_model_name': 'esp32s3', 'secret': 'NEVER-READ'})
        return 'true'

    def controller(self):
        return DeviceController(lambda: self.tools, self.call)


def run(controller, text, now=0):
    return asyncio.run(controller.execute(parse_command(text), now=now))


def test_relative_volume_reads_before_and_after_and_clamps():
    device = Device()
    device.volume = 95
    result = run(device.controller(), '声音大一点')
    assert result.ok and '100' in result.text
    assert device.calls == [
        ('self.get_device_status', {}),
        ('self.audio_speaker.set_volume', {'volume': 100}),
        ('self.get_device_status', {})]


@pytest.mark.parametrize('text', ['小声一点。', '调低音量。'])
def test_field_observed_phrases_change_actual_device_volume(text):
    device = Device()
    result = run(device.controller(), text)
    assert result.ok and device.volume == 32 and '32%' in result.text
    assert device.calls[-2:] == [('self.audio_speaker.set_volume', {'volume': 32}),
                                ('self.get_device_status', {})]


def test_unverified_volume_does_not_claim_success():
    device = Device(change=False)
    result = run(device.controller(), '音量调到五十')
    assert not result.ok
    assert '42' in result.text


def test_invalid_absolute_volume_never_writes():
    device = Device()
    result = run(device.controller(), '音量调到两百')
    assert not result.ok
    assert not device.calls


def test_mute_remembers_real_volume_and_unmute_restores():
    device = Device()
    controller = device.controller()
    muted = run(controller, '静音')
    assert muted.ok and not muted.speech and device.volume == 0
    restored = run(controller, '取消静音')
    assert restored.ok and device.volume == 42
    assert not any('NEVER-READ' in x.text for x in (muted, restored))


def test_unmute_without_known_previous_volume_does_not_guess():
    device = Device()
    device.volume = 0
    result = run(device.controller(), '取消静音')
    assert not result.ok
    assert all(name != 'self.audio_speaker.set_volume' for name, _ in device.calls)


def test_network_summary_never_reads_password_or_full_payload():
    result = run(Device().controller(), '网络状态')
    assert result.ok and 'Test WiFi' in result.text
    assert 'NEVER-READ' not in result.text and 'password' not in result.text


def test_system_summary_uses_firmware_field_not_protocol_version():
    result = run(Device().controller(), '读取设备信息')
    assert '2.0.3.3' in result.text and 'esp32s3' in result.text
    assert 'NEVER-READ' not in result.text


def test_reboot_requires_unexpired_confirmation():
    device = Device()
    controller = device.controller()
    assert not run(controller, '确认重启设备', 0).ok
    assert not device.calls
    assert run(controller, '重启设备', 1).ok
    assert not device.calls
    assert not run(controller, '确认重启设备', 17).ok
    run(controller, '重启设备', 20)
    assert run(controller, '确认重启设备', 21).ok
    assert device.calls == [('self.reboot', {})]


def test_unrelated_request_invalidates_reboot_confirmation():
    device = Device()
    controller = device.controller()
    run(controller, '重启设备', 1)
    run(controller, '网络状态', 2)
    assert not run(controller, '确认重启设备', 3).ok
    assert not any(name == 'self.reboot' for name, _ in device.calls)


@pytest.mark.parametrize('text', ['关机', '开机', '重新配网'])
def test_unsupported_power_and_wifi_never_reboot_or_erase(text):
    device = Device()
    result = run(device.controller(), text)
    assert not result.ok and not device.calls


def test_missing_tool_and_rpc_failure_are_explicit():
    device = Device()
    device.tools.clear()
    assert not run(device.controller(), '声音大一点').ok
    async def unavailable(name, args):
        raise TimeoutError('PRIVATE-DATA')
    result = run(DeviceController(lambda: Device().tools, unavailable), '当前音量是多少')
    assert not result.ok and 'PRIVATE-DATA' not in result.text
