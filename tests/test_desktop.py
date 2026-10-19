import json
import threading
import urllib.request
from types import SimpleNamespace

import pytest

from zhishu_inspection.desktop import DesktopService, run_window, main


class Event:
    def __init__(self):self.handlers=[]
    def __iadd__(self,handler):self.handlers.append(handler);return self
    def fire(self):
        for handler in self.handlers:handler()


class Window:
    def __init__(self):
        self.events=SimpleNamespace(closing=Event(),closed=Event())
        self.destroyed=threading.Event()
    def destroy(self):self.destroyed.set()


class View:
    def __init__(self,action):
        self.settings={};self.action=action;self.window=Window()
    def create_window(self,title,url,**kwargs):
        self.title=title;self.url=url;self.options=kwargs;return self.window
    def start(self,**kwargs):self.start_options=kwargs;self.action(self)


def test_native_window_close_stops_actual_backend_and_scheduler(tmp_path):
    service=DesktopService(tmp_path)
    def close_window(view):
        with urllib.request.urlopen(view.url+'api/sources') as response:
            assert json.load(response)['sources']==[]
        view.window.events.closing.fire()
        view.window.events.closed.fire()
    view=View(close_window)
    run_window(service,tmp_path,view)
    assert service.server.source_manager.stopped
    assert not service.thread.is_alive()
    with pytest.raises(OSError):urllib.request.urlopen(view.url+'api/health',timeout=.2)
    assert view.title=='智数巡检'
    assert view.settings['ALLOW_DOWNLOADS'] is True
    assert view.start_options['gui']=='edgechromium'
    assert view.options['min_size']==(900,640)


def test_native_renderer_start_failure_closes_backend(tmp_path):
    service=DesktopService(tmp_path)
    def fail(_):raise RuntimeError('renderer unavailable')
    with pytest.raises(RuntimeError,match='renderer unavailable'):
        run_window(service,tmp_path,View(fail))
    assert service.server.source_manager.stopped
    assert not service.thread.is_alive()


def test_exit_button_stops_server_and_closes_window(tmp_path):
    service=DesktopService(tmp_path)
    def exit_program(view):
        request=urllib.request.Request(view.url+'api/application/exit',data=b'{}',headers={'X-Zhishu-Local':'1'})
        with urllib.request.urlopen(request) as response:assert json.load(response)['stopped']
        assert view.window.destroyed.wait(3)
    run_window(service,tmp_path,View(exit_program))
    assert service.server.source_manager.stopped
    assert not service.thread.is_alive()


def test_headless_flag_retains_http_verification_entry_without_native_import(monkeypatch,tmp_path):
    import zhishu_inspection.desktop as desktop
    captured=[]
    monkeypatch.setattr(desktop,'run_headless',lambda args:captured.extend(args))
    main(['--no-browser','--port','8782','--data-dir',str(tmp_path)])
    assert captured==['--no-browser','--port','8782','--data-dir',str(tmp_path)]


def test_default_entry_does_not_launch_external_browser(monkeypatch,tmp_path):
    import zhishu_inspection.desktop as desktop
    calls=[]
    monkeypatch.setattr(desktop,'launch_desktop',lambda root,port:calls.append((root,port)))
    monkeypatch.setattr('webbrowser.open',lambda *_:pytest.fail('external browser opened'))
    main(['--data-dir',str(tmp_path)])
    assert calls==[(tmp_path.resolve(),0)]
