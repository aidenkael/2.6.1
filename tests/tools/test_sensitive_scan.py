from tools.sensitive_scan import main


def test_repository_sensitive_scan_passes():
    assert main() == 0
