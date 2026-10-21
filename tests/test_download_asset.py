import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from download_asset import download


def test_verified_existing_asset_does_not_need_network(tmp_path, monkeypatch):
    target = tmp_path / 'model.pt'
    target.write_bytes(b'verified model')
    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    def reject_network(*args, **kwargs):
        raise AssertionError('A verified local asset must work offline')
    monkeypatch.setattr('urllib.request.urlopen', reject_network)
    assert download('https://unused.invalid/model.pt', target, expected) == expected
