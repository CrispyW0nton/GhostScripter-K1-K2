"""
ghostscripter/utils/audio_player.py
====================================
Thread-safe audio player for KotOR VO / sound-effect files.

Supports:
  • WAV, MP3, OGG (anything soundfile or ffmpeg can decode)
  • Primary backend: soundfile + sounddevice (low-latency, no external process)
  • Fallback backend: ffplay subprocess (when no PortAudio device is present)
  • Qt signals for play-state, progress, and error reporting

Usage
-----
    from ghostscripter.utils.audio_player import AudioPlayerService

    svc = AudioPlayerService(parent_qobject)
    svc.state_changed.connect(lambda s: print("state:", s))
    svc.play(Path("dan13_dorak_001.wav"))

    # Later:
    svc.stop()
    svc.cleanup()          # call on widget close
"""

from __future__ import annotations

import logging
import threading
import subprocess
import time
from pathlib import Path


from qtpy.QtCore import QObject, Signal, QTimer

log = logging.getLogger("ghostscripter.audio_player")

# ── States ────────────────────────────────────────────────────────────────────

STATE_IDLE     = "idle"
STATE_LOADING  = "loading"
STATE_PLAYING  = "playing"
STATE_STOPPED  = "stopped"
STATE_ERROR    = "error"


# ── Backend detection ─────────────────────────────────────────────────────────

def _sounddevice_available() -> bool:
    """Return True if sounddevice + soundfile can actually play audio."""
    try:
        import sounddevice as sd
        import soundfile  # noqa: F401
        devices = sd.query_devices()
        # Need at least one output device
        return any(d["max_output_channels"] > 0 for d in devices)
    except Exception:
        return False


def _ffplay_available() -> bool:
    """Return True if ffplay is installed."""
    try:
        r = subprocess.run(["ffplay", "-version"],
                           capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


# ── Audio info ────────────────────────────────────────────────────────────────

class AudioInfo:
    """Basic metadata about an audio file."""
    def __init__(self, path: Path):
        self.path = path
        self.duration_s: float = 0.0
        self.samplerate: int = 0
        self.channels: int = 0
        self.frames: int = 0
        self.format: str = ""
        self._load()

    def _load(self):
        try:
            import soundfile as sf
            info = sf.info(str(self.path))
            self.duration_s = info.duration
            self.samplerate = info.samplerate
            self.channels = info.channels
            self.frames = info.frames
            self.format = info.format
        except Exception as e:
            log.debug("AudioInfo._load failed for %s: %s", self.path, e)
            # Try ffprobe as fallback
            try:
                r = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-show_entries",
                     "format=duration", "-of", "csv=p=0", str(self.path)],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode == 0 and r.stdout.strip():
                    self.duration_s = float(r.stdout.strip().split()[0])
            except Exception:
                pass

    @property
    def duration_str(self) -> str:
        s = int(self.duration_s)
        return f"{s // 60}:{s % 60:02d}"


# ── Main service ──────────────────────────────────────────────────────────────

class AudioPlayerService(QObject):
    """
    Qt-friendly, thread-safe audio player.

    Signals
    -------
    state_changed(str)      — one of STATE_* constants
    progress_changed(float) — 0.0 … 1.0 playback fraction
    duration_ready(float)   — seconds, emitted once file is opened
    error_occurred(str)     — human-readable error message
    """

    state_changed    = Signal(str)
    progress_changed = Signal(float)
    duration_ready   = Signal(float)
    error_occurred   = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        self._state    = STATE_IDLE
        self._lock     = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()

        # ffplay subprocess fallback
        self._proc: subprocess.Popen | None = None

        # Progress polling timer (Qt main thread)
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._poll_progress)

        # Populated by play()
        self._current_path: Path | None = None
        self._duration: float = 0.0
        self._start_time: float = 0.0

        # Backend selection (lazy, cached)
        self._sd_ok: bool | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def play(self, path: Path) -> None:
        """Start playing *path*.  Stops any currently playing file first."""
        self.stop()
        if not path.exists():
            self._emit_error(f"File not found: {path.name}")
            return

        self._current_path = path
        self._set_state(STATE_LOADING)
        log.info("AudioPlayer: play %s", path.name)

        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._play_thread,
            args=(path,),
            daemon=True,
            name="audio-player"
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop playback immediately."""
        self._stop_evt.set()
        self._timer.stop()

        # Kill ffplay subprocess if running
        with self._lock:
            if self._proc is not None:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                self._proc = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        if self._state not in (STATE_IDLE, STATE_ERROR):
            self._set_state(STATE_STOPPED)

    def cleanup(self) -> None:
        """Call when the owning widget is destroyed."""
        self.stop()
        self._set_state(STATE_IDLE)

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_playing(self) -> bool:
        return self._state == STATE_PLAYING

    @property
    def duration(self) -> float:
        return self._duration

    # ── Internal ──────────────────────────────────────────────────────────────

    def _set_state(self, s: str) -> None:
        if self._state != s:
            self._state = s
            self.state_changed.emit(s)

    def _emit_error(self, msg: str) -> None:
        log.warning("AudioPlayer error: %s", msg)
        self._set_state(STATE_ERROR)
        self.error_occurred.emit(msg)

    def _use_sounddevice(self) -> bool:
        if self._sd_ok is None:
            self._sd_ok = _sounddevice_available()
            log.debug("AudioPlayer backend: %s",
                      "sounddevice" if self._sd_ok else "ffplay")
        return self._sd_ok

    # ── Playback thread ───────────────────────────────────────────────────────

    def _play_thread(self, path: Path) -> None:
        if self._use_sounddevice():
            self._play_sounddevice(path)
        else:
            self._play_ffplay(path)

    def _play_sounddevice(self, path: Path) -> None:
        """Play using soundfile + sounddevice (low-latency)."""
        try:
            import soundfile as sf
            import sounddevice as sd
            import numpy as np

            data, samplerate = sf.read(str(path), dtype="float32", always_2d=True)
            self._duration = len(data) / samplerate
            self._start_time = time.monotonic()
            self.duration_ready.emit(self._duration)
            self._set_state(STATE_PLAYING)

            chunk = 2048
            pos = 0
            stream = sd.OutputStream(samplerate=samplerate,
                                     channels=data.shape[1],
                                     dtype="float32")
            with stream:
                stream.start()
                while pos < len(data) and not self._stop_evt.is_set():
                    end = min(pos + chunk, len(data))
                    stream.write(data[pos:end])
                    pos = end

        except Exception as e:
            log.error("sounddevice playback failed: %s", e, exc_info=True)
            # Try ffplay fallback
            self._sd_ok = False
            self._play_ffplay(path)
            return

        if not self._stop_evt.is_set():
            self._set_state(STATE_STOPPED)
        self._timer_stop_safe()

    def _play_ffplay(self, path: Path) -> None:
        """Play using ffplay as a subprocess (fallback)."""
        if not _ffplay_available():
            self._emit_error("No audio backend available (ffplay not found).")
            return

        # Get duration first via soundfile or ffprobe
        try:
            info = AudioInfo(path)
            self._duration = info.duration_s
        except Exception:
            self._duration = 0.0

        self.duration_ready.emit(self._duration)
        self._start_time = time.monotonic()
        self._set_state(STATE_PLAYING)

        try:
            cmd = [
                "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                str(path)
            ]
            with self._lock:
                if self._stop_evt.is_set():
                    return
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            self._proc.wait()

            with self._lock:
                self._proc = None

        except Exception as e:
            log.error("ffplay playback failed: %s", e)
            self._emit_error(f"Playback error: {e}")
            return

        if not self._stop_evt.is_set():
            self._set_state(STATE_STOPPED)
        self._timer_stop_safe()

    def _timer_stop_safe(self) -> None:
        """Stop the progress timer from a non-Qt thread via QTimer.singleShot."""
        try:
            QTimer.singleShot(0, self._timer.stop)
        except Exception:
            pass

    def _poll_progress(self) -> None:
        """Called every 150 ms on the Qt main thread to emit progress."""
        if self._state != STATE_PLAYING:
            self._timer.stop()
            return
        if self._duration > 0:
            elapsed = time.monotonic() - self._start_time
            frac = min(elapsed / self._duration, 1.0)
            self.progress_changed.emit(frac)
            if frac >= 1.0:
                self._timer.stop()


# ── File resolution helper ────────────────────────────────────────────────────

def find_audio_file(resref: str, game_dir: Path | None = None,
                    project_dir: Path | None = None) -> Path | None:
    """
    Resolve a VO/sound resref to an actual audio file path.

    Search order:
      1. game_dir/streamwaves/<resref>.(wav|mp3|ogg)
      2. game_dir/streamvoice/<resref>.(wav|mp3|ogg)  (and subdirs 1 level deep)
      3. game_dir/override/<resref>.(wav|mp3|ogg)
      4. project_dir/<resref>.(wav|mp3|ogg)
      5. project_dir/audio/<resref>.(wav|mp3|ogg)

    Returns None if not found.
    """
    if not resref:
        return None

    name_lower = resref.lower()
    extensions = [".wav", ".mp3", ".ogg", ".flac"]

    def _candidates(base: Path) -> list[Path]:
        return [base / (name_lower + ext) for ext in extensions]

    search_dirs: list[Path] = []

    if game_dir and game_dir.exists():
        for sub in ("streamwaves", "streammusic"):
            d = game_dir / sub
            if d.exists():
                search_dirs.append(d)
                # one level of subdirectories (e.g. streamwaves/dan13/)
                try:
                    for child in d.iterdir():
                        if child.is_dir():
                            search_dirs.append(child)
                except OSError:
                    pass

        for sub in ("streamvoice", "override"):
            d = game_dir / sub
            if d.exists():
                search_dirs.append(d)
                try:
                    for child in d.iterdir():
                        if child.is_dir():
                            search_dirs.append(child)
                except OSError:
                    pass

    if project_dir and project_dir.exists():
        search_dirs.append(project_dir)
        search_dirs.append(project_dir / "audio")

    for base in search_dirs:
        for candidate in _candidates(base):
            if candidate.exists():
                log.debug("find_audio_file: found %s → %s", resref, candidate)
                return candidate

    log.debug("find_audio_file: '%s' not found in %d dirs", resref, len(search_dirs))
    return None
