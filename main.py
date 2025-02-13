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

        # 验证地址范围有效性（基础校验）
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
            if error == 299:  # 仅部分读取
                pass
            raise RuntimeError(f"读取地址 0x{address:X} 失败 [Error {error}]")

        return buffer.value


def get_module_base(process, module_name):
    for module in process.list_modules():
        if module.name.lower() == module_name.lower():
            print(f"[INFO] 找到模块 {module.name} 基址: 0x{module.lpBaseOfDll:X}")
            return module.lpBaseOfDll
    raise RuntimeError(f"未找到模块: {module_name}")


def resolve_pointer_chain(mem_reader, base, offsets):
    current_addr = base
    for idx, offset in enumerate(offsets, 1):
        try:
            current_addr = mem_reader.read_uint64(current_addr + offset)
            print(f"[DEBUG] Level {idx}: 0x{current_addr:X}")
        except Exception as e:
            raise RuntimeError(f"指针链解析失败于层级 {idx} (偏移 +0x{offset:X}): {str(e)}")
    return current_addr


def main():
    try:
        # 初始化内存读取器
        mem_reader = MemoryReader()

        # 获取窗口句柄
        hwnd = FindWindow("DesktopLyrics", u"桌面歌词")
        if hwnd == 0:
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
            0x18,  # 最终偏移
        ]

        # 解析指针链
        final_addr = resolve_pointer_chain(mem_reader, base_addr, pointer_chain)
        print(f"[SUCCESS] 最终歌词地址: 0x{final_addr:X}")

        # 歌词读取循环
        last_lyric = ""
        while True:
            try:
                # 获取歌词
                raw_bytes = pm.read_bytes(final_addr, 256)

                # 精确查找UTF-16终止符(0x0000)
                terminator_pos = raw_bytes.find(b'\x00\x00')
                if terminator_pos != -1:
                    # 包含终止符的情况下，截取到终止符位置
                    lyric = raw_bytes[:terminator_pos]
                else:
                    # 没有终止符时取全部内容（最多256字节）
                    lyric = raw_bytes

                # 移除可能存在的单个结尾null（奇数长度修正）
                if len(lyric) % 2 != 0:
                    lyric = lyric[:-1]

                # 解码时保留所有空格
                try:
                    decoded = lyric.decode('utf-16-le').strip()
                except UnicodeDecodeError:
                    # 遇到非法字符时使用替代策略
                    decoded = lyric.decode('utf-16-le', errors='replace').strip()

                # 显示处理（保留原始空格）
                display_str = decoded.replace('\u3000', ' ')  # 替换全角空格
                display_str = ' '.join(display_str.split())  # 合并连续空格但不删除单个空格

                if display_str != last_lyric:
                    # 清空行 + 显示歌词（最大显示80字符）
                    display = display_str[:80] + ('..' if len(display_str) > 80 else '')
                    print(f"\r\x1b[K🎵 {display}", end='', flush=True)
                    last_lyric = display_str

                time.sleep(0.01)

            except KeyboardInterrupt:
                print("\n终止进程")
                break

    except Exception as e:
        print(f"[FATAL] 发生错误: {str(e)}")
        exit(1)

    finally:
        mem_reader.close()
        if 'pm' in locals():
            pm.close_process()


if __name__ == "__main__":
    main()