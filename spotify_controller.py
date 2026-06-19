"""
Spotify Controller для Marci Agent
====================================
Управление Spotify через Spotipy (Web API) + локальные fallback-команды Windows.

Для полного функционала нужно зарегистрировать приложение:
  1. https://developer.spotify.com/dashboard -> Create App
  2. В настройках добавить Redirect URI из spotify_config.json
     Например: http://127.0.0.1:8888/callback
  3. Скопировать Client ID и Client Secret в spotify_config.json

Первичная авторизация проходит через локальный callback-сервер: браузер откроется,
Spotify вернет код на localhost/127.0.0.1, а токен сохранится в .spotify_cache.
Вставлять ссылку из браузера обратно в терминал больше не нужно.
"""

import ctypes
import json
import os
import re
import subprocess
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from resource_path import resource_path


CONFIG_PATH = resource_path("spotify_config.json")
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPE = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-library-modify "
    "user-read-currently-playing "
    "playlist-read-private "
    "playlist-read-collaborative"
)

MEDIA_KEYS = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
}
SPOTIFY_VOLUME_STEP = 10

ARTIST_MARKERS = (
    "исполнителя",
    "исполнитель",
    "автора",
    "автор",
    "артиста",
    "артист",
    "группы",
    "группа",
    "певца",
    "певицы",
    "от",
)

CYRILLIC_TO_LATIN = str.maketrans({
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
})

ENGLISH_SOUND_ALIASES = (
    ("дж", "j"),
    ("кс", "x"),
    ("кью", "q"),
    ("ку", "q"),
    ("вай", "y"),
    ("ви", "v"),
    ("дабл ю", "w"),
    ("даблю", "w"),
    ("ф", "f"),
)


class SpotifyController:
    """
    Контроллер Spotify. Для точного управления используется Spotipy Web API.
    Если API недоступен, команды play/pause/next/previous пробуют медиаклавиши Windows.
    """

    def __init__(self):
        self._spotify = None
        self._swspotify = None
        self._auth = None
        self._cache_path = None
        self._last_device_id = None
        self.use_spotipy = False
        self.use_swspotify = False

        try:
            from SwSpotify import spotify as _sp

            self._swspotify = _sp
            self.use_swspotify = True
            print("[Spotify] SwSpotify доступен (чтение треков)")
        except ImportError:
            pass

    def _load_config(self) -> dict:
        """Загрузить конфиг из spotify_config.json."""
        if not os.path.exists(CONFIG_PATH):
            return {}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Spotify] Не удалось прочитать spotify_config.json: {e}")
            return {}

    @staticmethod
    def _is_local_redirect_uri(redirect_uri: str) -> bool:
        parsed = urlparse(redirect_uri)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "http" and host in {"127.0.0.1", "localhost"} and parsed.port is not None

    def _get_redirect_uri(self, config: dict) -> str:
        redirect_uri = (config.get("SPOTIPY_REDIRECT_URI") or DEFAULT_REDIRECT_URI).strip()
        if self._is_local_redirect_uri(redirect_uri):
            return redirect_uri

        print("[Spotify] SPOTIPY_REDIRECT_URI должен быть локальным HTTP-адресом с портом.")
        print(f"[Spotify] Пример: {DEFAULT_REDIRECT_URI}")
        print("[Spotify] Добавь этот же адрес в Spotify Developer Dashboard -> Redirect URIs.")
        return ""

    def _ensure_spotipy(self, allow_auth: bool = True) -> bool:
        """Ленивая инициализация Spotipy без ручного ввода redirect URL в терминал."""
        if self.use_spotipy and self._spotify is not None:
            return True

        config = self._load_config()
        client_id = config.get("SPOTIPY_CLIENT_ID", "").strip()
        client_secret = config.get("SPOTIPY_CLIENT_SECRET", "").strip()
        username = config.get("SPOTIPY_USERNAME", "").strip()
        redirect_uri = self._get_redirect_uri(config)

        if not client_id or not client_secret:
            print("[Spotify] Нет SPOTIPY_CLIENT_ID или SPOTIPY_CLIENT_SECRET в spotify_config.json")
            return False
        if not redirect_uri:
            return False

        try:
            self._cache_path = os.path.join(os.path.dirname(CONFIG_PATH), ".spotify_cache")
            self._auth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=SCOPE,
                username=username or None,
                cache_path=self._cache_path,
                open_browser=True,
                requests_timeout=10,
            )

            cached_token = self._auth.get_cached_token()
            token = None
            if cached_token is not None:
                token_info = self._auth.validate_token(cached_token)
                if token_info is not None:
                    token = token_info.get("access_token")

            if token is None and not allow_auth:
                return False

            if token is None:
                print("\n  🔐 Требуется авторизация Spotify")
                print(f"  Redirect URI: {redirect_uri}")
                print("  Открою браузер. Нажми Agree — дальше токен сохранится автоматически.\n")
                token = self._auth.get_access_token(as_dict=False, check_cache=True)
                if not token:
                    print("[Spotify] Spotify не вернул access token")
                    return False

            self._spotify = spotipy.Spotify(auth_manager=self._auth, requests_timeout=10)
            self.use_spotipy = True
            print("[Spotify] Spotipy авторизован")
            return True

        except OSError as e:
            print(f"[Spotify] Не удалось поднять локальный OAuth-сервер: {e}")
            print("[Spotify] Проверь, что порт в SPOTIPY_REDIRECT_URI свободен, или укажи другой.")
            return False
        except Exception as e:
            msg = self._short_error(e)
            print(f"[Spotify] Ошибка авторизации Spotipy: {msg}")
            if "redirect" in msg.lower() or "invalid" in msg.lower():
                print(f"[Spotify] В Spotify Developer Dashboard должен быть Redirect URI: {redirect_uri}")
            return False

    @property
    def is_available(self) -> bool:
        """Доступен ли хоть какой-то функционал Spotify."""
        return self.use_spotipy or self.use_swspotify

    @property
    def can_control(self) -> bool:
        """Доступно ли управление через Spotify Web API."""
        return self.use_spotipy

    @staticmethod
    def _short_error(error: Exception) -> str:
        return " ".join(str(error).split())[:300]

    def _spotify_protocol(self, command: str = "") -> bool:
        """Открыть Spotify URI через системный обработчик spotify:."""
        uri = f"spotify:{command}" if command else "spotify:"
        try:
            if os.name == "nt":
                subprocess.Popen(
                    ["cmd", "/c", "start", "", uri],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif os.uname().sysname == "Darwin":
                subprocess.Popen(["open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"[Spotify] Не удалось открыть {uri}: {self._short_error(e)}")
            return False

    def _send_media_key(self, key_name: str) -> bool:
        """Fallback для desktop Spotify: глобальные медиаклавиши Windows."""
        vk_code = MEDIA_KEYS.get(key_name)
        if vk_code is None:
            return False

        return self._send_virtual_key(vk_code)

    def _send_virtual_key(self, vk_code: int) -> bool:
        """Нажать виртуальную клавишу Windows."""
        if os.name != "nt":
            return False

        try:
            keyeventf_keyup = 0x0002
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.keybd_event(vk_code, 0, 0, 0)
            user32.keybd_event(vk_code, 0, keyeventf_keyup, 0)
            return True
        except Exception as e:
            print(f"[Spotify] Клавиша Windows не сработала: {self._short_error(e)}")
            return False

    def _get_device_id(self) -> str | None:
        """Найти активное или подходящее устройство Spotify для Web API."""
        if not self.use_spotipy or self._spotify is None:
            return None

        try:
            playback = self._spotify.current_playback()
            device = (playback or {}).get("device") or {}
            if device.get("id"):
                self._last_device_id = device["id"]
                return self._last_device_id
        except Exception:
            pass

        try:
            devices = self._spotify.devices().get("devices", [])
        except Exception:
            return self._last_device_id

        if not devices:
            return self._last_device_id

        for device in devices:
            if device.get("is_active") and not device.get("is_restricted"):
                self._last_device_id = device.get("id")
                return self._last_device_id

        for device in devices:
            if not device.get("is_restricted"):
                self._last_device_id = device.get("id")
                return self._last_device_id

        return self._last_device_id

    def _local_playing_state(self) -> bool | None:
        """Вернуть локальное состояние Spotify, если SwSpotify смог его определить."""
        if not self.use_swspotify or self._swspotify is None:
            return None

        try:
            self._swspotify.song()
            return True
        except self._swspotify.SpotifyPaused:
            return False
        except Exception:
            return None

    def _play_pause_fallback(self, want_playing: bool) -> bool:
        state = self._local_playing_state()
        if state is want_playing:
            return True
        return self._send_media_key("play_pause")

    def _api_or_fallback(self, api_call, fallback) -> bool:
        """Выполнить Web API-команду, а при ошибке попробовать медиаклавишу."""
        if self._ensure_spotipy(allow_auth=False) and self._spotify is not None:
            device_id = self._get_device_id()
            try:
                api_call(device_id)
                return True
            except Exception as e:
                print(f"[Spotify] Web API не выполнил команду: {self._short_error(e)}")

        return fallback()

    # ─── Чтение информации ─────────────────────────────────────

    def get_current_track(self) -> dict | None:
        """Получить информацию о текущем треке."""
        if self.use_spotipy and self._spotify:
            try:
                data = self._spotify.current_playback()
                if data is not None and data.get("item"):
                    item = data["item"]
                    return {
                        "song": item.get("name", ""),
                        "artist": ", ".join(a["name"] for a in item.get("artists", [])),
                        "album": item.get("album", {}).get("name", ""),
                        "playing": data.get("is_playing", False),
                        "progress_ms": data.get("progress_ms", 0),
                        "duration_ms": item.get("duration_ms", 0),
                        "error": None,
                    }
                if data is None:
                    return {"song": None, "artist": None, "playing": False, "error": "Spotify not running"}
                return {"song": None, "artist": None, "playing": data.get("is_playing", False), "error": "no track"}
            except Exception:
                pass

        if self.use_swspotify and self._swspotify:
            try:
                return {
                    "song": self._swspotify.song(),
                    "artist": self._swspotify.artist(),
                    "playing": None,
                    "error": None,
                }
            except self._swspotify.SpotifyClosed:
                return {"song": None, "artist": None, "playing": False, "error": "Spotify closed"}
            except self._swspotify.SpotifyNotRunning:
                return {"song": None, "artist": None, "playing": False, "error": "Spotify not running"}
            except self._swspotify.SpotifyPaused:
                try:
                    return {
                        "song": self._swspotify.song(),
                        "artist": self._swspotify.artist(),
                        "playing": False,
                        "error": "paused",
                    }
                except Exception:
                    return {"song": None, "artist": None, "playing": False, "error": "paused"}
            except Exception:
                return None

        return None

    def get_status_text(self) -> str:
        """Красивый статус для голосового ответа."""
        self._ensure_spotipy(allow_auth=False)
        track = self.get_current_track()
        if track is None:
            if not self.is_available:
                return "Модуль Spotify недоступен"
            return "Не удалось получить информацию"

        error = track.get("error")
        song = track.get("song")
        artist = track.get("artist")
        album = track.get("album")

        if error == "Spotify closed":
            return "Spotify закрыт, открой Spotify сначала"
        if error == "Spotify not running":
            return "Spotify не запущен"
        if error == "no track":
            return "Ничего не играет"
        if not song:
            return "Сейчас ничего не играет"

        status = "Сейчас играет" if track.get("playing") is not False else "На паузе"
        extra = f" (альбом {album})" if album else ""
        return f"{status} {song} — {artist}{extra}"

    # ─── Управление ────────────────────────────────────────────

    def open(self) -> bool:
        """Открыть Spotify без запуска OAuth."""
        return self._spotify_protocol("")

    def play(self) -> bool:
        """Продолжить воспроизведение."""
        return self._api_or_fallback(
            lambda device_id: self._spotify.start_playback(device_id=device_id),
            lambda: self._play_pause_fallback(True),
        )

    def pause(self) -> bool:
        """Поставить на паузу."""
        return self._api_or_fallback(
            lambda device_id: self._spotify.pause_playback(device_id=device_id),
            lambda: self._play_pause_fallback(False),
        )

    def next(self) -> bool:
        """Следующий трек."""
        return self._api_or_fallback(
            lambda device_id: self._spotify.next_track(device_id=device_id),
            lambda: self._send_media_key("next"),
        )

    def previous(self) -> bool:
        """Предыдущий трек."""
        return self._api_or_fallback(
            lambda device_id: self._spotify.previous_track(device_id=device_id),
            lambda: self._send_media_key("previous"),
        )

    def like(self) -> str:
        """Лайкнуть / добавить текущий трек в избранное."""
        if not self._ensure_spotipy() or self._spotify is None:
            return "Лайк требует авторизацию Spotify"

        try:
            playback = self._spotify.current_playback()
            item = (playback or {}).get("item")
            if not item:
                return "Сейчас ничего не играет, нечего лайкать"
            if item.get("type") != "track":
                return "Лайк доступен только для треков"

            self._spotify.current_user_saved_tracks_add([item["id"]])
            return "Добавлено в избранное"
        except Exception as e:
            return f"Ошибка лайка: {self._short_error(e)}"

    def play_song(self, uri: str = "") -> bool:
        """Воспроизвести трек по Spotify URI."""
        if not uri:
            return self.play()

        if self._ensure_spotipy() and self._spotify is not None:
            try:
                self._spotify.start_playback(uris=[uri])
                return True
            except Exception as e:
                print(f"[Spotify] Не удалось включить URI через API: {self._short_error(e)}")

        return self._spotify_protocol(uri.replace("spotify:", "", 1))

    def search_and_play(self, query: str) -> str:
        """Найти трек по названию, дополнительно учитывая исполнителя из фразы."""
        if not self._ensure_spotipy() or self._spotify is None:
            return "Поиск недоступен без авторизации Spotify"

        parsed = self._parse_track_query(query)
        search_queries = self._build_track_search_queries(parsed)

        try:
            tracks = []
            for search_query in search_queries:
                results = self._spotify.search(q=search_query, type="track", limit=5)
                tracks = results.get("tracks", {}).get("items", [])
                if tracks:
                    break

            if not tracks:
                return f"Ничего не найдено по запросу '{query}'"

            track = self._pick_best_track(tracks, parsed)
            uri = track["uri"]
            name = track["name"]
            artist = ", ".join(a["name"] for a in track["artists"])

            self._spotify.start_playback(uris=[uri])
            return f"Воспроизвожу {name} — {artist}"
        except Exception as e:
            return f"Ошибка поиска: {self._short_error(e)}"

    @staticmethod
    def _clean_query_part(value: str | None) -> str:
        value = " ".join((value or "").strip().split())
        return value.strip(" .,!?:;\"'")

    def _parse_track_query(self, query: str) -> dict:
        """Вытащить название и исполнителя из естественной фразы."""
        raw = self._clean_query_part(query)
        lowered = raw.lower()

        if not raw:
            return {"raw": "", "track": "", "artist": ""}

        dash_match = re.split(r"\s+[-–—]\s+", raw, maxsplit=1)
        if len(dash_match) == 2:
            first = self._clean_query_part(dash_match[0])
            second = self._clean_query_part(dash_match[1])
            return {"raw": raw, "track": second, "artist": first}

        for marker in ARTIST_MARKERS:
            pattern = rf"\s+{re.escape(marker)}\s+"
            match = re.search(pattern, lowered)
            if not match:
                continue

            track = self._clean_query_part(raw[:match.start()])
            artist = self._clean_query_part(raw[match.end():])
            if track and artist:
                return {"raw": raw, "track": track, "artist": artist}

        return {"raw": raw, "track": raw, "artist": ""}

    @staticmethod
    def _spotify_quote(value: str) -> str:
        return value.replace('"', "")

    @staticmethod
    def _normalize_match_text(value: str | None) -> str:
        value = unicodedata.normalize("NFKD", value or "")
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        value = value.lower().replace("&", " and ")
        value = re.sub(r"[^0-9a-zа-яё]+", " ", value)
        return " ".join(value.split())

    @classmethod
    def _latinized_text(cls, value: str | None) -> str:
        normalized = cls._normalize_match_text(value)
        for source, replacement in ENGLISH_SOUND_ALIASES:
            normalized = normalized.replace(source, replacement)
        return " ".join(normalized.translate(CYRILLIC_TO_LATIN).split())

    @classmethod
    def _playlist_score(cls, playlist: dict, query: str) -> int:
        wanted = cls._normalize_match_text(query)
        wanted_latin = cls._latinized_text(query)
        name = cls._normalize_match_text(playlist.get("name"))
        name_latin = cls._latinized_text(playlist.get("name"))

        score = 0
        if wanted and wanted == name:
            score += 100
        if wanted_latin and wanted_latin == name_latin:
            score += 95
        if wanted and wanted in name:
            score += 70
        if wanted_latin and wanted_latin in name_latin:
            score += 65
        if wanted and name in wanted:
            score += 40
        if wanted_latin and name_latin in wanted_latin:
            score += 35

        for left in (wanted, wanted_latin):
            for right in (name, name_latin):
                if left and right:
                    score += int(SequenceMatcher(None, left, right).ratio() * 45)

        wanted_words = set(wanted.split()) | set(wanted_latin.split())
        name_words = set(name.split()) | set(name_latin.split())
        score += len(wanted_words & name_words) * 8
        return score

    def _get_user_playlists(self) -> list[dict]:
        playlists = []
        limit = 50
        offset = 0

        while True:
            page = self._spotify.current_user_playlists(limit=limit, offset=offset)
            items = page.get("items", [])
            playlists.extend(items)
            if not page.get("next"):
                break
            offset += limit

        return playlists

    def _search_playlists(self, query: str) -> list[dict]:
        results = self._spotify.search(q=query, type="playlist", limit=10)
        return results.get("playlists", {}).get("items", [])

    def _find_playlist(self, query: str) -> dict | None:
        own_playlists = self._get_user_playlists()
        candidates = [p for p in own_playlists if p]

        if query:
            try:
                candidates.extend(p for p in self._search_playlists(query) if p)
            except Exception as e:
                print(f"[Spotify] Поиск публичных плейлистов не сработал: {self._short_error(e)}")

        unique = {}
        for playlist in candidates:
            playlist_id = playlist.get("id")
            if playlist_id and playlist_id not in unique:
                unique[playlist_id] = playlist

        if not unique:
            return None

        ranked = sorted(
            unique.values(),
            key=lambda playlist: self._playlist_score(playlist, query),
            reverse=True,
        )
        best = ranked[0]
        return best if self._playlist_score(best, query) > 0 else None

    def _build_track_search_queries(self, parsed: dict) -> list[str]:
        raw = parsed.get("raw", "")
        track = parsed.get("track", "")
        artist = parsed.get("artist", "")

        queries = []
        if track and artist:
            queries.append(f'track:"{self._spotify_quote(track)}" artist:"{self._spotify_quote(artist)}"')
            queries.append(f"{track} {artist}")
            queries.append(f"{artist} {track}")
        if raw:
            queries.append(raw)

        unique = []
        for query in queries:
            query = " ".join((query or "").strip().split())
            if query and query not in unique:
                unique.append(query)
        return unique or [raw]

    @staticmethod
    def _score_track(track: dict, parsed: dict) -> int:
        wanted_track = (parsed.get("track") or "").lower()
        wanted_artist = (parsed.get("artist") or "").lower()
        name = (track.get("name") or "").lower()
        artists = " ".join(a.get("name", "") for a in track.get("artists", [])).lower()

        score = 0
        if wanted_track and wanted_track in name:
            score += 20
        if wanted_artist and wanted_artist in artists:
            score += 30
        if name == wanted_track:
            score += 10
        if wanted_artist and any((a.get("name", "").lower() == wanted_artist) for a in track.get("artists", [])):
            score += 15
        return score

    def _pick_best_track(self, tracks: list[dict], parsed: dict) -> dict:
        if not parsed.get("artist"):
            return tracks[0]
        return max(tracks, key=lambda track: self._score_track(track, parsed))

    def search_and_play_playlist(self, query: str) -> str:
        """Найти свой или публичный плейлист по названию и запустить его."""
        query = self._clean_query_part(query)
        if not query:
            return "Не услышал название плейлиста"
        if not self._ensure_spotipy() or self._spotify is None:
            return "Плейлисты недоступны без авторизации Spotify"

        try:
            playlist = self._find_playlist(query)
            if not playlist:
                return f"Плейлист '{query}' не найден"

            uri = playlist.get("uri")
            name = playlist.get("name") or query
            owner = (playlist.get("owner") or {}).get("display_name") or "Spotify"
            if not uri:
                return f"У плейлиста '{name}' нет Spotify URI"

            self._spotify.start_playback(context_uri=uri, device_id=self._get_device_id())
            return f"Включаю плейлист {name} — {owner}"
        except Exception as e:
            return f"Ошибка плейлиста: {self._short_error(e)}"

    def volume(self, percent: int) -> str:
        """Установить громкость Spotify (0-100)."""
        if not self._ensure_spotipy() or self._spotify is None:
            return "Регулировка громкости недоступна без авторизации Spotify"

        percent = max(0, min(100, int(percent)))
        try:
            self._spotify.volume(percent, device_id=self._get_device_id())
            return f"Громкость Spotify установлена на {percent}%"
        except Exception as e:
            return f"Ошибка громкости: {self._short_error(e)}"

    def _get_spotify_device_for_volume(self, playback: dict | None = None) -> dict | None:
        """Найти устройство Spotify с известной громкостью."""
        if playback is None:
            try:
                playback = self._spotify.current_playback()
            except Exception:
                pass

        device = (playback or {}).get("device") or {}
        if device.get("volume_percent") is not None:
            return device

        try:
            devices = self._spotify.devices().get("devices", [])
        except Exception:
            return device if device else None

        for candidate in devices:
            if candidate.get("is_active") and candidate.get("volume_percent") is not None:
                return candidate

        for candidate in devices:
            if not candidate.get("is_restricted") and candidate.get("volume_percent") is not None:
                return candidate

        return device if device else None

    def _change_spotify_volume(self, delta: int, require_playing: bool = False) -> tuple[str, bool]:
        """Изменить громкость активного устройства Spotify."""
        if not self._ensure_spotipy(allow_auth=True) or self._spotify is None:
            return ("Не удалось авторизоваться в Spotify для изменения громкости", False)

        try:
            playback = self._spotify.current_playback()
            if require_playing and not (playback and playback.get("is_playing") and playback.get("item")):
                return ("Spotify сейчас не играет", False)

            device = self._get_spotify_device_for_volume(playback)
            if not device or device.get("volume_percent") is None:
                return ("Не удалось прочитать громкость устройства Spotify", False)

            current = int(device["volume_percent"])
            percent = max(0, min(100, current + delta))
            self._spotify.volume(percent, device_id=device.get("id"))
            return (f"Громкость Spotify: {percent}%", True)
        except Exception as e:
            return (f"Ошибка громкости Spotify: {self._short_error(e)}", False)

    def smart_volume(self, direction: str) -> tuple[str, bool]:
        """Изменить громкость Spotify, не трогая системную громкость Windows."""
        is_up = direction == "up"
        delta = SPOTIFY_VOLUME_STEP if is_up else -SPOTIFY_VOLUME_STEP
        return self._change_spotify_volume(delta, require_playing=True)


# ─── Модульные функции для command_handler ────────────────────
# Вызываются через "python:spotify_controller:spotify_play" и т.д.

_sp_instance = None


def _get_sp():
    global _sp_instance
    if _sp_instance is None:
        _sp_instance = SpotifyController()
    return _sp_instance


def spotify_open():
    return _get_sp().open()


def spotify_play():
    return _get_sp().play()


def spotify_pause():
    return _get_sp().pause()


def spotify_next():
    return _get_sp().next()


def spotify_prev():
    return _get_sp().previous()


def spotify_like():
    result = _get_sp().like()
    print(f"  [Spotify] {result}")
    failed_prefixes = (
        "Ошибка",
        "Нет ",
        "Сейчас ничего",
        "Лайк требует",
        "Лайк доступен",
    )
    return not any(isinstance(result, str) and result.startswith(prefix) for prefix in failed_prefixes)


def spotify_volume_up():
    result, success = _get_sp().smart_volume("up")
    print(f"  [Spotify] {result}")
    return success


def spotify_volume_down():
    result, success = _get_sp().smart_volume("down")
    print(f"  [Spotify] {result}")
    return success


def spotify_search_and_play(query: str | None = ""):
    if not query:
        return ("Не услышал название трека", False)

    result = _get_sp().search_and_play(query)
    print(f"  [Spotify] {result}")
    failed_prefixes = ("Ошибка", "Ничего", "Поиск недоступен")
    return (result, not any(result.startswith(prefix) for prefix in failed_prefixes))


def spotify_search_and_play_playlist(query: str | None = ""):
    if not query:
        return ("Не услышал название плейлиста", False)

    result = _get_sp().search_and_play_playlist(query)
    print(f"  [Spotify] {result}")
    failed_prefixes = ("Ошибка", "Плейлист", "Плейлисты недоступны", "Не услышал")
    return (result, not any(result.startswith(prefix) for prefix in failed_prefixes))


def spotify_status():
    return _get_sp().get_status_text()


# ─── Self-test ────────────────────────────────────────────────

if __name__ == "__main__":
    sp = SpotifyController()

    print(f"\n  Доступен: {sp.is_available}")
    print(f"  Управление: {sp.can_control}")
    print()

    track = sp.get_current_track()
    if track:
        print(f"  Трек: {track.get('song', 'N/A')}")
        print(f"  Артист: {track.get('artist', 'N/A')}")
        print(f"  Альбом: {track.get('album', 'N/A')}")
        print(f"  Статус: {sp.get_status_text()}")
    else:
        print("  Не удалось получить трек")
