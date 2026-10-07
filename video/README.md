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

## Video tanpa muka (voiceover ElevenLabs)

`faceless.py` menghasilkan video gaya Ali Abdaal tanpa rakaman kamera. Setiap frame dilukis:
latar kertas dan grid, kad babak di tengah (tajuk, animasi kertas, badge, langkah, CTA),
label stage dengan progress bar, sari kata perkataan demi perkataan, dan SFX. Warnanya ikut brand Mindsel.

```bash
python3 video/faceless.py video/projects/<nama>/edit.json            # render penuh
python3 video/faceless.py video/projects/<nama>/edit.json --stills   # pratonton pantas (frame dalam "previews")
```

Projek: `mindsel-fikiran-penat`, `mindsel-launch`.

### Langkah
1. Jana suara di ElevenLabs, kemudian simpan sebagai `assets/voice.mp3`.
2. Transcribe suara (ElevenLabs Scribe) dan simpan masa perkataan sebagai `assets/words.json` (`{"words": [{"text", "start", "end"}]}`).
3. Tulis `edit.json`:
   - `script`: teks yang dipaparkan. `|` memisahkan chunk, dan `*perkataan*` diberi highlight oren.
     Chunk dipadankan dengan `words.json`, jadi teks paparan boleh berbeza sedikit dari yang disebut
     (contohnya "mindsel dot my" dipaparkan sebagai "mindsel.my").
   - Tag dalam skrip:
     - `[scene=key]` tukar kad babak
     - `[stage=n]` papar label stage (`0` sembunyikan)
     - `[reveal=n]` papar item badge atau langkah satu per satu
     - `[sfx=nama]` mainkan bunyi
     Chunk kosong di hujung (`|[scene=end]`) menjadi kad penutup selepas suara tamat.
   - `scenes`: jenis kad yang ada ialah `hero`, `strike`, `anim` (klip Paper Crumple green-screen, dibuang latarnya secara automatik), `card`, `badges`, `steps`, `cta` dan `end`.
   - `sfx`, `sfx_gain`, `auto_sfx` (whoosh setiap kali babak bertukar, pop setiap kali reveal), dan `bed` (bunyi latar).

### Aset
Aset dari pek **AA Editing Assets** (font Nitti, SFX, Grid BG, Paper Folds, Masking Tape, Paper Crumple)
dimuat turun dari folder Google Drive "Ali abdaal sttle" ke `video/assets/aa/`, dengan struktur folder yang sama.
Folder ini tidak di-commit. Kalau aset tiada, renderer guna grid lukisan sendiri dan emoji sebagai ganti.
