"""
Sound Manager for Marci Agent
Handles loading and playing sounds from the sounds/ directory using pygame.
"""

import os
import random
import time

import pygame

from resource_path import resource_path


SOUNDS_DIR = resource_path("sounds")

# Sound mappings - each intent maps to one or more sound files
SOUND_MAP = {
    "wake": ["Vo_marci_marci_move.mp3", "Vo_marci_marci_move_2.mp3", "Vo_marci_marci_move_3.mp3"],
    "deny": ["Vo_marci_marci_deny.mp3"],
    "immortality": ["Vo_marci_marci_immortality.mp3"],
    "laugh": ["Vo_marci_marci_laugh.mp3"],
    "move": ["Vo_marci_marci_move.mp3", "Vo_marci_marci_move_2.mp3", "Vo_marci_marci_move_3.mp3"],
    "damage": ["Vo_marci_marci_taking_damage.mp3"],
    "thanks": ["Vo_marci_marci_thanks.mp3"],
    "rare": ["rare.mp3"],
}

# Global cache of Sound objects — prevents garbage collection during playback
# pygame may stop playing if the Sound object is freed
_sound_cache = {}

# Track currently playing channels so they don't get GC'd
_playing_channels = []

# Initialize pygame mixer
_mixer_initialized = False


def _init_mixer():
    """Initialize pygame mixer if not already done."""
    global _mixer_initialized
    if not _mixer_initialized:
        pygame.mixer.init(
            frequency=44100,
            size=-16,
            channels=2,      # stereo — MP3 files may be stereo
            buffer=4096,     # larger buffer prevents truncation on long sounds
        )
        # Allocate enough channels for simultaneous playback
        pygame.mixer.set_num_channels(16)
        _mixer_initialized = True


def _get_sound(filepath: str) -> pygame.mixer.Sound:
    """Load or retrieve a cached Sound object."""
    if filepath not in _sound_cache:
        _sound_cache[filepath] = pygame.mixer.Sound(filepath)
    return _sound_cache[filepath]


def _get_sound_duration(sound: pygame.mixer.Sound) -> float:
    """Get the duration of a pygame Sound object in seconds."""
    return sound.get_length()


def play_sound(intent: str, blocking: bool = False) -> bool:
    """
    Play a sound for the given intent.
    
    Args:
        intent: One of the keys in SOUND_MAP (wake, deny, immortality, laugh, move, damage, thanks)
        blocking: If True, wait for the sound to finish playing
    
    Returns:
        True if sound was played, False otherwise
    """
    _init_mixer()

    if intent not in SOUND_MAP:
        print(f"[SoundManager] Unknown intent: {intent}")
        return False

    filenames = SOUND_MAP[intent]
    filename = random.choice(filenames)
    filepath = os.path.join(SOUNDS_DIR, filename)

    if not os.path.exists(filepath):
        print(f"[SoundManager] Warning: file not found: {filepath}")
        return False

    try:
        sound = _get_sound(filepath)
        print(f"[SoundManager] Playing: {filename} (intent: {intent})")

        channel = sound.play()

        if channel is not None:
            # Keep a reference to the channel to prevent GC
            _playing_channels.append(channel)
            # Clean up finished channels periodically
            if len(_playing_channels) > 32:
                _playing_channels[:] = [ch for ch in _playing_channels if ch.get_busy()]

        if blocking and channel is not None:
            # Wait for sound to finish
            while channel.get_busy():
                time.sleep(0.05)

        return True
    except Exception as e:
        print(f"[SoundManager] Error playing {filename}: {e}")
        return False


def play_file(filename: str, blocking: bool = False) -> bool:
    """
    Play a specific sound file by name.
    
    Args:
        filename: Name of the MP3 file in the sounds/ directory
        blocking: If True, wait for the sound to finish playing
    
    Returns:
        True if sound was played, False otherwise
    """
    _init_mixer()

    filepath = os.path.join(SOUNDS_DIR, filename)
    if not os.path.exists(filepath):
        print(f"[SoundManager] Warning: file not found: {filepath}")
        return False

    try:
        sound = _get_sound(filepath)
        print(f"[SoundManager] Playing: {filename}")

        channel = sound.play()

        if channel is not None:
            _playing_channels.append(channel)
            if len(_playing_channels) > 32:
                _playing_channels[:] = [ch for ch in _playing_channels if ch.get_busy()]

        if blocking and channel is not None:
            while channel.get_busy():
                time.sleep(0.05)

        return True
    except Exception as e:
        print(f"[SoundManager] Error playing {filename}: {e}")
        return False


def sing_rare():
    """Play rare.mp3 from start to finish for the voice command."""
    played = play_file("rare.mp3", blocking=True)
    return ("Спел rare.mp3", played)


def stop_all():
    """Stop all currently playing sounds."""
    global _playing_channels
    if _mixer_initialized:
        pygame.mixer.stop()
        _playing_channels.clear()


def list_available_sounds() -> list:
    """List all available sound files."""
    sounds = []
    for f in os.listdir(SOUNDS_DIR):
        if f.endswith(".mp3"):
            sounds.append(f)
    return sorted(sounds)


def list_intents() -> list:
    """List all available intents."""
    return list(SOUND_MAP.keys())
