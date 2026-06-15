"""
Command Handler for Marci Agent
================================
Чистый обработчик голосовых команд.

- Читает команды из commands.json
- Ищет совпадение триггера в тексте
- Выполняет action как shell-команду (subprocess.Popen)
- Никаких хардкод-команд — всё только из JSON

Формат commands.json:
{
  "имя_команды": {
    "triggers": ["фраза 1", "фраза 2", ...],
    "action": "любая shell-команда",
    "description": "Что делает команда"
  }
}

Примеры action (для Windows):
  "start chrome"             — открыть браузер
  "notepad.exe"              — открыть блокнот
  "calc.exe"                 — калькулятор
  "start steam://..."        — запустить игру
  "start https://..."        — открыть URL
  "shutdown /s /t 5"         — выключить ПК
  "explorer"                 — проводник
  "taskmgr"                  — диспетчер задач
  "powershell -Command ..."  — любая PowerShell команда
"""

import json
import subprocess
import os

from resource_path import resource_path


COMMANDS_JSON_PATH = resource_path("commands.json")


class CommandHandler:
    """
    Обработчик команд. Загружает команды из commands.json
    и выполняет их при совпадении триггера с голосовым текстом.
    """

    def __init__(self):
        self._commands: dict = {}
        self._load_commands()

    def _load_commands(self):
        """Загрузить команды из commands.json."""
        self._commands = {}

        if not os.path.exists(COMMANDS_JSON_PATH):
            print(f"[CommandHandler] Файл {COMMANDS_JSON_PATH} не найден")
            return

        try:
            with open(COMMANDS_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                print(f"[CommandHandler] Ошибка: не словарь в {COMMANDS_JSON_PATH}")
                return

            for name, cmd in data.items():
                if not isinstance(cmd, dict):
                    continue
                triggers = cmd.get("triggers", [])
                action = cmd.get("action", "")
                description = cmd.get("description", "")
                if triggers and action:
                    self._commands[name] = {
                        "triggers": [t.lower().strip() for t in triggers],
                        "action": action,
                        "description": description,
                    }

            print(f"[CommandHandler] Загружено {len(self._commands)} команд")

        except json.JSONDecodeError as e:
            print(f"[CommandHandler] Ошибка JSON: {e}")
        except Exception as e:
            print(f"[CommandHandler] Ошибка загрузки: {e}")

    def reload(self):
        """Перезагрузить команды из JSON (без перезапуска агента)."""
        self._load_commands()

    def list_commands(self) -> list[tuple[str, list[str], str]]:
        """Вернуть список: (имя, триггеры, описание)."""
        return [
            (name, cmd["triggers"], cmd["description"])
            for name, cmd in self._commands.items()
        ]

    def process(self, text: str) -> tuple[str | None, bool | None]:
        """
        Найти команду по тексту и выполнить.

        Returns:
            (command_name, True)  — найдено, выполнено успешно
            (command_name, False) — найдено, но ошибка выполнения
            (None, None)          — не найдено
        """
        if not text:
            return (None, None)

        text_lower = text.lower().strip()

        for name, cmd in self._commands.items():
            for trigger in cmd["triggers"]:
                if trigger in text_lower:
                    print(f"  [CommandHandler] '{name}' по триггеру '{trigger}'")
                    try:
                        subprocess.Popen(cmd["action"], shell=True)
                        return (name, True)
                    except Exception as e:
                        print(f"  [CommandHandler] Ошибка '{name}': {e}")
                        return (name, False)

        return (None, None)