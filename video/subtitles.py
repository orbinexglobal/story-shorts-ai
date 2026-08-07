"""
ASS subtitle generation in viral Shorts karaoke style.

Captions appear one sentence at a time near the bottom of the frame.
Inside a sentence the words accumulate as they are spoken and the word
currently being spoken pops in a highlight colour (yellow by default).
Timing comes from the TTS provider's real word-boundary timestamps when
available, falling back to an even spread across the narration duration.
"""

from __future__ import annotations

import re
from pathlib import Path

from config.settings import Config
from providers.base import WordTiming

# ASS colours use &HAABBGGRR&.
_HIGHLIGHT_COLOURS = {
    "yellow": "&H0000FFFF&",
    "orange": "&H0000A5FF&",
    "white": "&H00FFFFFF&",
    "red": "&H000000FF&",
    "green": "&H0000FF00&",
}

_SENTENCE_END = re.compile(r"[.!?…]$")

# Bottom-centre caption area on the 1080x1920 canvas.
_ALIGNMENT = 2      # bottom-centre
_MARGIN_V = 470     # distance from the bottom edge (~y 1450)


def _format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


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
    """Write a karaoke .ass file synced to the narration words."""
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
        f"&H00000000,1,{max(font_size // 12, 3)},0,{_ALIGNMENT},0,0,{_MARGIN_V}\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Text\n"
    ]

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
