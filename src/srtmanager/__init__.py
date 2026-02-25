from __future__ import annotations
import srt
from datetime import timedelta
from typing import Iterable, List, Callable, Optional


class SRTValidationError(Exception):
    """Raised when subtitle invariants are violated."""


class SRTManager:
    """
    Advanced, expressive, production-safe subtitle manager.

    Invariants
    ----------
    - Subtitles are sorted by start time.
    - Subtitles are sequentially indexed starting from 1.
    - No overlapping subtitles.
    - All timestamps >= 0.

    Transformations return new SRTManager instances
    unless explicitly documented otherwise.
    """

    # --------------------------------------------------
    # Constructor
    # --------------------------------------------------

    def __init__(self, subtitles: Optional[Iterable[srt.Subtitle]] = None):
        self._subtitles: List[srt.Subtitle] = []
        if subtitles:
            self._subtitles = self._normalize(subtitles)

    # --------------------------------------------------
    # Core Internal
    # --------------------------------------------------

    def _normalize(self, subs: Iterable[srt.Subtitle]) -> List[srt.Subtitle]:
        """Sort, reindex, and validate subtitles."""
        sorted_subs = sorted(subs, key=lambda x: x.start)

        normalized: List[srt.Subtitle] = []

        for i, sub in enumerate(sorted_subs, start=1):
            if sub.start < timedelta(0) or sub.end < timedelta(0):
                raise SRTValidationError("Negative timestamps not allowed.")

            if sub.end < sub.start:
                raise SRTValidationError("Subtitle end before start.")

            normalized.append(
                srt.Subtitle(
                    index=i,
                    start=sub.start,
                    end=sub.end,
                    content=sub.content.strip(),
                )
            )

        self._validate_no_overlap(normalized)
        return normalized

    def _validate_no_overlap(self, subs: List[srt.Subtitle]):
        for i in range(1, len(subs)):
            if subs[i - 1].end > subs[i].start:
                raise SRTValidationError(
                    f"Overlap detected:\n"
                    f"{subs[i-1].start} --> {subs[i-1].end}\n"
                    f"{subs[i].start} --> {subs[i].end}"
                )

    def _to_td(self, value) -> timedelta:
        if value is None:
            return None
        if isinstance(value, timedelta):
            return value
        if isinstance(value, (int, float)):
            return timedelta(seconds=float(value))
        raise TypeError("Time must be timedelta, int, or float.")

    # --------------------------------------------------
    # Constructors
    # --------------------------------------------------

    @classmethod
    def from_file(cls, path: str) -> SRTManager:
        with open(path, "r", encoding="utf-8") as f:
            return cls(srt.parse(f.read()))

    @classmethod
    def from_string(cls, raw: str) -> SRTManager:
        return cls(srt.parse(raw))

    # --------------------------------------------------
    # Basic Magic
    # --------------------------------------------------

    def copy(self) -> SRTManager:
        return SRTManager(self._subtitles)

    def __len__(self):
        return len(self._subtitles)

    def __repr__(self):
        return f"SRTManager({len(self)} subtitles, duration={self.duration})"

    def __getitem__(self, item):
        if isinstance(item, slice):
            return self.slice(item.start, item.stop)
        if isinstance(item, str):
            return self.find(item)
        return self._subtitles[item]

    # --------------------------------------------------
    # Time Properties
    # --------------------------------------------------

    @property
    def start(self) -> timedelta:
        return self._subtitles[0].start if self._subtitles else timedelta(0)

    @property
    def end(self) -> timedelta:
        return self._subtitles[-1].end if self._subtitles else timedelta(0)

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    @duration.setter
    def duration(self, new_duration):
        """Scale subtitles to fit new duration."""
        if not self._subtitles:
            return

        new_duration = self._to_td(new_duration)
        old_seconds = self.duration.total_seconds()

        if old_seconds == 0:
            return

        scale = new_duration.total_seconds() / old_seconds
        base = self.start

        scaled = (
            srt.Subtitle(
                index=sub.index,
                start=base + timedelta(
                    seconds=(sub.start - base).total_seconds() * scale
                ),
                end=base + timedelta(
                    seconds=(sub.end - base).total_seconds() * scale
                ),
                content=sub.content,
            )
            for sub in self._subtitles
        )

        self._subtitles = self._normalize(scaled)

    # --------------------------------------------------
    # Shift
    # --------------------------------------------------

    def shift(self, seconds: float) -> SRTManager:
        offset = timedelta(seconds=seconds)

        shifted = (
            srt.Subtitle(
                index=sub.index,
                start=max(sub.start + offset, timedelta(0)),
                end=max(sub.end + offset, timedelta(0)),
                content=sub.content,
            )
            for sub in self._subtitles
        )

        return SRTManager(shifted)

    def __lshift__(self, seconds):
        """Shift earlier."""
        return self.shift(-seconds)

    def __rshift__(self, seconds):
        """Shift later."""
        return self.shift(seconds)

    # --------------------------------------------------
    # Merge
    # --------------------------------------------------

    def __add__(self, other):
        if isinstance(other, srt.Subtitle):
            other = SRTManager([other])

        if not isinstance(other, SRTManager):
            raise TypeError("Can only merge SRTManager")

        if not self._subtitles:
            return other.copy()
        if not other._subtitles:
            return self.copy()

        offset = max(self.end - other.start, timedelta(0))
        other_shifted = other.shift(offset.total_seconds())

        merged = list(self._subtitles) + list(other_shifted._subtitles)
        return SRTManager(merged)

    # --------------------------------------------------
    # Slice (with clipping)
    # --------------------------------------------------

    def slice(self, start=None, end=None) -> SRTManager:
        if not self._subtitles:
            return SRTManager()

        start = self._to_td(start) or self.start
        end = self._to_td(end) or self.end

        clipped = []

        for sub in self._subtitles:
            if sub.end <= start or sub.start >= end:
                continue

            clipped.append(
                srt.Subtitle(
                    index=sub.index,
                    start=max(sub.start, start),
                    end=min(sub.end, end),
                    content=sub.content,
                )
            )

        return SRTManager(clipped)

    # --------------------------------------------------
    # Find
    # --------------------------------------------------

    def find(self, text: str, case_sensitive=False) -> SRTManager:
        if not case_sensitive:
            text = text.lower()

        matches = (
            sub
            for sub in self._subtitles
            if text in (
                sub.content if case_sensitive else sub.content.lower()
            )
        )

        return SRTManager(matches)

    # --------------------------------------------------
    # Split
    # --------------------------------------------------

    def split(self, delimiter="<line>") -> List[SRTManager]:
        parts, current = [], []

        for sub in self._subtitles:
            if sub.content.strip() == delimiter:
                if current:
                    parts.append(SRTManager(current))
                    current = []
            else:
                current.append(sub)

        if current:
            parts.append(SRTManager(current))

        return parts

    # --------------------------------------------------
    # Join
    # --------------------------------------------------

    def join_as_single(self, sep=" ") -> Optional[srt.Subtitle]:
        if not self._subtitles:
            return None

        return srt.Subtitle(
            index=1,
            start=self.start,
            end=self.end,
            content=sep.join(sub.content.strip() for sub in self._subtitles),
        )

    # --------------------------------------------------
    # Gap Compression
    # --------------------------------------------------

    def compress_gaps(self) -> SRTManager:
        if not self._subtitles:
            return self

        new_subs = []
        current_time = self.start

        for sub in self._subtitles:
            duration = sub.end - sub.start
            new_subs.append(
                srt.Subtitle(
                    index=sub.index,
                    start=current_time,
                    end=current_time + duration,
                    content=sub.content,
                )
            )
            current_time += duration

        return SRTManager(new_subs)

    # --------------------------------------------------
    # Utilities
    # --------------------------------------------------

    def map_content(self, fn: Callable[[str], str]) -> SRTManager:
        transformed = (
            srt.Subtitle(
                index=sub.index,
                start=sub.start,
                end=sub.end,
                content=fn(sub.content),
            )
            for sub in self._subtitles
        )
        return SRTManager(transformed)

    def to_plain_text(self, sep="\n") -> str:
        return sep.join(sub.content.strip() for sub in self._subtitles)

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(srt.compose(self._subtitles))

    # --------------------------------------------------
    # Raw Add (validated)
    # --------------------------------------------------

    def add_raw(self, new_subs: Iterable[srt.Subtitle]):
        """
        Add subtitles as-is.
        Raises SRTValidationError on overlap.
        """
        combined = list(self._subtitles) + list(new_subs)
        self._subtitles = self._normalize(combined)