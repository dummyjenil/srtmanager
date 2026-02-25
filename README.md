# 🎬 SRTManager

**Advanced, expressive, production-safe subtitle manager for `.srt` files.**

`SRTManager` is a high-level abstraction built on top of the `srt` Python library that enforces strict subtitle invariants while providing powerful transformation utilities like shifting, slicing, scaling, merging, gap compression, content mapping, and more.

---

## ✨ Features

* ✅ Automatic sorting & reindexing
* ✅ Overlap detection
* ✅ Timestamp validation (no negative times)
* ✅ Immutable-style transformations
* ✅ Shift subtitles forward/backward
* ✅ Merge subtitle files safely
* ✅ Clip/slice by time range
* ✅ Search by text
* ✅ Split & join subtitle segments
* ✅ Gap compression
* ✅ Duration scaling
* ✅ Functional content transformations

---

## 📦 Installation

```bash
pip install srtmanager
```

Then place `SRTManager` in your project.

---

## 🧠 Core Invariants

Every `SRTManager` instance guarantees:

1. Subtitles are sorted by start time
2. Subtitles are sequentially indexed from `1`
3. No overlapping subtitles
4. All timestamps are ≥ 0

If any invariant is violated:

```python
SRTValidationError
```

is raised.

---

## 🚀 Quick Start

```python
from srtmanager import SRTManager

# Load from file
subs = SRTManager.from_file("input.srt")

# Shift forward by 2 seconds
shifted = subs >> 2

# Search for text
hello_lines = subs["hello"]

# Slice between 10s and 30s
clip = subs[10:30]

# Save result
shifted.save("output.srt")
```

---

# 📚 API Documentation

---

## 🔹 Constructors

### `SRTManager.from_file(path: str)`

Load subtitles from `.srt` file.

```python
subs = SRTManager.from_file("movie.srt")
```

---

### `SRTManager.from_string(raw: str)`

Parse subtitles from raw string.

---

## 🔹 Basic Properties

### `len(manager)`

Returns number of subtitles.

### `manager.start`

Start timestamp of first subtitle.

### `manager.end`

End timestamp of last subtitle.

### `manager.duration`

Total duration (`end - start`).

You can also **scale duration**:

```python
subs.duration = 120  # scale entire timeline to 120 seconds
```

---

## 🔹 Time Shifting

### `shift(seconds: float) -> SRTManager`

```python
new_subs = subs.shift(2.5)
```

### Operator Overloads

```python
subs >> 2   # shift forward 2 seconds
subs << 1   # shift backward 1 second
```

---

## 🔹 Merge

```python
combined = subs1 + subs2
```

* Automatically shifts second file to avoid overlap.
* Maintains invariants.

---

## 🔹 Slice (Time Clipping)

```python
clip = subs.slice(10, 30)
# or
clip = subs[10:30]
```

* Clips subtitles within range
* Adjusts start/end if partially overlapping

---

## 🔹 Find (Search)

```python
results = subs.find("hello")
results = subs.find("HELLO", case_sensitive=True)

# Shortcut
results = subs["hello"]
```

Returns new `SRTManager` containing matches.

---

## 🔹 Split

Split subtitles using delimiter:

```python
parts = subs.split("<line>")
```

Returns list of `SRTManager` instances.

---

## 🔹 Join as Single Subtitle

```python
single = subs.join_as_single()
```

Returns one merged `srt.Subtitle`.

---

## 🔹 Gap Compression

Removes silent gaps between subtitles while preserving durations:

```python
tight = subs.compress_gaps()
```

---

## 🔹 Content Transformation

Functional style mapping:

```python
upper = subs.map_content(lambda text: text.upper())
```

---

## 🔹 Plain Text Export

```python
text = subs.to_plain_text()
```

---

## 🔹 Save

```python
subs.save("output.srt")
```

---

## 🔹 Add Raw Subtitles (Validated)

```python
subs.add_raw(new_subtitles)
```

Re-validates:

* Sorting
* Indexing
* Overlaps

Raises `SRTValidationError` if invalid.

---

# 🛡 Error Handling

### `SRTValidationError`

Raised when:

* Negative timestamps
* End before start
* Overlapping subtitles

Example:

```python
try:
    subs = SRTManager(invalid_subtitles)
except SRTValidationError as e:
    print("Invalid SRT:", e)
```

---

# 🧩 Design Philosophy

This library follows:

* **Immutability-first transformations**
* **Strong invariants**
* **Operator overloading for expressiveness**
* **Functional programming patterns**
* **Production-safe validation**

---

# 🔮 Example Workflow

```python
subs = (
    SRTManager.from_file("raw.srt")
    .shift(1.2)
    .map_content(str.strip)
    .compress_gaps()
)

subs.save("cleaned.srt")
```

---

# 📌 Ideal Use Cases

* Subtitle synchronization
* Post-processing AI-generated subtitles
* Timeline alignment
* Subtitle merging pipelines
* Research projects
* Video automation tools

---

# 🧠 Author Notes

Built for developers who want:

* Clean abstraction
* No silent timeline corruption
* Predictable transformations
* Composable subtitle workflows




Below are **advanced, production-level usage patterns** for your `SRTManager` implementation 

These go beyond basic examples and show how to build real subtitle pipelines.

---

# 🔥 Advanced Usage Examples

---

# 1️⃣ Auto-Sync Two Subtitle Files

### 🎯 Problem

You have:

* `dialogue.srt`
* `translated.srt` (starts earlier)

You want to align them safely and merge.

```python
from srtmanager import SRTManager

dialogue = SRTManager.from_file("dialogue.srt")
translated = SRTManager.from_file("translated.srt")

# Align translated to dialogue start
offset = (dialogue.start - translated.start).total_seconds()
translated_aligned = translated.shift(offset)

# Merge safely (no overlap corruption)
final = dialogue + translated_aligned

final.save("merged.srt")
```

✔ Automatically prevents overlap
✔ Keeps indexes clean
✔ Guarantees invariants

---

# 2️⃣ Normalize AI-Generated Subtitles

### 🎯 Problem

AI subtitles often contain:

* Extra spaces
* Broken casing
* Random gaps

### 🧠 Clean Pipeline

```python
def clean_text(text: str) -> str:
    return " ".join(text.strip().split()).capitalize()

subs = (
    SRTManager.from_file("ai_output.srt")
    .map_content(clean_text)
    .compress_gaps()
)

subs.save("clean_ai_output.srt")
```

✔ Removes weird spacing
✔ Fixes formatting
✔ Eliminates timing gaps

---

# 3️⃣ Clip Scene + Retime to New Duration

### 🎯 Problem

You want only the segment from 60s–120s
Then stretch it to exactly 30 seconds.

```python
clip = SRTManager.from_file("movie.srt")[60:120]

# Scale duration to 30 seconds
clip.duration = 30

clip.save("scene_shortened.srt")
```

✔ Automatically scales proportionally
✔ Keeps relative timing intact

---

# 4️⃣ Subtitle Chunking (Episode Segmentation)

### 🎯 Problem

You use `<line>` as delimiter to mark chapter breaks.

```python
subs = SRTManager.from_file("lecture.srt")

parts = subs.split("<line>")

for i, part in enumerate(parts, 1):
    part.save(f"chapter_{i}.srt")
```

✔ Clean segmentation
✔ Maintains proper indexing

---

# 5️⃣ Build a Search Engine on Subtitles

### 🎯 Problem

Extract all dialogue containing a keyword.

```python
subs = SRTManager.from_file("podcast.srt")

crypto_mentions = subs["blockchain"]

print(crypto_mentions.to_plain_text())
```

✔ Returns only matching subtitles
✔ Keeps original timestamps

---

# 6️⃣ Remove Silence but Keep Flow

### 🎯 Problem

You want subtitles to play continuously without silent gaps.

```python
tight = (
    SRTManager.from_file("documentary.srt")
    .compress_gaps()
)

tight.save("no_silence.srt")
```

Original:

```
00:00:01 → 00:00:03
00:00:10 → 00:00:12
```

Compressed:

```
00:00:01 → 00:00:03
00:00:03 → 00:00:05
```

✔ Keeps duration of each subtitle
✔ Removes dead air

---

# 7️⃣ Subtitle Stitching (Multiple Episodes → Movie Cut)

### 🎯 Problem

Combine multiple SRT files into one continuous timeline.

```python
ep1 = SRTManager.from_file("ep1.srt")
ep2 = SRTManager.from_file("ep2.srt")
ep3 = SRTManager.from_file("ep3.srt")

movie_cut = ep1 + ep2 + ep3

movie_cut.save("full_movie.srt")
```

✔ Automatically offsets later files
✔ No overlap errors

---

# 8️⃣ Build a Subtitle Analytics Tool

### 🎯 Word Frequency Counter

```python
from collections import Counter

subs = SRTManager.from_file("debate.srt")

words = subs.to_plain_text().lower().split()
freq = Counter(words)

print(freq.most_common(20))
```

✔ Works perfectly because `to_plain_text()` strips formatting

---

# 9️⃣ Convert Subtitles to Voice Script

### 🎯 Create Narration Script

```python
subs = SRTManager.from_file("course.srt")

script = subs.join_as_single(sep=" ")

with open("script.txt", "w") as f:
    f.write(script.content)
```

✔ Preserves full timeline span
✔ Merges content cleanly

---

# 🔟 Real Production Pipeline Example

```python
def production_pipeline(path_in: str, path_out: str):
    subs = (
        SRTManager.from_file(path_in)
        .shift(0.5)
        .map_content(lambda t: t.replace("uh", "").strip())
        .compress_gaps()
    )

    subs.save(path_out)


production_pipeline("raw.srt", "final.srt")
```

✔ Sync correction
✔ Filler word removal
✔ Timeline tightening
✔ Safe save

---

# ⚙️ Advanced Pattern: Functional Chaining

Because transformations return new `SRTManager` instances:

```python
final = (
    SRTManager.from_file("input.srt")
    >> 1.2
    .map_content(str.upper)
    .slice(30, 90)
    .compress_gaps()
)
```

This enables:

* Declarative pipelines
* Immutable-style transformations
* Predictable behavior

---

# 🏗 Design Strength Shown in Advanced Use

Your architecture supports:

* Deterministic transformations
* Strong validation
* Clean composition
* Safe timeline arithmetic
* Operator expressiveness

