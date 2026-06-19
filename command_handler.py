"""
Command Handler for Marci Agent
================================
Чистый обработчик голосовых команд.

Формат commands.json:
  "категория": ["🔠 Название", {
    "имя": [["триггер","фраза"], "action", "описание"]
  }]

Типы action:
  - "start chrome"           → subprocess.Popen (shell)
  - "python:модуль:метод"    → importlib.import_module().method()
    например "python:spotify_controller:get_status_text"

Никаких хардкод-команд — всё только из JSON.
"""

import json
import subprocess
import os
import importlib
import re
import shlex

from resource_path import resource_path


COMMANDS_JSON_PATH = resource_path("commands.json")


def _call_python_action(action: str, argument: str | None = None):
    """
    Выполнить action вида "python:модуль:метод".

    Поддерживаемые форматы:
      "python:модуль:функция"         — module.function()
      "python:модуль:Класс:метод"     — module.Class().method()
      "python:модуль:класс:метод"     — module.Class().method() (авто PascalCase)

    Returns:
        (result_string, success_bool) — строка результата и флаг успеха
        (None, False)                 — ошибка
    """
    try:
        parts = action.split(":")

        if len(parts) < 3:
            return (None, False)

        module_name = parts[1]

        if len(parts) == 3:
            method_name = parts[2]
            module = importlib.import_module(module_name)
            func = getattr(module, method_name, None)
            if func is None:
                return (None, False)
            result = func(argument) if argument is not None else func()
        else:
            class_name = parts[2]
            method_name = parts[3]
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name, None)
            if cls is None:
                alt = "".join(p.capitalize() for p in class_name.split("_"))
                cls = getattr(module, alt, None)
            if cls is None:
                return (None, False)
            instance = cls()
            func = getattr(instance, method_name, None)
            if func is None:
                return (None, False)
            result = func(argument) if argument is not None else func()

        # Определяем success по типу результата
        if isinstance(result, tuple) and len(result) == 2:
            result_str = str(result[0]) if result[0] is not None else None
            success = bool(result[1])
        elif isinstance(result, bool):
            # Функция вернула True/False — используем как success
            success = result
            result_str = str(result) if result else None
        else:
            # Функция вернула строку или что-то ещё — считаем успехом
            success = True
            result_str = str(result) if result is not None else None

        return (result_str, success)

    except Exception as e:
        print(f"  [CommandHandler] Ошибка python-действия {action}: {e}")
        return (None, False)


def _normalize_text(text: str) -> str:
    return " ".join((text or "").lower().strip().split())


def _extract_argument(text: str, trigger: str, options: dict | None = None) -> str:
    options = options or {}
    text_clean = " ".join((text or "").strip().split())
    text_lower = text_clean.lower()
    trigger_lower = trigger.lower().strip()

    capture_after = options.get("capture_after", [])
    if isinstance(capture_after, str):
        capture_after = [capture_after]

    markers = [m.lower().strip() for m in capture_after if isinstance(m, str) and m.strip()]
    markers.extend([
        " и запиши ",
        " запиши ",
        " напиши ",
        " введи ",
        " вставь ",
        " найди ",
        " поищи ",
        " включи ",
        " открой ",
    ])

    for marker in sorted(set(markers), key=len, reverse=True):
        index = text_lower.find(marker)
        if index != -1:
            return text_clean[index + len(marker):].strip(" .,!?:;\"'")

    index = text_lower.find(trigger_lower)
    if index != -1:
        return text_clean[index + len(trigger_lower):].strip(" .,!?:;\"'")

    return ""


def _format_shell_action(action: str, argument: str) -> str:
    if "{arg}" not in action:
        return action
    if os.name == "nt":
        return action.replace("{arg}", subprocess.list2cmdline([argument]))
    return action.replace("{arg}", shlex.quote(argument))


class CommandHandler:
    """
    Обработчик команд. Загружает commands.json компактного формата.
    """

    def __init__(self):
        self._commands: dict = {}
        self._categories: dict = {}
        self._load_commands()

    def _load_commands(self):
        """Загрузить команды из commands.json (компактный формат)."""
        self._commands = {}
        self._categories = {}

        if not os.path.exists(COMMANDS_JSON_PATH):
            print(f"[CommandHandler] Файл {COMMANDS_JSON_PATH} не найден")
            return

        try:
            with open(COMMANDS_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                print(f"[CommandHandler] Ошибка: не словарь в {COMMANDS_JSON_PATH}")
                return

            for cat_name, category in data.items():
                if not isinstance(category, list) or len(category) < 2:
                    continue

                cat_desc = category[0]
                commands_dict = category[1]

                if not isinstance(commands_dict, dict):
                    continue

                self._categories[cat_name] = {
                    "description": cat_desc,
                    "command_count": 0,
                }

                for cmd_name, cmd in commands_dict.items():
                    if not isinstance(cmd, list) or len(cmd) < 3:
                        continue

                    triggers, action, description = cmd[0], cmd[1], cmd[2]
                    options = cmd[3] if len(cmd) > 3 and isinstance(cmd[3], dict) else {}

                    if not isinstance(triggers, list) or not triggers or not action:
                        continue

                    full_name = f"{cat_name}.{cmd_name}"
                    self._commands[full_name] = {
                        "triggers": [t.lower().strip() for t in triggers],
                        "action": action,
                        "description": description,
                        "options": options,
                        "category": cat_name,
                        "category_desc": cat_desc,
                    }
                    self._categories[cat_name]["command_count"] += 1

            total = len(self._commands)
            cats = len(self._categories)
            print(f"[CommandHandler] {total} команд в {cats} категориях загружено")

        except json.JSONDecodeError as e:
            print(f"[CommandHandler] Ошибка JSON: {e}")
        except Exception as e:
            print(f"[CommandHandler] Ошибка загрузки: {e}")

    def reload(self):
        """Перезагрузить команды из JSON (без перезапуска агента)."""
        self._load_commands()

    def list_categories(self):
        """Вернуть список: (имя, описание, кол-во команд)."""
        return [
            (name, cat["description"], cat["command_count"])
            for name, cat in self._categories.items()
        ]

    def list_commands(self):
        """
        Вернуть список: (полное_имя, категория, триггеры, описание).
        Отсортировано по категориям.
        """
        result = []
        for cat_name in self._categories:
            cat_desc = self._categories[cat_name]["description"]
            for full_name, cmd in self._commands.items():
                if cmd["category"] == cat_name:
                    result.append((
                        full_name,
                        cat_desc,
                        cmd["triggers"],
                        cmd["description"],
                    ))
        return result

    def process(self, text: str):
        """
        Найти команду по тексту и выполнить.

        Returns:
            (command_name, True, result)  — найдено, выполнено, результат
            (command_name, False, None)   — найдено, ошибка
            (None, None, None)            — не найдено
        """
        if not text:
            return (None, None, None)

        text_lower = _normalize_text(text)
        best_match = None

        for name, cmd in self._commands.items():
            for trigger in cmd["triggers"]:
                trigger_lower = _normalize_text(trigger)
                if trigger_lower in text_lower:
                    score = len(trigger_lower)
                    if cmd.get("options", {}).get("arg"):
                        score += 1000
                    if best_match is None or score > best_match[3]:
                        best_match = (name, cmd, trigger_lower, score)

        if best_match is not None:
            name, cmd, trigger, _score = best_match
            action = cmd["action"]
            options = cmd.get("options", {})
            argument = None

            if options.get("arg") or "{arg}" in action:
                argument = _extract_argument(text, trigger, options)
                if not argument and options.get("require_arg", True):
                    return (name, False, "Не услышал аргумент команды")

            try:
                if action.startswith("python:"):
                    # Python-действие — возвращает (result_str, success)
                    result_text, success = _call_python_action(action, argument)
                    return (name, success, result_text)
                else:
                    # Shell-команда
                    action = _format_shell_action(action, argument or "")
                    subprocess.Popen(action, shell=True)
                    return (name, True, None)
            except Exception:
                return (name, False, None)

        return (None, None, None)
