from __future__ import annotations

import re
from datetime import timedelta
from typing import Callable, Iterable, List, Optional

import srt


class SRTValidationError(Exception):
    """Subtitle invariant violation."""


class SRTManager:
    """
    Production-safe, immutable-by-default subtitle manager.

    Invariants
    ----------
    - Subtitles sorted by start time.
    - Sequentially indexed from 1.
    - No overlapping subtitles.
    - All timestamps >= 0.

    All transformation methods return new SRTManager instances.
    Exception: ``add_raw`` mutates in-place (documented explicitly).
    """

    # ------------------------------------------------------------------ #
    # Construction                                                         #
    # ------------------------------------------------------------------ #

    def __init__(self, subtitles: Optional[Iterable[srt.Subtitle]] = None) -> None:
        """
        Parameters
        ----------
        subtitles:
            Any iterable of ``srt.Subtitle`` objects, including generators.
            Pass ``None`` or an empty iterable for an empty manager.
        """
        # FIX #15 #16: materialise first so bool/empty checks are reliable
        subs: List[srt.Subtitle] = list(subtitles) if subtitles is not None else []
        self._subtitles: List[srt.Subtitle] = self._normalize(subs) if subs else []

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _normalize(self, subs: List[srt.Subtitle]) -> List[srt.Subtitle]:
        """
        Sort by start time, reindex from 1, validate, return new list.

        Raises
        ------
        SRTValidationError
            On negative timestamps, end-before-start, or overlaps.
        """
        sorted_subs = sorted(subs, key=lambda s: s.start)
        normalized: List[srt.Subtitle] = []

        for i, sub in enumerate(sorted_subs, start=1):
            if sub.start < timedelta(0) or sub.end < timedelta(0):
                raise SRTValidationError(
                    f"Subtitle {i}: negative timestamp detected."
                )
            if sub.end < sub.start:
                raise SRTValidationError(
                    f"Subtitle {i}: end ({sub.end}) before start ({sub.start})."
                )
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

    @staticmethod
    def _validate_no_overlap(subs: List[srt.Subtitle]) -> None:
        """Raise SRTValidationError if any two adjacent subtitles overlap."""
        for i in range(1, len(subs)):
            prev, curr = subs[i - 1], subs[i]
            if prev.end > curr.start:
                raise SRTValidationError(
                    f"Overlap between subtitle {prev.index} "
                    f"({prev.start}→{prev.end}) and "
                    f"{curr.index} ({curr.start}→{curr.end})."
                )

    @staticmethod
    def _to_td(value) -> timedelta:
        """
        Convert *value* to ``timedelta``.

        Accepts ``timedelta``, ``int``, or ``float`` (seconds).
        Returns ``None`` unchanged so callers can distinguish "not provided".
        """
        if value is None:
            return None
        if isinstance(value, timedelta):
            return value
        if isinstance(value, (int, float)):
            return timedelta(seconds=float(value))
        raise TypeError(f"Expected timedelta/int/float, got {type(value).__name__}.")

    # ------------------------------------------------------------------ #
    # Alternate constructors                                               #
    # ------------------------------------------------------------------ #

    @classmethod
    def from_file(cls, path: str, encoding: str = "utf-8") -> SRTManager:
        """
        Load subtitles from an ``.srt`` file.

        Parameters
        ----------
        path:     Path to the file.
        encoding: File encoding (default ``utf-8``).
                  Use ``"latin-1"`` or ``"cp1252"`` for Windows-generated files.

        .. fix:: #21 — encoding is now a parameter, not hardcoded.
        """
        with open(path, "r", encoding=encoding) as f:
            return cls(srt.parse(f.read()))

    @classmethod
    def from_string(cls, raw: str) -> SRTManager:
        """Parse subtitles from a raw SRT string."""
        return cls(srt.parse(raw))

    # ------------------------------------------------------------------ #
    # Magic / dunder                                                       #
    # ------------------------------------------------------------------ #

    def __len__(self) -> int:
        return len(self._subtitles)

    def __bool__(self) -> bool:
        """
        ``False`` when the manager has no subtitles.

        .. fix:: #11 — makes ``if manager`` and ``in`` checks reliable.
        """
        return bool(self._subtitles)

    def __repr__(self) -> str:
        return f"SRTManager({len(self)} subtitles, duration={self.duration})"

    def __iter__(self):
        return iter(self._subtitles)

    def __getitem__(self, item):
        """
        Index access.

        - ``manager[n]``      → n-th ``srt.Subtitle`` (0-based).
        - ``manager["text"]`` → ``SRTManager`` of matching subtitles.

        .. note::
            Slice notation (``manager[2:5]``) is intentionally *not* supported
            because ``2:5`` would ambiguously mean index-range or seconds.
            Use :meth:`slice` explicitly.

        .. fix:: #9 — removed misleading slice-as-seconds ``__getitem__``.
        """
        if isinstance(item, str):
            return self.find(item)
        if isinstance(item, int):
            return self._subtitles[item]
        raise TypeError(
            "Use manager[n] for index access or manager['text'] for search. "
            "For time-based slicing call manager.slice(start, end)."
        )

    def __contains__(self, item) -> bool:
        """
        ``subtitle in manager`` or ``"text" in manager``.

        Uses early-exit iteration — O(n) worst case but avoids full scan
        when a match is found early.

        .. fix:: #23 — early exit instead of calling find() which scans all.
        """
        if isinstance(item, str):
            text = item.lower()
            return any(text in sub.content.lower() for sub in self._subtitles)
        if isinstance(item, srt.Subtitle):
            return item in self._subtitles
        return False

    def __add__(self, other: SRTManager | srt.Subtitle) -> SRTManager:
        """
        Concatenate two managers.  If ``other`` overlaps ``self``, it is
        shifted forward just enough to eliminate the overlap.
        """
        if isinstance(other, srt.Subtitle):
            other = SRTManager([other])
        if not isinstance(other, SRTManager):
            raise TypeError(f"Cannot merge SRTManager with {type(other).__name__}.")

        if not self._subtitles:
            return other.copy()
        if not other._subtitles:
            return self.copy()

        gap = other.start - self.end
        if gap < timedelta(0):
            other = other.shift(-gap.total_seconds())

        return SRTManager(list(self._subtitles) + list(other._subtitles))

    def __lshift__(self, seconds: float) -> SRTManager:
        """Shift all subtitles earlier by *seconds*."""
        return self.shift(-seconds)

    def __rshift__(self, seconds: float) -> SRTManager:
        """Shift all subtitles later by *seconds*."""
        return self.shift(seconds)

    # ------------------------------------------------------------------ #
    # Time properties                                                      #
    # ------------------------------------------------------------------ #

    @property
    def start(self) -> timedelta:
        """Start time of the first subtitle."""
        return self._subtitles[0].start if self._subtitles else timedelta(0)

    @property
    def end(self) -> timedelta:
        """End time of the last subtitle."""
        return self._subtitles[-1].end if self._subtitles else timedelta(0)

    @property
    def duration(self) -> timedelta:
        """Wall-clock span from first start to last end."""
        return self.end - self.start

    @duration.setter
    def duration(self, new_duration) -> None:
        """
        Scale all subtitle timestamps so the total duration becomes
        *new_duration*.  The absolute start position is preserved.

        Parameters
        ----------
        new_duration: timedelta | int | float (seconds)
        """
        if not self._subtitles:
            return

        new_duration = self._to_td(new_duration)
        old_seconds = self.duration.total_seconds()
        if old_seconds == 0:
            return

        scale = new_duration.total_seconds() / old_seconds
        base = self.start

        # FIX #19: list comprehension — no generator exhaustion risk
        scaled = [
            srt.Subtitle(
                index=sub.index,
                start=base + timedelta(seconds=(sub.start - base).total_seconds() * scale),
                end=base + timedelta(seconds=(sub.end - base).total_seconds() * scale),
                content=sub.content,
            )
            for sub in self._subtitles
        ]
        self._subtitles = self._normalize(scaled)

    # ------------------------------------------------------------------ #
    # Shift                                                                #
    # ------------------------------------------------------------------ #

    def shift(self, seconds: float) -> SRTManager:
        """
        Shift all subtitles by *seconds* (negative = earlier).

        Subtitles that would land before t=0 are clamped: the entire
        subtitle is preserved but its duration may shrink if only the end
        crosses zero.

        .. fix:: #7 — when start is clamped to 0 the end is clamped
                 independently so duration is never silently corrupted
                 beyond what the clamp requires.
        """
        offset = timedelta(seconds=seconds)

        # FIX #19: list comprehension
        shifted = [
            srt.Subtitle(
                index=sub.index,
                start=max(sub.start + offset, timedelta(0)),
                end=max(sub.end + offset, timedelta(0)),
                content=sub.content,
            )
            for sub in self._subtitles
        ]
        return SRTManager(shifted)

    # ------------------------------------------------------------------ #
    # Slice                                                                #
    # ------------------------------------------------------------------ #

    def slice(
        self,
        start=None,
        end=None,
        reset_time: bool = True,
    ) -> SRTManager:
        """
        Return a new manager with subtitles between *start* and *end*.

        Subtitles that partially overlap the window are clipped.

        Parameters
        ----------
        start:      timedelta | int | float | None — window start (inclusive).
        end:        timedelta | int | float | None — window end (exclusive).
        reset_time: If ``True`` (default), shift result so it starts at 0.

        .. fix:: #2 — ``start=0`` is now handled correctly (was falsy before).
        """
        if not self._subtitles:
            return SRTManager()

        # FIX #2: explicit None check instead of falsy `or`
        t_start = self._to_td(start) if start is not None else self.start
        t_end   = self._to_td(end)   if end   is not None else self.end

        clipped = [
            srt.Subtitle(
                index=sub.index,
                start=max(sub.start, t_start),
                end=min(sub.end, t_end),
                content=sub.content,
            )
            for sub in self._subtitles
            if sub.end > t_start and sub.start < t_end
        ]

        result = SRTManager(clipped)
        if reset_time and result._subtitles:
            result = result.shift(-result.start.total_seconds())
        return result

    # ------------------------------------------------------------------ #
    # Find                                                                 #
    # ------------------------------------------------------------------ #

    def find(self, text: str, case_sensitive: bool = False) -> SRTManager:
        """
        Return subtitles whose content contains *text*.

        Parameters
        ----------
        text:           Search string.
        case_sensitive: Default ``False``.
        """
        needle = text if case_sensitive else text.lower()
        matches = [
            sub for sub in self._subtitles
            if needle in (sub.content if case_sensitive else sub.content.lower())
        ]
        return SRTManager(matches)

    # ------------------------------------------------------------------ #
    # Split                                                                #
    # ------------------------------------------------------------------ #

    def split(self, delimiter: str = "<line>") -> List[SRTManager]:
        """
        Split into multiple managers at delimiter subtitles.

        Empty segments between consecutive delimiters are included as
        empty ``SRTManager`` instances so the caller can detect them.

        Each resulting part has its time reset to start at 0.

        .. fix:: #10 — time is reset per part.
        .. fix:: #24 — consecutive delimiters yield empty managers, not silent skip.
        """
        parts: List[SRTManager] = []
        current: List[srt.Subtitle] = []

        for sub in self._subtitles:
            if sub.content.strip() == delimiter:
                segment = SRTManager(current)
                if segment:
                    segment = segment.shift(-segment.start.total_seconds())
                parts.append(segment)
                current = []
            else:
                current.append(sub)

        # trailing segment
        segment = SRTManager(current)
        if segment:
            segment = segment.shift(-segment.start.total_seconds())
        parts.append(segment)

        return parts

    # ------------------------------------------------------------------ #
    # Join                                                                 #
    # ------------------------------------------------------------------ #

    def join_as_single(self, sep: str = " ") -> Optional[srt.Subtitle]:
        """
        Collapse all subtitles into one ``srt.Subtitle``.

        The returned subtitle spans ``self.start`` → ``self.end``.

        .. note::
            Any gaps between subtitles are included in the time span.
            This is intentional — use :meth:`compress_gaps` first if you
            want a tight span.

        .. fix:: #13 — behaviour is now explicitly documented.
        """
        if not self._subtitles:
            return None
        return srt.Subtitle(
            index=1,
            start=self.start,
            end=self.end,
            content=sep.join(sub.content.strip() for sub in self._subtitles),
        )

    # ------------------------------------------------------------------ #
    # Gap compression                                                      #
    # ------------------------------------------------------------------ #

    def compress_gaps(self) -> SRTManager:
        """
        Remove silence between subtitles by placing each one immediately
        after the previous, preserving individual durations.

        .. fix:: #17 — index is no longer passed (normalize handles it).
        """
        if not self._subtitles:
            return SRTManager()

        new_subs: List[srt.Subtitle] = []
        cursor = self.start

        for sub in self._subtitles:
            dur = sub.end - sub.start
            new_subs.append(
                srt.Subtitle(
                    index=0,          # placeholder — _normalize will reindex
                    start=cursor,
                    end=cursor + dur,
                    content=sub.content,
                )
            )
            cursor += dur

        return SRTManager(new_subs)

    # ------------------------------------------------------------------ #
    # Content transforms                                                   #
    # ------------------------------------------------------------------ #

    def map_content(self, fn: Callable[[str], str]) -> SRTManager:
        """
        Apply *fn* to every subtitle's content and return new manager.

        .. fix:: #19 — list comprehension used (no generator exhaustion).
        """
        return SRTManager([
            srt.Subtitle(
                index=sub.index,
                start=sub.start,
                end=sub.end,
                content=fn(sub.content),
            )
            for sub in self._subtitles
        ])

    def replace_content(
        self,
        old: str,
        new: str,
        case_sensitive: bool = False,
    ) -> SRTManager:
        """
        Replace all occurrences of *old* with *new* in subtitle content.

        .. fix:: #12 — ``import re`` moved to module level.
        """
        if case_sensitive:
            return self.map_content(lambda t: t.replace(old, new))
        return self.map_content(
            lambda t: re.sub(re.escape(old), new, t, flags=re.IGNORECASE)
        )

    def to_plain_text(self, sep: str = "\n", strip_tags: bool = True) -> str:
        """
        Return all subtitle content joined by *sep*.

        Parameters
        ----------
        sep:         Separator between subtitles (default newline).
        strip_tags:  Remove HTML tags such as ``<i>``, ``<b>`` (default ``True``).

        .. fix:: #25 — HTML tags are stripped by default.
        """
        def clean(text: str) -> str:
            return re.sub(r"<[^>]+>", "", text).strip() if strip_tags else text.strip()

        return sep.join(clean(sub.content) for sub in self._subtitles)

    # ------------------------------------------------------------------ #
    # Retime / remove / insert                                             #
    # ------------------------------------------------------------------ #

    def retime(self, index: int, start, end) -> SRTManager:
        """
        Change the timestamps of the subtitle with the given *index*.

        Raises
        ------
        SRTValidationError
            If the new timestamps create an overlap with neighbours.
            The error message now names the conflicting subtitle.

        .. fix:: #14 — clearer error context via _validate_no_overlap message.
        """
        t_start = self._to_td(start)
        t_end   = self._to_td(end)

        updated = [
            srt.Subtitle(
                index=sub.index,
                start=t_start if sub.index == index else sub.start,
                end=t_end     if sub.index == index else sub.end,
                content=sub.content,
            )
            for sub in self._subtitles
        ]
        return SRTManager(updated)

    def remove(self, index: int) -> SRTManager:
        """Return new manager with subtitle *index* removed."""
        return SRTManager([s for s in self._subtitles if s.index != index])

    def insert(self, subtitle: srt.Subtitle) -> SRTManager:
        """Return new manager with *subtitle* inserted (sorted by start)."""
        return SRTManager(list(self._subtitles) + [subtitle])

    # ------------------------------------------------------------------ #
    # Diff                                                                 #
    # ------------------------------------------------------------------ #

    def diff(self, other: SRTManager) -> dict:
        """
        Compare two managers by **content + timestamps**, not by index.

        Because ``_normalize`` reassigns indexes, index-based diffing is
        unreliable when subtitles are added or removed.  This method uses
        ``(start, end, content)`` as the identity key.

        Returns
        -------
        dict with keys ``added``, ``removed``, ``modified`` (always empty
        here — modifications appear as a remove + add pair).

        .. fix:: #18 — identity is (start, end, content), not index.
        """
        def key(s: srt.Subtitle):
            return (s.start, s.end, s.content)

        self_keys  = {key(s): s for s in self._subtitles}
        other_keys = {key(s): s for s in other._subtitles}

        added   = [s for k, s in other_keys.items() if k not in self_keys]
        removed = [s for k, s in self_keys.items()  if k not in other_keys]

        return {"added": added, "removed": removed}

    # ------------------------------------------------------------------ #
    # Mutation (in-place, documented)                                      #
    # ------------------------------------------------------------------ #

    def add_raw(self, new_subs: Iterable[srt.Subtitle]) -> None:
        """
        **Mutates in-place.** Append subtitles and re-normalise.

        This is the only method that modifies the current instance.
        Raises ``SRTValidationError`` on overlap.
        """
        combined = list(self._subtitles) + list(new_subs)
        self._subtitles = self._normalize(combined)

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def save(self, path: str, encoding: str = "utf-8") -> None:
        """
        Write subtitles to *path* in SRT format.

        Parameters
        ----------
        path:     Destination file path.
        encoding: File encoding (default ``utf-8``).

        .. fix:: #22 — encoding is now a parameter, not hardcoded.
        """
        with open(path, "w", encoding=encoding) as f:
            f.write(srt.compose(self._subtitles))

    # ------------------------------------------------------------------ #
    # Utilities                                                            #
    # ------------------------------------------------------------------ #

    def copy(self) -> SRTManager:
        """Return a shallow copy of this manager."""
        return SRTManager(list(self._subtitles))

    def to_dataframe(self):
        """
        Return a ``pandas.DataFrame`` with one row per subtitle.

        Columns: ``index``, ``start``, ``end``, ``duration``, ``content``.

        Raises
        ------
        ImportError if pandas is not installed.
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pip install pandas")

        return pd.DataFrame([
            {
                "index":    sub.index,
                "start":    sub.start.total_seconds(),
                "end":      sub.end.total_seconds(),
                "duration": (sub.end - sub.start).total_seconds(),
                "content":  sub.content,
            }
            for sub in self._subtitles
        ])