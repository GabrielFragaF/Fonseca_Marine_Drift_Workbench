"""Restore inherited worker pipes in the Windows GUI executable."""
import os
import sys

if sys.platform == "win32":
    import ctypes
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [ctypes.c_ulong]
    kernel.GetStdHandle.restype = ctypes.c_void_p
    for name, handle_id in (("stdin", -10), ("stdout", -11), ("stderr", -12)):
        if getattr(sys, name) is None:
            handle = kernel.GetStdHandle(handle_id & 0xFFFFFFFF)
            try:
                if not handle or handle == ctypes.c_void_p(-1).value:
                    raise OSError("No inherited pipe")
                mode = "r" if name == "stdin" else "w"
                fd = msvcrt.open_osfhandle(handle, os.O_RDONLY if name == "stdin" else os.O_WRONLY)
                stream = os.fdopen(fd, mode, encoding="utf-8", buffering=1)
            except OSError:
                stream = open(os.devnull, "r" if name == "stdin" else "w", encoding="utf-8")
            setattr(sys, name, stream)

if getattr(sys, "frozen", False):
    from pathlib import Path

    base = Path(sys._MEIPASS)
    for name, relative in (("PROJ_DATA", "proj"), ("GDAL_DATA", "gdal")):
        if (base / relative).is_dir():
            os.environ[name] = str(base / relative)
