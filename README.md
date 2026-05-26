## Gambaran Umum Workflow
Proyek ini punya **3 tahap utama** yang saling terhubung:

1. **OCR** form inspeksi PDF → `hasil_inspeksi.json`
2. **Parse** PDF SketchUp IFC → `hasil_sketchup_ifc.json` (otomatis merge dengan hasil OCR)
3. **Ruby script** di SketchUp → warnai elemen 3D sesuai kategori

## Persiapan Awal (Install Dependensi)
Jalankan di terminal/cmd:
pip install easyocr opencv-python pymupdf numpy

## Tahap 1 — OCR Form Inspeksi
Script ini membaca `FORM FINALL.pdf` (form inspeksi struktur), mendeteksi Tag Number (`STR-001`, `STR-002`, dst.) beserta kategorinya (A/B/C/D/E).
python "run_ocr_json copy.py"
# Jika ingin proses hanya 1 gambar spesifik
python "run_ocr_json copy.py" --image pdf_pages/page_01.png
# Ganti DPI render PDF (default 200)
python "run_ocr_json copy.py" --dpi 300
**Hasil:** File `hasil_inspeksi.json` berisi array semua tag + kategori + prioritas.

## Tahap 2 — Parse Data SketchUp IFC
Script ini membaca `FORM BARUUUUUUUUUUUUUU.pdf` (form SketchUp), mengekstrak GlobalID, IFC Type (`IfcColumn`, `IfcBeam`, dst.), nomor instance, lalu otomatis **merge** dengan `hasil_inspeksi.json` dari tahap 1.
python parse_sketchup_ifc.py
python parse_sketchup_ifc.py --debug
**Hasil:** File `hasil_sketchup_ifc.json` berisi data elemen lengkap + kolom `keterangan` (kategori A-E yang diambil dari hasil OCR).

## Tahap 3 — Warnai Elemen di SketchUp
Setelah 2 file JSON di atas siap, masuk ke SketchUp:
1. Buka model SketchUp kamu
2. Buka **Ruby Console**: menu `Extensions → Ruby Console` (atau `Window → Ruby Console`)
3. Jalankan script (ganti path sesuai lokasi repo kamu):
load "C:/Users/kamu/Documents/OCR-Sketchup/update_colors_from_ocr.rb"
4. Script akan membaca `hasil_sketchup_ifc.json` secara otomatis (dari folder yang sama dengan file `.rb`)
5. Jika warna belum terlihat: aktifkan `View → Face Style → Shaded with Textures`


**Mapping warna:**
| Kategori | Warna | Prioritas |
|---|---|---|
| A | Hijau | Baik |
| B | Biru | Perhatian |
| C | Kuning | Sedang |
| D | Oranye | Buruk |
| E | Merah | Kritis |

## Shortcut: Jalankan Semua Sekaligus (Windows)
Kalau di Windows, tinggal double-click file `reset_dan_run.bat` — ini akan hapus cache gambar lama dan jalankan ulang OCR + parse secara otomatis.
