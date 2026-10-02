# Video pipeline: gaya Ali Abdaal (TikTok / Threads, 9:16)

Tukar rakaman talking-head kepada video pendek dengan:
jump cut, zoom selang-seli, sari kata besar dengan highlight kuning,
kad tajuk, senarai bernombor, label stage dengan progress bar, outro CTA,
audio dibersihkan dan dinormalkan ke -14 LUFS, dan cover image.

## Keperluan
- `ffmpeg` / `ffprobe`
- Python 3 dengan `pip install pillow numpy`

## Cara guna
```bash
python3 video/render.py <rakaman.mov> video/projects/<nama>/edit.json
```
Output akan masuk ke `video/projects/<nama>/out/`: `tiktok.mp4`, `cover.jpg` dan `captions.srt`.

## Format `edit.json`
- `segments`: bahagian rakaman yang disimpan (`in`/`out` dalam saat). Semua bahagian lain dibuang.
  - `zoom`: selang-seli `1.00` / `1.12`, supaya setiap cut rasa macam sudut kamera baru.
  - `text`: sari kata. `|` memisahkan setiap chunk, `*perkataan*` jadi kuning.
    Tag seperti `[list=2]`, `[stage=3]` dan `[outro=1]` akan menukar grafik bermula pada chunk itu.
- `title`, `list`, `stages` (berapa-berapa stage pun boleh), `outro`: teks untuk grafik.
- `cover` (`line1`, `line2`, `tag`) dan `cover_time`: teks dan frame untuk cover.
- `anchor`: kedudukan muka dalam frame (`[x, y]`, 0–1), iaitu titik tengah zoom.
- Tag `[zoom=1.14]` dalam teks: zoom masuk atau keluar di tengah take yang panjang.

Untuk video baru, salin `projects/5-stages-awareness/edit.json` dan tukar masa serta teks.
Masa `in`/`out` boleh didapati dari transcript (contohnya Whisper).

## B-roll / gambar
Tetapkan kad dalam `broll`, kemudian panggil dengan tag `[broll=nama]` dalam teks.
Kad akan kekal sehingga tag `[broll=...]` seterusnya, atau `[broll=none]`.
- `image`: gambar dari folder projek, contohnya `{"type": "image", "src": "assets/buku.jpg", "height": 520, "align": "left", "y": 600}`.
- `card`: emoji besar dengan tajuk, contohnya `{"type": "card", "emoji": "🥼", "title": "Lab coat putih", "sub": "..."}`.
- `compare`: dua pilihan ❌ / ✅, contohnya `{"type": "compare", "left": {"emoji": "👕", "label": "Santai"}, "right": {"emoji": "👔", "label": "Corporate"}}`.
- `lowerthird`: contoh nama dan jawatan, contohnya `{"type": "lowerthird", "label": "CONTOH", "name": "...", "role": "..."}`.
