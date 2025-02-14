# 2022-10-15 by jd3096 vx:jd3096
# 2024-12-26 rewrite by 五月
# 2025-02-13 basically a complete rewrite by DuoDuoJuZi

"""
    网易云获取歌词，需手动获取基址与四级偏移
"""

import pymem
import time
import win32process
from win32con import PROCESS_ALL_ACCESS
import win32api
import ctypes
from win32gui import FindWindow


class MemoryReader:
    def __init__(self):
        self._process_handle = None
        self._kernel32 = ctypes.windll.kernel32

    def open_process(self, pid):
        self._process_handle = win32api.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not self._process_handle:
            raise RuntimeError(f"打开进程失败，PID: {pid}")

    def close(self):
        if self._process_handle:
            win32api.CloseHandle(self._process_handle)

    def read_uint64(self, address):
        if not self._process_handle:
            raise RuntimeError("进程未打开")

        buffer = ctypes.c_uint64()
        bytes_read = ctypes.c_size_t()

        if address > 0x7FFFFFFFFFFF or address < 0x10000:
            raise ValueError(f"可疑地址值: 0x{address:X}")

        success = self._kernel32.ReadProcessMemory(
            int(self._process_handle),
            ctypes.c_void_p(address),
            ctypes.byref(buffer),
            ctypes.sizeof(ctypes.c_uint64),
            ctypes.byref(bytes_read)
        )

        if not success or bytes_read.value != 8:
            error = ctypes.GetLastError()
            raise RuntimeError(f"读取地址 0x{address:X} 失败 [Error {error}]")

        return buffer.value


def get_module_base(process, module_name):
    for module in process.list_modules():
        if module.name.lower() == module_name.lower():
            return module.lpBaseOfDll
    raise RuntimeError(f"未找到模块: {module_name}")


def resolve_pointer_chain(mem_reader, base, offsets):
    current_addr = base
    for offset in offsets:
        current_addr = mem_reader.read_uint64(current_addr + offset)
    return current_addr


def main():
    mem_reader = None
    pm = None
    last_lyric = ""

    try:
        # 初始化内存读取器
        mem_reader = MemoryReader()

        # 获取窗口句柄
        if (hwnd := FindWindow("DesktopLyrics", "桌面歌词")) == 0:
            raise RuntimeError("未找到桌面歌词窗口")

        # 获取进程信息
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        mem_reader.open_process(pid)

        # 附加到云音乐进程
        pm = pymem.Pymem("cloudmusic.exe")

        # 获取模块基址
        base_addr = get_module_base(pm, "cloudmusic.dll")

        # 定义指针链偏移（需要实际调试获取！！！！！！！）
        pointer_chain = [
            0x01A52400,  # 模块基址偏移
            0xE8,  # 第二级偏移
            0x38,  # 第三级偏移
            0x120,  # 第四级偏移
            0x18  # 最终偏移
        ]

        # 解析指针链
        final_addr = resolve_pointer_chain(mem_reader, base_addr, pointer_chain)
        print(f"[系统] 歌词指针初始化完成 (0x{final_addr:X})")

        # 歌词刷新循环
        while True:
            try:
                # 读取歌词数据（增大缓冲区防止截断）
                raw_bytes = pm.read_bytes(final_addr, 512)

                # 查找有效终止符（兼容单双空字节）
                terminator_pos = -1
                for i in range(0, len(raw_bytes) - 1, 2):
                    if raw_bytes[i] == 0 and raw_bytes[i + 1] == 0:
                        terminator_pos = i
                        break

                # 截取有效歌词部分
                lyric = raw_bytes[:terminator_pos] if terminator_pos != -1 else raw_bytes

                # 移除末尾单个空字节（保证偶数长度）
                if len(lyric) % 2 != 0:
                    lyric = lyric[:-1]

                # 解码处理（严格模式）
                try:
                    decoded = lyric.decode('utf-16-le', errors='strict').strip()
                except UnicodeDecodeError:
                    # 宽松模式解码并标记错误
                    decoded = lyric.decode('utf-16-le', errors='replace').strip() + ' [解码错误]'

                # 显示处理（保留所有空格）
                display_str = decoded.replace('\u3000', ' ')  # 全角转半角空格

                # 仅当内容变化时更新显示
                if display_str != last_lyric and display_str:
                    # 清空行 + 显示歌词（保留原始空格）
                    print(f"\r\x1b[K🎵 {display_str}", end='', flush=True)
                    last_lyric = display_str

                time.sleep(0.1)

            except KeyboardInterrupt:
                print("\n\n[系统] 终止监听")
                break
            except Exception as e:
                print(f"\n[警告] 临时读取失败 ({str(e)})")
                time.sleep(1)

    except Exception as e:
        print(f"\n[错误] 致命错误: {str(e)}")
    finally:
        if mem_reader:
            mem_reader.close()
        if pm:
            pm.close_process()
        print("\x1b[K")  # 清空最后一行


if __name__ == "__main__":
    main()