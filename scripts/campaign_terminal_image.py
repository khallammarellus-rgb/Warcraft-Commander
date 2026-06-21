"""Half-block terminal images for the campaign setup TUI."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.color import Color
from rich.console import Console, ConsoleOptions, RenderResult
from rich.segment import Segment
from rich.style import Style

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment,misc]


DEFAULT_TERMINAL_COLS = 110
DEFAULT_TERMINAL_ROWS = 52
WELCOME_CREST_MAX_WIDTH = 68


class HalfBlockImage:
    """Rich renderable: one terminal cell = two image rows (▀)."""

    def __init__(self, path: Path, *, max_width: int = WELCOME_CREST_MAX_WIDTH) -> None:
        self.path = Path(path)
        self.max_width = max_width
        self._lines: list[list[Segment]] | None = None
        self.char_width = 0
        self.char_height = 0

    def _build(self) -> None:
        if Image is None:
            raise RuntimeError("Pillow is required for terminal images")

        img = Image.open(self.path).convert("RGB")
        src_w, src_h = img.size
        new_w = min(self.max_width, src_w)
        new_h = max(2, int(new_w * src_h / src_w))
        if new_h % 2 == 1:
            new_h += 1
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        pixels = img.load()

        lines: list[list[Segment]] = []
        for y in range(0, new_h, 2):
            row: list[Segment] = []
            for x in range(new_w):
                top = pixels[x, y]
                bottom = pixels[x, y + 1]
                if sum(top) < 24 and sum(bottom) < 24:
                    row.append(Segment(" "))
                    continue
                style = Style.from_color(
                    Color.from_rgb(top[0], top[1], top[2]),
                    Color.from_rgb(bottom[0], bottom[1], bottom[2]),
                )
                row.append(Segment("▀", style=style))
            lines.append(row)

        self._lines = lines
        self.char_width = new_w
        self.char_height = len(lines)

    def __rich_console__(
        self,
        console: Console,
        options: ConsoleOptions,
    ) -> RenderResult:
        if self._lines is None:
            self._build()
        assert self._lines is not None
        for row in self._lines:
            yield from row
            yield Segment.line()


def crest_display_metrics(path: Path, *, max_width: int = WELCOME_CREST_MAX_WIDTH) -> tuple[int, int]:
    """Return (char_width, char_height) for a crest image at half-block scale."""
    renderable = HalfBlockImage(path, max_width=max_width)
    renderable._build()
    return renderable.char_width, renderable.char_height


def recommended_terminal_size(
    crest_path: Path | None,
    *,
    min_cols: int = DEFAULT_TERMINAL_COLS,
    min_rows: int = DEFAULT_TERMINAL_ROWS,
) -> tuple[int, int]:
    """Rows/cols that fit the crest plus the two-panel wizard chrome."""
    cols = min_cols
    rows = min_rows
    if crest_path is not None and crest_path.exists() and Image is not None:
        width, height = crest_display_metrics(crest_path)
        cols = max(cols, width + 42)
        rows = max(rows, height + 30)
    return cols, rows


def resize_terminal(cols: int, rows: int) -> None:
    """Request terminal size via DECSLPP (xterm / Terminal.app / iTerm)."""
    sys.stdout.write(f"\033[8;{rows};{cols}t")
    sys.stdout.flush()


def try_load_halfblock_image(path: Path | None, *, max_width: int = WELCOME_CREST_MAX_WIDTH) -> HalfBlockImage | None:
    if path is None or not path.exists() or Image is None:
        return None
    try:
        renderable = HalfBlockImage(path, max_width=max_width)
        renderable._build()
        return renderable
    except OSError:
        return None