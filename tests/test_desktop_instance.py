import sys

import pytest

from zhishu_inspection.desktop_instance import DesktopInstance

pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Windows native instance lock')


def test_same_workspace_can_only_have_one_native_owner(tmp_path):
    with DesktopInstance(tmp_path) as first:
        assert first.acquired
        with DesktopInstance(tmp_path) as second:assert not second.acquired
        with DesktopInstance(tmp_path/'different') as other:assert other.acquired
    with DesktopInstance(tmp_path) as reopened:assert reopened.acquired
