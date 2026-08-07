"""
ASS subtitle generation in the viral "Reddit story" Shorts style.

A dark card is drawn in the center of the frame (by the renderer) and
the narration is rendered inside it as word-by-word captions: the
sentence accumulates while the word currently being spoken pops in a
highlight colour. Timing comes from the TTS provider's real
word-boundary timestamps when available, falling back to an even spread
across the narration duration.

The card geometry constants must match the drawbox used in
video/renderer.py.
"""

from __future__ import annotations

import re
from pathlib import Path

from config.settings import Config
from providers.base import WordTiming

# Card geometry (1080x1920 canvas) — keep in sync with renderer.py.
CARD_X = 60
CARD_Y = 620
CARD_W = 960
CARD_H = 680

# ASS colours use &HAABBGGRR&.
_HIGHLIGHT_COLOURS = {
    "yellow": "&H0000FFFF&",
    "orange": "&H0000A5FF&",
    "white": "&H00FFFFFF&",
    "red": "&H000000FF&",
    "green": "&H0000FF00&",
}

_SENTENCE_END = re.compile(r"[.!?…]$")


def _format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _header_style(font_size: int) -> str:
    """Small grey card header (the fake Reddit username bar)."""
    header_margin_v = 1920 - (CARD_Y + 40)  # sits just inside the card's top edge
    return (
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
        f"Style: CardHeader,Arial,{max(font_size // 2, 20)},"
        f"&H00AAAAAA,&H00000000,&H00000000,0,1,0,2,{CARD_X},{CARD_X},{header_margin_v}\n"
    )


def _even_word_timings(words: list[str], duration: float) -> list[WordTiming]:
    """Fallback timing used when the TTS provider gives no word boundaries."""
    if not words:
        return [WordTiming("", 0.0, duration)]
    step = duration / len(words)
    return [
        WordTiming(word=word, start=i * step, end=(i + 1) * step)
        for i, word in enumerate(words)
    ]


def generate_ass(
    narration_text: str,
    duration_seconds: float,
    word_timings: list[WordTiming] | None,
    cfg: Config,
    out_path: Path,
) -> Path:
    """Write a Reddit-card .ass file synced to the narration words."""
    words = narration_text.split()
    if not words:
        words = [""]

    timings = word_timings or _even_word_timings(words, duration_seconds)
    if len(timings) < len(words):
        # Provider returned fewer boundaries than visible words (e.g. some
        # edge-tts quirks). Pad with an even spread over the tail.
        timings = _even_word_timings(words, duration_seconds)

    font_size = cfg.subtitles.font_size
    highlight = _HIGHLIGHT_COLOURS.get(
        cfg.subtitles.highlight_color, _HIGHLIGHT_COLOURS["yellow"]
    )
    base_ass = "&H00000000&" if cfg.subtitles.font_color == "black" else "&H00FFFFFF&"
    outline_ass = "&H00000000&" if cfg.subtitles.outline_color == "black" else "&H00FFFFFF&"

    lines = [
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: 1080\nPlayResY: 1920\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
        f"Style: Default,Arial,{font_size},{base_ass},{outline_ass},"
        f"&H00000000,1,{max(font_size // 12, 3)},0,5,{CARD_X},{CARD_X},0\n"
        f"{_header_style(font_size)}\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Text\n"
    ]

    # Card header (fake Reddit user bar).
    header_text = cfg.subtitles.card_header
    if header_text:
        lines.append(
            f"Dialogue: 0,0:00:00.00,{_format_timestamp(duration_seconds)},"
            f"CardHeader,{header_text}\n"
        )

    # Split word boundaries into sentences (punctuation signals the end).
    sentences: list[list[WordTiming]] = []
    current: list[WordTiming] = []
    for wt in timings:
        current.append(wt)
        if _SENTENCE_END.search(wt.word):
            sentences.append(current)
            current = []
    if current:
        sentences.append(current)

    for sentence in sentences:
        for i, wt in enumerate(sentence):
            # Pop the current word, then reset to the base colour.
            prefix = " ".join(w.word for w in sentence[:i])
            popped = f"{{\\c{highlight}}}{sentence[i].word}{{\\c{base_ass}}}"
            shown = f"{prefix} {popped}" if prefix else popped
            start = wt.start
            end = sentence[i + 1].start if i + 1 < len(sentence) else wt.end + 0.05
            lines.append(
                f"Dialogue: 0,{_format_timestamp(start)},{_format_timestamp(end)},"
                f"Default,{shown}\n"
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(lines), encoding="utf-8")
    return out_path
