@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo   RESET DAN RUN ULANG PIPELINE OCR
echo ============================================
echo.

rem === EDIT DI BAWAH INI SESUAI FILE ANDA ===

rem Form INSPEKSI: yang ada tabel STR-001, STR-002, kategori A sampai E
set "PDF_INSPEKSI=FORM FINALL.pdf"

rem Form SKETCHUP: yang ada tabel IfcColumn, IfcBeam, Instance, GlobalId
set "PDF_SKETCHUP=FORM BARUUUUUUUUUUUUUU.pdf"

rem ===========================================

echo PDF Inspeksi : %PDF_INSPEKSI%
echo PDF SketchUp : %PDF_SKETCHUP%
echo.

if not exist "%PDF_INSPEKSI%" (
    echo [ERROR] File tidak ditemukan: %PDF_INSPEKSI%
    echo Ganti PDF_INSPEKSI di dalam file reset_dan_run.bat
    pause
    exit /b 1
)

if not exist "%PDF_SKETCHUP%" (
    echo [ERROR] File tidak ditemukan: %PDF_SKETCHUP%
    echo Ganti PDF_SKETCHUP di dalam file reset_dan_run.bat
    pause
    exit /b 1
)

echo [1] Hapus cache gambar PDF lama...
if exist pdf_pages           rmdir /s /q pdf_pages
if exist pdf_pages_sketchup  rmdir /s /q pdf_pages_sketchup
echo     Done.

echo.
echo [2] Reset database SQLite...
python clear_db.py

echo.
echo [3] OCR form inspeksi - ekstrak STR tags dan kategori A-E...
python "run_ocr_json copy.py" --pdf "%PDF_INSPEKSI%"

echo.
echo [4] Parse form SketchUp IFC + merge kategori dari step 3...
python parse_sketchup_ifc.py --pdf "%PDF_SKETCHUP%"

echo.
echo ============================================
echo   SELESAI!
echo   - hasil_inspeksi.json diupdate dari: %PDF_INSPEKSI%
echo   - hasil_sketchup_ifc.json diupdate dari: %PDF_SKETCHUP%
echo.
echo   Selanjutnya di SketchUp Ruby Console:
echo   load "C:/Users/dayinta agustina/Downloads/Documents/MAGANG PETROKIMIA GRESIK/OCRRRRR BARUUUUUUUUU/update_colors_from_ocr.rb"
echo ============================================
pause
