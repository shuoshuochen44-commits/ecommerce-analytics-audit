"""One native window per workspace, without changing existing browser services."""

import ctypes
import hashlib
import json
import os
from pathlib import Path
from ctypes import wintypes

TITLE='智数巡检'


class DesktopInstance:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.record=self.root/'desktop-window.json'
        self.handle=None
        self.acquired=False

    def __enter__(self):
        key=hashlib.sha256(os.path.normcase(str(self.root)).encode()).hexdigest()
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.argtypes=(ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR)
        kernel.CreateMutexW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
        kernel.CloseHandle.restype=wintypes.BOOL
        self.kernel=kernel
        self.handle=kernel.CreateMutexW(None,False,'Local\\ZhishuDesktop-'+key)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        self.acquired=ctypes.get_last_error()!=183
        return self

    def remember(self,window_handle):
        if not self.acquired:return
        self.root.mkdir(parents=True,exist_ok=True)
        self.record.write_text(json.dumps({'pid':os.getpid(),'hwnd':int(window_handle)}),encoding='utf-8')

    def activate(self):
        try:
            record=json.loads(self.record.read_text(encoding='utf-8'))
            user=ctypes.WinDLL('user32',use_last_error=True)
            user.GetWindowThreadProcessId.argtypes=(wintypes.HWND,ctypes.POINTER(wintypes.DWORD))
            user.GetWindowTextW.argtypes=(wintypes.HWND,wintypes.LPWSTR,ctypes.c_int)
            user.ShowWindow.argtypes=(wintypes.HWND,ctypes.c_int)
            user.SetForegroundWindow.argtypes=(wintypes.HWND,)
            hwnd=record['hwnd'];pid=wintypes.DWORD();title=ctypes.create_unicode_buffer(256)
            user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            user.GetWindowTextW(hwnd,title,256)
            if pid.value!=record['pid'] or title.value!=TITLE:return False
            user.ShowWindow(hwnd,9)
            return bool(user.SetForegroundWindow(hwnd))
        except (OSError,ValueError,KeyError,TypeError):
            return False

    def __exit__(self,*_):
        if self.acquired:self.record.unlink(missing_ok=True)
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle=None
