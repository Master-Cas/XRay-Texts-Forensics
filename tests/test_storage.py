from xray_text_forensics.storage import ContentAddressedStore


def test_content_store_is_idempotent(tmp_path) -> None:
    store = ContentAddressedStore(tmp_path)
    first = store.put_bytes("artifacts", b"forensic bytes")
    second = store.put_bytes("artifacts", b"forensic bytes")

    assert first.path == second.path
    assert first.sha256 == second.sha256
    assert store.read_bytes(first) == b"forensic bytes"
