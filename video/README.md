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
- `title`, `list`, `stages`, `outro`, `cover_time`: teks dan frame untuk grafik.

Untuk video baru, salin `projects/5-stages-awareness/edit.json` dan tukar masa serta teks.
Masa `in`/`out` boleh didapati dari transcript (contohnya Whisper).
