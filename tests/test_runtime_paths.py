from xray_text_forensics.runtime.context import _file_uri_to_path


def test_windows_drive_file_uri_drops_uri_leading_slash() -> None:
    path = _file_uri_to_path(
        "file:///C:/Users/Alice/AppData/Local/XRay%20Texts/evidence.txt",
        windows=True,
    )
    assert path.as_posix() == "C:/Users/Alice/AppData/Local/XRay Texts/evidence.txt"


def test_windows_unc_file_uri_preserves_host() -> None:
    path = _file_uri_to_path(
        "file://forensic-server/share/case/evidence.txt",
        windows=True,
    )
    assert path.as_posix() == "//forensic-server/share/case/evidence.txt"


def test_posix_file_uri_remains_absolute() -> None:
    path = _file_uri_to_path(
        "file:///var/lib/xray/evidence%20store/item.txt",
        windows=False,
    )
    assert path.as_posix() == "/var/lib/xray/evidence store/item.txt"
