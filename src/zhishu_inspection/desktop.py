"""Desktop host: native window on the main thread, local data service in a worker."""

import argparse
import threading
from pathlib import Path

from .desktop_instance import DesktopInstance,TITLE
from .launcher import main as run_headless,prepare_workspace
from .resources import project_directory
from .server import create_server


class DesktopService:
    def __init__(self,root,port=0):
        self.server=create_server(root,port)
        self.url=f'http://127.0.0.1:{self.server.server_address[1]}/'
        self.window=None
        self.closing=threading.Event()
        self.thread=threading.Thread(target=self._serve,name='zhishu-desktop-http',daemon=True)
        self._closed=False

    def _serve(self):
        try:
            self.server.serve_forever(poll_interval=.1)
        finally:
            if self.window and not self.closing.is_set():
                try:self.window.destroy()
                except Exception:pass # A user may already have closed the native window.

    def start(self):self.thread.start()

    def stop(self):
        self.closing.set()
        if self.thread.is_alive():self.server.shutdown()

    def close(self):
        if self._closed:return
        self._closed=True
        self.stop()
        if self.thread.ident:self.thread.join(timeout=10)
        self.server.server_close()


def run_window(service,root,webview,instance=None):
    try:
        webview.settings['ALLOW_DOWNLOADS']=True
        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER']=False
        window=webview.create_window(TITLE,service.url,width=1280,height=860,min_size=(900,640),
                                     background_color='#f4f7f2',text_select=True)
        service.window=window
        window.events.closing+=lambda:service.closing.set()
        window.events.closed+=service.stop
        if instance:
            window.events.shown+=lambda:instance.remember(window.native.Handle.ToInt64())
        service.start()
        webview.start(gui='edgechromium',debug=False,private_mode=True,
                      storage_path=str(Path(root)/'desktop-profile'),
                      localization={'global.quit':'退出','global.cancel':'取消','global.saveFile':'保存文件',
                                    'global.openFile':'选择文件','global.saveFileError':'文件无法保存'})
    finally:
        service.close()


def launch_desktop(root,port=0):
    with DesktopInstance(root) as instance:
        if not instance.acquired:
            instance.activate()
            return
        import webview
        run_window(DesktopService(root,port),root,webview,instance)


def main(argv=None):
    parser=argparse.ArgumentParser(description=TITLE)
    parser.add_argument('--headless','--no-browser',dest='headless',action='store_true')
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--port',type=int)
    args=parser.parse_args(argv)
    root=args.data_dir.resolve() if args.data_dir else prepare_workspace(project_directory())
    if args.headless:
        options=['--no-browser']
        if args.port is not None:options+=['--port',str(args.port)]
        options+=['--data-dir',str(root)]
        return run_headless(options)
    return launch_desktop(root,args.port or 0)


if __name__=='__main__':main()
