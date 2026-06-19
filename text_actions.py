"""Argument-aware actions for voice commands."""

import ctypes
import os
import subprocess
import time
import urllib.parse
import webbrowser


def _clean_text(text: str | None) -> str:
    return " ".join((text or "").strip().split())


def _set_clipboard(text: str) -> bool:
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
                input=text,
                text=True,
                capture_output=True,
                timeout=5,
            )
            if completed.returncode == 0:
                return True
        except Exception:
            pass

    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception as e:
        print(f"  [TextActions] Не удалось записать буфер обмена: {e}")
        return False


def _send_ctrl_v() -> bool:
    if not hasattr(ctypes, "WinDLL"):
        return False

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        keyeventf_keyup = 0x0002
        vk_control = 0x11
        vk_v = 0x56
        user32.keybd_event(vk_control, 0, 0, 0)
        user32.keybd_event(vk_v, 0, 0, 0)
        user32.keybd_event(vk_v, 0, keyeventf_keyup, 0)
        user32.keybd_event(vk_control, 0, keyeventf_keyup, 0)
        return True
    except Exception as e:
        print(f"  [TextActions] Не удалось вставить текст: {e}")
        return False


def open_notepad_and_write(text: str | None = "") -> tuple[str, bool]:
    text = _clean_text(text)
    if not text:
        return ("Не услышал текст для записи", False)

    try:
        subprocess.Popen(["notepad.exe"])
        time.sleep(0.8)
        if not _set_clipboard(text):
            return ("Не удалось подготовить текст", False)
        if not _send_ctrl_v():
            return ("Не удалось вставить текст в блокнот", False)
        return ("Записал текст в блокнот", True)
    except Exception as e:
        return (f"Ошибка блокнота: {e}", False)


def type_text(text: str | None = "") -> tuple[str, bool]:
    text = _clean_text(text)
    if not text:
        return ("Не услышал текст для ввода", False)

    if not _set_clipboard(text):
        return ("Не удалось подготовить текст", False)
    if not _send_ctrl_v():
        return ("Не удалось вставить текст", False)
    return ("Вставил текст", True)


def google_search(query: str | None = "") -> tuple[str, bool]:
    query = _clean_text(query)
    if not query:
        return ("Не услышал поисковый запрос", False)

    url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
    webbrowser.open(url)
    return (f"Ищу в Google: {query}", True)


def youtube_search(query: str | None = "") -> tuple[str, bool]:
    query = _clean_text(query)
    if not query:
        return ("Не услышал запрос для YouTube", False)

    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    webbrowser.open(url)
    return (f"Ищу на YouTube: {query}", True)
