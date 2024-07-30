"""
PC-BASIC - interface package
Video, input and audio handlers

(c) 2013--2023 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

from .base import InitFailed, video_plugins, audio_plugins
from .interface import Interface, InterfaceAsync
from ..compat import EMSCRIPTEN

# video plugins
from .video import VideoPlugin
from .video_pygame import VideoPygame

if not EMSCRIPTEN:
    from .video_ansi import VideoANSI
    from .video_cli import VideoCLI
    from .video_curses import VideoCurses
    from .video_sdl2 import VideoSDL2

# audio plugins
from .audio import AudioPlugin
from .audio_pygame import AudioPygame

if not EMSCRIPTEN:
    from .audio_beep import AudioBeep
    from .audio_sdl2 import AudioSDL2
    from .audio_portaudio import AudioPortAudio
