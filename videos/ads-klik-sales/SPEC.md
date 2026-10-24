# SPEC — "Kenapa ads banyak klik tapi sales slow?"

GOAL:    Pemilik bisnes faham: masalah bukan ads, tapi apa yang jadi LEPAS orang klik — dan rasa nak follow / komen.
OUTPUT:  HyperFrames, 1080 x 1920 (9:16 Reels/TikTok), 30 fps
TIME:    64.5 s x 30 = 1935 frames. Voiceover = jam (ElevenLabs, Aisyah – Expressive Conversational, eleven_v4).

STORY:   Perjalanan Kak Ani + kaunter "bakal pembeli" yang jatuh setiap kali ada bocor.
         1,000 klik → 400 (orang salah) → 220 (page lambat) → 90 (page tak sama dgn ad, tiada harga/review)
         → 8 (reply WhatsApp lambat). Angka ilustrasi, ditanda "*angka contoh".

LOOK:    Sticker / komik flat.
         ground home #FFD23F (kuning), dunia lain: teal #2EC4B6 (Kak Ani), salmon #FFB4A2 (page), mint #B8F2E6 (chat), merah #F2542D (twist)
         ink #161412 — semua outline 8 px, bayang keras 10 px 10 px 0 ink, tiada blur/glow
         accent rugi #F2542D (hanya angka jatuh, lubang, harga ???); accent baiki #1FA45B (hanya tampalan)
         display: Archivo Black; body: Poppins 800/600
         teks dibaca ≥ 28 px; semua perkataan dalam band 168–1150 px; caption 1190–1330 px
OBJECTS: corong putih (mulut elips, spout), orang = bulatan berwarna dgn outline;
         Kak Ani: muka #F3C9A0, tudung ungu #8E44AD; telefon: badan ink radius 56, skrin putih;
         chat card putih dgn header kedai; jam dinding; tampalan = pita hijau dgn label.
MOTION:  masuk expo.out / back.out(1.6) untuk sticker; keluar power3.in 40–50% lebih pendek;
         colour flood power2.inOut 0.45 s; whip 0.25 s; label tiba tepat pada perkataan VO.
SHOTS:   S1 0–6.75 hook 1,000 → 8 · S2 6.75–14.5 corong + bocor #1 · S3 14.5–23.58 Kak Ani + loading 8s
         S4 23.58–31.75 page ≠ ad, RM ???, 0 review · S5 31.75–39.65 chat, +3 JAM, beli kedai lain
         S6 39.65–51.55 "BUKAN ADS" → "LEPAS KLIK" → tampal 4 bocor · S7 51.55–64.5 FOLLOW/LIKE/SHARE/KOMEN + soalan
BANNED:  dark void, glow, gradient ungu/biru, cream paper + serif, semua fade+slide-up, 3 kad sebaris,
         logo di penjuru, tajuk bergerak selepas mendarat, emoji sebagai ikon
QA:      0.0 (thumbnail ada 1,000), 4.5, 10.9, 20.0, 27.8, 34.6, 41.8, 49.9, 60.0
