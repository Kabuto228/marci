"""
Marci Voice Agent — Talking Ben style
=====================================
Единый блок: голос + команды.
- Слушает микрофон (Vosk / Google Speech)
- Распознаёт пробуждение по слову "Марси"
- Реагирует звуками и картинками
- Idle-режим с so_long звуком после 10-15 мин тишины
- Команды ТОЛЬКО из commands.json (через CommandHandler)

Набор команд не зашит в коде — всё в commands.json.
Пользователь открывает commands.json в блокноте и добавляет/меняет команды.
"""

import signal
import sys
import time
import re
import random
import json
import os
import threading

import pyaudio
import vosk
import speech_recognition as sr

from sound_manager import play_sound, play_file, stop_all
from image_manager import show_random_image
from resource_path import resource_path
from command_handler import CommandHandler


# ─── Config ───────────────────────────────────────────────────

VOSK_MODEL_PATH = resource_path("vosk-model-small-ru-0.22")
RARE_CHANCE = 0.10          # 10% chance for rare sound
IDLE_MIN_SECS = 10 * 60     # 10 min idle before so_long
IDLE_MAX_SECS = 15 * 60     # 15 min idle before so_long


# ─── State ────────────────────────────────────────────────────

running = True
so_long_playing = False

cmd_handler = CommandHandler()


def signal_handler(sig, frame):
    global running
    print("\n[Marci] Bye!")
    running = False


# ─── Wake / Stop helpers ──────────────────────────────────────

def check_wake_word(text: str) -> bool:
    """Check if text contains 'Марси' with fuzzy matching."""
    t = text.lower().strip()
    for w in ["марси", "марся", "марс", "макси", "мари", "марсо",
              "marci", "marcy", "mars", "барсе", "март", "арси"]:
        if w in t:
            return True
    if re.search(r'\bмар[сиояеуюа]{1,3}\b', t):
        return True
    if re.search(r'\bмакс[иояеуюа]?\b', t):
        return True
    return False


def check_stop_command(text: str) -> bool:
    """Check if text means 'stop/shut up' — to interrupt long sounds."""
    t = text.lower().strip()
    stop_words = ["стоп", "хватит", "завали", "ебало", "заткн", "замолч",
                  "прекрат", "останов", "баста", "всё", "всё хватит",
                  "закр", "рош", "останов", "перестань", "умолкн",
                  "stop", "shut up", "quiet", "enough", "silence"]
    for w in stop_words:
        if w in t:
            return True
    return False


# ─── Sound reaction helpers ───────────────────────────────────

def simple_react() -> str:
    """Random reaction with 10% rare chance — just like Talking Ben!"""
    if random.random() < RARE_CHANCE:
        return "rare"
    return random.choice(["move", "laugh", "deny", "thanks", "immortality", "damage"])


def random_react_exclude_rare() -> str:
    """Random reaction, but NEVER plays the rare sound."""
    return random.choice(["move", "laugh", "deny", "thanks", "immortality", "damage"])


# ─── Microphone helpers ───────────────────────────────────────

def find_usb_mic():
    """Find USB microphone device index."""
    p = pyaudio.PyAudio()
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0 and "usb" in info["name"].lower():
            p.terminate()
            return i
    p.terminate()
    return None


def listen_with_vosk(model, device_index=None, timeout=10, stop_check=None):
    """
    Fast offline listening with Vosk. Returns recognized text or None.
    stop_check: optional callable returning True to abort listening early.
    """
    p = pyaudio.PyAudio()
    
    if device_index is not None:
        dev_info = p.get_device_info_by_index(device_index)
    else:
        try:
            dev_info = p.get_default_input_device_info()
        except OSError:
            p.terminate()
            return None
    
    native_rate = int(dev_info["defaultSampleRate"])
    device_idx = device_index if device_index is not None else dev_info["index"]
    
    rec = vosk.KaldiRecognizer(model, native_rate)
    
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=native_rate,
        input=True,
        input_device_index=device_idx,
        frames_per_buffer=4000,
    )

    result_text = ""
    start_time = time.time()
    last_partial = ""
    
    try:
        while time.time() - start_time < timeout:
            if stop_check and stop_check():
                break

            data = stream.read(2000, exception_on_overflow=False)
            
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                text = res.get("text", "")
                if text:
                    result_text += text + " "
                    if time.time() - start_time > 0.5:
                        break
            else:
                partial = json.loads(rec.PartialResult())
                ptext = partial.get("partial", "")
                if ptext and ptext != last_partial:
                    last_partial = ptext
                    if check_wake_word(ptext):
                        result_text = ptext + " "
                        break
                    if check_stop_command(ptext):
                        result_text = ptext + " "
                        break

        res = json.loads(rec.FinalResult())
        text = res.get("text", "")
        if text:
            result_text += text + " "

    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

    result_text = result_text.strip()
    return result_text if result_text else None


def listen_command_google(device_index=None, timeout=5):
    """Listen for a command phrase using Google Speech API."""
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.6
    
    try:
        mic = sr.Microphone(device_index=device_index)
    except (AttributeError, OSError):
        return None

    with mic as source:
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=6)
        except sr.WaitTimeoutError:
            return None

    try:
        return recognizer.recognize_google(audio, language="ru-RU")
    except (sr.UnknownValueError, sr.RequestError):
        return None



# ─── Main ─────────────────────────────────────────────────────

def main():
    global running, so_long_playing

    print()
    print("  🎤 Marci — Talking Ben Style")
    print("  Say 'Марси' then talk — Marci reacts!")
    print("  Ctrl+C to quit")
    print()

    signal.signal(signal.SIGINT, signal_handler)

    # Startup sound
    try:
        play_sound("wake", blocking=True)
    except Exception as e:
        print(f"[Marci] Startup sound error: {e}")

    # Find best mic
    device_index = find_usb_mic()
    
    # Load Vosk
    if os.path.exists(VOSK_MODEL_PATH):
        print("[Vosk] Loading model for fast wake word detection...")
        model = vosk.Model(VOSK_MODEL_PATH)
        print("[Vosk] Ready! (offline, instant)")
        use_vosk = True
    else:
        print("[Vosk] Model not found — using Google for everything (slower)")
        use_vosk = False
        model = None
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.5
        try:
            mic = sr.Microphone(device_index=device_index)
        except (AttributeError, OSError):
            print("[Marci] No microphone found!")
            sys.exit(1)
        print("[Marci] Calibrating... stay quiet.")
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
        print("[Marci] Ready!")

    print("[Marci] 🟢\n")

    # Shared state for idle timer
    last_interaction = {'time': time.time()}
    state = "idle"

    while running:
        try:
            if state == "idle":
                if so_long_playing:
                    stop_all()
                    so_long_playing = False

                if use_vosk:
                    text = listen_with_vosk(model, device_index=device_index, timeout=5)
                    if text:
                        print(f"  heard: \"{text}\"")
                        
                        if check_stop_command(text):
                            stop_all()
                            so_long_playing = False
                            continue
                        
                        if check_wake_word(text):
                            print("  ✨ Wake word!")
                            last_interaction['time'] = time.time()
                            play_sound("wake", blocking=False)
                            show_random_image()
                            state = "listening"
                else:
                    with mic as source:
                        try:
                            audio = recognizer.listen(source, timeout=None, phrase_time_limit=3)
                        except sr.WaitTimeoutError:
                            continue
                    try:
                        text = recognizer.recognize_google(audio, language="ru-RU")
                        if check_stop_command(text):
                            stop_all()
                            so_long_playing = False
                            continue
                        if check_wake_word(text):
                            print(f"  heard: \"{text}\" ✨")
                            last_interaction = time.time()
                            play_sound("wake", blocking=True)
                            state = "listening"
                    except (sr.UnknownValueError, sr.RequestError):
                        pass

            elif state == "listening":
                last_interaction['time'] = time.time()
                
                if use_vosk:
                    text = listen_with_vosk(model, device_index=device_index, timeout=6)
                else:
                    text = listen_command_google(device_index=device_index, timeout=5)

                if text:
                    # Try to process as a command first. This lets phrases like
                    # "останови музыку" reach Spotify instead of being consumed
                    # by the generic Marci stop-word check.
                    cmd_name, success, result_text = cmd_handler.process(text)
                    if cmd_name is not None:
                        # Command was matched
                        if success:
                            print(f"  ✅ Команда '{cmd_name}' выполнена!")
                            reaction = random_react_exclude_rare()
                        else:
                            print(f"  ❌ Команда '{cmd_name}' не выполнена!")
                            reaction = "deny"
                        print(f"  said: \"{text}\" → {reaction}")
                        play_sound(reaction, blocking=False)
                        show_random_image()
                        state = "idle"
                        print()
                        continue

                    # No command matched, so generic stop words can interrupt Marci.
                    if check_stop_command(text):
                        print("  🛑 Stopped!")
                        stop_all()
                        so_long_playing = False
                        state = "idle"
                        print()
                        continue

                    else:
                        # No command matched — random react but exclude rare
                        reaction = random_react_exclude_rare()
                        print(f"  said: \"{text}\" → {reaction}")
                else:
                    # No text at all — standard reaction with rare chance
                    reaction = simple_react()
                    print(f"  → {reaction}")

                play_sound(reaction, blocking=False)
                show_random_image()

                state = "idle"
                print()

        except KeyboardInterrupt:
            signal_handler(None, None)
        except Exception as e:
            print(f"[Marci] Error: {e}")
            time.sleep(0.3)

    print("[Marci] 👋")


if __name__ == "__main__":
    main()
