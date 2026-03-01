# SRTManager — Complete Documentation

> A production-safe Python library for reading, editing, transforming, and saving `.srt` subtitle files.

---

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Core Concepts](#core-concepts)
4. [Creating a Manager](#creating-a-manager)
5. [Properties](#properties)
6. [Shifting & Timing](#shifting--timing)
7. [Slicing](#slicing)
8. [Merging](#merging)
9. [Searching](#searching)
10. [Editing Content](#editing-content)
11. [Splitting](#splitting)
12. [Gap Compression](#gap-compression)
13. [Retime / Remove / Insert](#retime--remove--insert)
14. [Diffing](#diffing)
15. [Exporting & Saving](#exporting--saving)
16. [Mutation: add_raw](#mutation-add_raw)
17. [Error Reference](#error-reference)
18. [Full Workflow Examples](#full-workflow-examples)

---

## Installation

```bash
pip install srtmanager
```

```python
from srtmanager import SRTManager, SRTValidationError
```

---

## Quick Start

```python
from srtmanager import SRTManager

# Load a file
mgr = SRTManager.from_file("movie.srt")

# Shift all subtitles 2.5 seconds later
mgr2 = mgr >> 2.5

# Extract a 60-second clip starting at t=120s
clip = mgr.slice(120, 180)

# Save it
clip.save("clip.srt")
```

---

## Core Concepts

**Immutability by default.**
Every transformation method returns a *new* `SRTManager`. The original is never changed. The only exception is `add_raw()`, which is explicitly documented as mutating.

**Invariants enforced automatically.**
On every construction the library:
- Sorts subtitles by start time
- Reindexes from 1
- Validates no negative timestamps
- Validates no overlapping subtitles
- Strips leading/trailing whitespace from content

If any invariant is violated, `SRTValidationError` is raised immediately.

---

## Creating a Manager

### From a file

```python
mgr = SRTManager.from_file("subtitles.srt")

# Non-UTF-8 files (common on Windows)
mgr = SRTManager.from_file("subtitles.srt", encoding="latin-1")
mgr = SRTManager.from_file("subtitles.srt", encoding="cp1252")
```

### From a string

```python
raw = """
1
00:00:01,000 --> 00:00:03,000
Hello world

2
00:00:04,000 --> 00:00:06,000
How are you?
"""
mgr = SRTManager.from_string(raw)
```

### From a list of `srt.Subtitle` objects

```python
import srt
from datetime import timedelta

subs = [
    srt.Subtitle(1, timedelta(seconds=1), timedelta(seconds=3), "Hello"),
    srt.Subtitle(2, timedelta(seconds=4), timedelta(seconds=6), "World"),
]
mgr = SRTManager(subs)
```

### Empty manager

```python
mgr = SRTManager()
# or
mgr = SRTManager([])
```

---

## Properties

```python
mgr = SRTManager.from_file("movie.srt")

len(mgr)          # number of subtitles
bool(mgr)         # False if empty
repr(mgr)         # "SRTManager(42 subtitles, duration=0:48:22)"

mgr.start         # timedelta — start of first subtitle
mgr.end           # timedelta — end of last subtitle
mgr.duration      # timedelta — total span (end - start)
```

### Iterating

```python
for sub in mgr:
    print(sub.index, sub.start, sub.content)
```

### Index access

```python
first = mgr[0]    # srt.Subtitle object (0-based)
last  = mgr[-1]   # last subtitle
```

> **Note:** `manager[2:5]` is intentionally not supported because `2:5`
> could mean indexes *or* seconds — ambiguous. Use `mgr.slice(2, 5)` explicitly.

### Membership

```python
"hello" in mgr          # True if any subtitle contains "hello" (case-insensitive)
some_subtitle in mgr    # True if that exact srt.Subtitle object is present
```

---

## Shifting & Timing

### Shift by seconds

```python
# Shift 3 seconds later
later = mgr >> 3
later = mgr.shift(3)

# Shift 1.5 seconds earlier
earlier = mgr << 1.5
earlier = mgr.shift(-1.5)
```

Subtitles that would fall below `t=0` are clamped at zero. Each timestamp
(start and end) is clamped independently so duration is only affected
when the clamp is unavoidable.

```python
# Example: subtitle at 0.5s→1.5s, shift back 1s
# start → max(0.5-1, 0) = 0.0
# end   → max(1.5-1, 0) = 0.5   (duration preserved: 1s)

# Example: subtitle at 0.2s→0.8s, shift back 1s
# start → max(0.2-1, 0) = 0.0
# end   → max(0.8-1, 0) = 0.0   (both clamped — subtitle becomes zero-duration)
```

### Rescale duration

Change the total duration while keeping relative timing proportional:

```python
# Scale everything to fit in exactly 30 minutes
mgr.duration = 1800          # seconds (int/float)

from datetime import timedelta
mgr.duration = timedelta(minutes=30)   # or timedelta
```

The absolute start position is preserved; only the relative spacing scales.

---

## Slicing

Extract a time window. Subtitles that partially overlap the window are clipped.

```python
# Seconds (int or float)
clip = mgr.slice(60, 120)          # 60s → 120s

# timedelta
from datetime import timedelta
clip = mgr.slice(timedelta(minutes=1), timedelta(minutes=2))

# Open-ended
clip = mgr.slice(start=60)         # from 60s to end
clip = mgr.slice(end=120)          # from beginning to 120s

# start=0 works correctly
clip = mgr.slice(0, 30)            # from t=0 to t=30s

# Keep original timestamps (don't reset to 0)
clip = mgr.slice(60, 120, reset_time=False)
```

By default (`reset_time=True`) the result is shifted so it starts at `t=0`.

---

## Merging

Combine two managers with `+`. If the second manager overlaps the first,
it is automatically shifted forward to eliminate the overlap.

```python
combined = intro + main + credits

# Adding a single srt.Subtitle
import srt
from datetime import timedelta

new_sub = srt.Subtitle(0, timedelta(seconds=10), timedelta(seconds=12), "Extra line")
updated = mgr + new_sub
```

---

## Searching

### Find by text

```python
# Case-insensitive (default)
results = mgr.find("hello")
results = mgr["hello"]          # shorthand

# Case-sensitive
results = mgr.find("Hello", case_sensitive=True)
```

Returns a new `SRTManager` with only matching subtitles. Returns an empty
manager (falsy) if nothing matches.

```python
results = mgr.find("xyz")
if not results:
    print("Nothing found")
```

### Check membership

```python
if "error" in mgr:
    print("Found an error subtitle")
```

---

## Editing Content

### Map a function over all content

```python
# Uppercase everything
upper = mgr.map_content(str.upper)

# Strip HTML bold tags
clean = mgr.map_content(lambda t: t.replace("<b>", "").replace("</b>", ""))
```

### Find and replace

```python
# Case-insensitive replacement (default)
fixed = mgr.replace_content("colour", "color")

# Case-sensitive
fixed = mgr.replace_content("OK", "Okay", case_sensitive=True)
```

### Export as plain text

```python
text = mgr.to_plain_text()              # HTML tags stripped, newline-separated
text = mgr.to_plain_text(sep=" ")       # space-separated
text = mgr.to_plain_text(strip_tags=False)  # keep HTML tags as-is
```

### Collapse all subtitles into one

```python
single = mgr.join_as_single()           # returns srt.Subtitle or None if empty
single = mgr.join_as_single(sep=" | ")  # custom separator
```

> **Note:** The resulting subtitle spans `start → end` of the entire manager,
> including any gaps between subtitles. Call `compress_gaps()` first if you
> want a tight span.

---

## Splitting

Split a manager into parts at delimiter subtitles.

```python
# Default delimiter is "<line>"
parts = mgr.split()

# Custom delimiter
parts = mgr.split(delimiter="---")

for part in parts:
    print(f"Part has {len(part)} subtitles, duration={part.duration}")
```

Each part starts at `t=0` (time-reset automatically).
Consecutive delimiters produce empty `SRTManager` instances — check with `bool(part)`.

**Typical use:** Mark section boundaries in your SRT with a delimiter subtitle,
then split and process/save each section independently.

```python
sections = mgr.split("<chapter>")
for i, section in enumerate(sections):
    if section:
        section.save(f"chapter_{i+1}.srt")
```

---

## Gap Compression

Remove silences between subtitles. Each subtitle is placed immediately after
the previous one, preserving individual durations.

```python
compressed = mgr.compress_gaps()
```

Useful before `join_as_single()` to get a tight span with no embedded gaps.

```python
single = mgr.compress_gaps().join_as_single()
```

---

## Retime / Remove / Insert

### Change timestamps of one subtitle

```python
# By index (1-based, as displayed in SRT files)
updated = mgr.retime(index=5, start=10.0, end=13.5)

from datetime import timedelta
updated = mgr.retime(index=5, start=timedelta(seconds=10), end=timedelta(seconds=13.5))
```

Raises `SRTValidationError` if the new timestamps overlap adjacent subtitles.

### Remove a subtitle

```python
shorter = mgr.remove(index=3)   # remove subtitle #3
```

### Insert a subtitle

```python
import srt
from datetime import timedelta

new_sub = srt.Subtitle(
    index=0,   # placeholder — will be reindexed automatically
    start=timedelta(seconds=25),
    end=timedelta(seconds=27),
    content="New subtitle here",
)
updated = mgr.insert(new_sub)
```

---

## Diffing

Compare two managers to find what changed. Identity is determined by
`(start, end, content)` — not by index, since indexes are reassigned
on every normalisation.

```python
diff = original.diff(edited)

print("Added:")
for sub in diff["added"]:
    print(f"  [{sub.start}] {sub.content}")

print("Removed:")
for sub in diff["removed"]:
    print(f"  [{sub.start}] {sub.content}")
```

> Modifications appear as one entry in `removed` (old version) and one in `added`
> (new version). There is no separate `"modified"` key.

---

## Exporting & Saving

### Save to file

```python
mgr.save("output.srt")

# Non-UTF-8 encoding
mgr.save("output.srt", encoding="latin-1")
```

### Convert to pandas DataFrame

```python
df = mgr.to_dataframe()
# Columns: index, start (seconds), end (seconds), duration (seconds), content

# Example: find subtitles longer than 5 seconds
long_ones = df[df["duration"] > 5]
```

Requires `pandas`: `pip install pandas`.

### Copy

```python
copy = mgr.copy()
```

---

## Mutation: add_raw

This is the **only** method that modifies the manager in place.
All other methods return new instances.

```python
import srt
from datetime import timedelta

new_subs = [
    srt.Subtitle(0, timedelta(seconds=100), timedelta(seconds=102), "Extra"),
]
mgr.add_raw(new_subs)   # mgr itself is changed
```

Raises `SRTValidationError` if any of the new subtitles overlap existing ones.

---

## Error Reference

All errors subclass `SRTValidationError`:

| Condition | Message |
|---|---|
| Negative timestamp | `"Subtitle N: negative timestamp detected."` |
| `end` before `start` | `"Subtitle N: end (...) before start (...)."` |
| Overlapping subtitles | `"Overlap between subtitle A (...→...) and B (...→...)."` |
| Wrong type to `shift`/`slice` | `TypeError: "Expected timedelta/int/float, got X."` |
| Wrong type to merge | `TypeError: "Cannot merge SRTManager with X."` |

```python
from srtmanager import SRTValidationError

try:
    mgr.retime(5, start=50, end=40)   # end before start
except SRTValidationError as e:
    print(f"Timing error: {e}")
```

---

## Full Workflow Examples

### 1. Fix subtitle delay

Video was muxed 2.3 seconds late — shift subtitles to compensate:

```python
mgr = SRTManager.from_file("movie.srt")
fixed = mgr >> 2.3
fixed.save("movie_fixed.srt")
```

---

### 2. Extract a highlight clip

```python
mgr = SRTManager.from_file("lecture.srt")

# Extract minutes 10–25
clip = mgr.slice(600, 1500)
clip.save("highlight.srt")
```

---

### 3. Translate: export text → reimport

```python
mgr = SRTManager.from_file("original.srt")

# Export plain text for a translator
with open("text_for_translation.txt", "w") as f:
    for sub in mgr:
        f.write(f"{sub.index}|{sub.content}\n")

# After translation, reimport content
translations = {}
with open("translated.txt") as f:
    for line in f:
        idx, content = line.strip().split("|", 1)
        translations[int(idx)] = content

translated = mgr.map_content(lambda t: t)  # start from copy
import srt
new_subs = [
    srt.Subtitle(sub.index, sub.start, sub.end, translations.get(sub.index, sub.content))
    for sub in mgr
]
SRTManager(new_subs).save("translated.srt")
```

---

### 4. Merge intro + main + credits

```python
intro   = SRTManager.from_file("intro.srt")
main    = SRTManager.from_file("main.srt")
credits = SRTManager.from_file("credits.srt")

full = intro + main + credits
full.save("full_movie.srt")
```

---

### 5. Split a long file into chapters

Mark chapter boundaries in your SRT with a special subtitle:

```
42
00:22:10,000 --> 00:22:10,500
<chapter>
```

Then:

```python
mgr = SRTManager.from_file("documentary.srt")
chapters = mgr.split("<chapter>")

for i, chapter in enumerate(chapters, start=1):
    if chapter:
        chapter.save(f"chapter_{i:02d}.srt")
        print(f"Chapter {i}: {len(chapter)} subs, {chapter.duration}")
```

---

### 6. Find & fix a mistimed subtitle

```python
mgr = SRTManager.from_file("movie.srt")

# Find which subtitle has the wrong text
results = mgr.find("shoudl")   # typo in content
print(results[0].index)        # e.g. prints 73

# Fix its timing and the typo
fixed = (
    mgr
    .retime(73, start=445.2, end=447.8)
    .replace_content("shoudl", "should")
)
fixed.save("movie_fixed.srt")
```

---

### 7. Analyse subtitles with pandas

```python
mgr = SRTManager.from_file("movie.srt")
df  = mgr.to_dataframe()

# Subtitles longer than 7 seconds (likely need splitting)
print(df[df["duration"] > 7][["index", "duration", "content"]])

# Average subtitle duration
print(df["duration"].mean())

# Total spoken word count
total_words = df["content"].str.split().str.len().sum()
print(f"Total words: {total_words}")
```

---

### 8. Scale subtitles to a re-encoded video

Video was sped up by 5% — scale all subtitle timestamps:

```python
mgr = SRTManager.from_file("original.srt")

original_duration = mgr.duration.total_seconds()
new_duration      = original_duration / 1.05       # 5% faster

mgr.duration = new_duration
mgr.save("rescaled.srt")
```

---

### 9. Diff two versions

```python
v1 = SRTManager.from_file("subtitles_v1.srt")
v2 = SRTManager.from_file("subtitles_v2.srt")

diff = v1.diff(v2)

print(f"Added:   {len(diff['added'])}")
print(f"Removed: {len(diff['removed'])}")

for sub in diff["added"]:
    print(f"  + [{sub.start}] {sub.content}")
for sub in diff["removed"]:
    print(f"  - [{sub.start}] {sub.content}")
```
