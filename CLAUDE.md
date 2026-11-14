# CLAUDE.md — eval-platform (P5)

## KONTEKS
Repo ini bagian dari portofolio AI Quality Engineer milik Jordy (sementara di akun GitHub `Jordy1406`; target org
`finassist-quality`). Sistem target bernama **FinAssist ID** (repo `finassist-app`): chatbot RAG atas dokumen publik
pasar modal (Bahasa Indonesia) + agent dengan tools `get_quote`, `get_portfolio`, `place_order` ke MOCK broker.

- **Repo ini:** P5 — Quality Platform.
- **Tujuan:** membuat semua tes berjalan otomatis, terukur, terlihat.
- **MINIMUM:** eval subset di setiap PR + full terjadwal; quality gate (PR gagal jika skor turun > ambang); riwayat run
  di SQLite.
- **STRETCH:** dashboard Streamlit (tren skor, biaya, latensi), tracing Langfuse, cache respons, video demo 3 menit.
- **Selesai jika:** demo — perubahan yang menurunkan kualitas otomatis diblokir (screenshot di README).
- **Keputusan Jordy (2026-11-14):** GitHub Actions terkunci billing → platform dijalankan **lokal** (perintah
  `evalplat check` meniru PR check + git hook pre-push); workflow Actions tetap ditulis untuk nanti. Model di CI:
  Ollama. Dataset subset: 20 kasus draf Claude, **wajib direview & disetujui Jordy** sebelum dianggap final.

## STACK
Python 3.12, pytest, httpx, PyYAML, SQLite (stdlib). Memakai `../llm-eval-harness` (format kasus + metrik) dan
`../finassist-app` (target). Ollama lokal.

## CARA RUN
Lihat README.

## ATURAN
- Jelaskan rencana dulu, tunggu persetujuan, baru tulis kode.
- 1 sesi = 1 fitur = 1 commit/PR kecil. Pesan commit format Conventional Commits.
- Kerjakan MINIMUM dulu; STRETCH hanya jika diminta.
- Jangan tambah dependency tanpa alasan; catat di README jika menambah.
- Data hanya publik atau fiktif. Rahasia hanya di `.env` (dan `.env` di `.gitignore`).
- Desain eval (dataset, rubrik, ambang gate) diputuskan Jordy; Claude bantu implementasi dan menjelaskan.
- Setelah tiap fitur: jalankan test, laporkan hasil, usulkan pesan commit.
