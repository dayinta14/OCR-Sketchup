# -*- coding: utf-8 -*-
"""
run_ocr_json.py
===============
Otomatis ekstrak Tag Number + Kategori dari Form Inspeksi Struktur.
Strategi: EasyOCR full-page untuk deteksi tag + koordinat Y baris,
lalu cell-crop kolom Kat. per baris menggunakan Y yang akurat.

Jalankan:
    python run_ocr_json.py
    python run_ocr_json.py --debug
    python run_ocr_json.py --image pdf_pages/page_01.png
"""

import os, re, json, sys, argparse
import cv2
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Konfigurasi
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_PDF    = "FORM FINALL.pdf"
DEFAULT_IMGDIR = "pdf_pages"
OUTPUT_JSON    = "hasil_inspeksi.json"
DEFAULT_DPI   = 200   # 300 = OOM, 200 cukup akurat
DEFAULT_SCALE = 1     # jangan 2x, hemat RAM
VALID_CAT      = set("ABCDE")
PRIORITY       = {'A': 'HIGH', 'B': 'HIGH', 'C': 'MEDIUM', 'D': 'LOW', 'E': 'LOW'}
TAG_RE         = re.compile(r'\bSTR[-\s]?0*(\d{1,3})\b', re.IGNORECASE)

# Koreksi noise OCR untuk 1 karakter
CAT_FIX = {
    'O': 'D', '0': 'D', 'Q': 'D',    # D sering terbaca O/0/Q
    '9': 'C', 'G': 'C', '6': 'C',    # C sering terbaca 9/G/6
    'P': 'D',                          # D italic mirip P
}

# Koreksi multi-karakter (noise OCR untuk huruf italic)
CAT_FIX_MULTI = {
    'IC': 'C', 'LC': 'C', 'lc': 'C', '1C': 'C',
    'IO': 'D', 'lo': 'D',
}

# ─────────────────────────────────────────────────────────────────────────────
# Render PDF
# ─────────────────────────────────────────────────────────────────────────────
def pdf_to_images(pdf_path, out_dir, dpi=300):
    try:
        import fitz
    except ImportError:
        print("[WARN] PyMuPDF tidak ada."); return []
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, page in enumerate(fitz.open(pdf_path)):
        p = os.path.join(out_dir, "page_{:02d}.png".format(i + 1))
        if not os.path.exists(p):
            page.get_pixmap(dpi=dpi).save(p)
        paths.append(p)
    print("  {} halaman (DPI={})".format(len(paths), dpi))
    return paths

# ─────────────────────────────────────────────────────────────────────────────
# EasyOCR singleton
# ─────────────────────────────────────────────────────────────────────────────
_reader = None
def get_reader():
    global _reader
    if _reader is None:
        import easyocr
        print("  Init EasyOCR...")
        _reader = easyocr.Reader(['en', 'id'], gpu=False, verbose=False)
    return _reader

# ─────────────────────────────────────────────────────────────────────────────
# OCR full page
# ─────────────────────────────────────────────────────────────────────────────
def ocr_full(img_path, scale=2):
    img  = cv2.imread(img_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    big  = cv2.resize(gray, (w*scale, h*scale), interpolation=cv2.INTER_CUBIC)
    kern = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
    sharp = cv2.filter2D(big, -1, kern)
    raw   = get_reader().readtext(sharp, detail=1, paragraph=False)
    blocks = []
    for (bbox, text, conf) in raw:
        xs = [p[0]/scale for p in bbox]; ys = [p[1]/scale for p in bbox]
        x1,y1,x2,y2 = min(xs),min(ys),max(xs),max(ys)
        blocks.append({
            'text':text.strip(),'conf':float(conf),
            'x1':x1,'y1':y1,'x2':x2,'y2':y2,
            'cx':(x1+x2)/2,'cy':(y1+y2)/2,'h':y2-y1,
        })
    print("  Full-page OCR: {} blok".format(len(blocks)))
    return blocks, img

# ─────────────────────────────────────────────────────────────────────────────
# Normalisasi kategori
# ─────────────────────────────────────────────────────────────────────────────
def norm_cat(text):
    if not text: return None
    t = text.strip().upper()
    if t in VALID_CAT: return t
    if len(t) == 1:
        fixed = CAT_FIX.get(t)
        if fixed and fixed in VALID_CAT: return fixed
    # Cek koreksi multi-karakter (noise italic)
    if len(t) == 2:
        fixed = CAT_FIX_MULTI.get(t) or CAT_FIX_MULTI.get(text.strip())
        if fixed and fixed in VALID_CAT: return fixed
    return None

def parse_tag(text):
    m = TAG_RE.search(text)
    return "STR-{:03d}".format(int(m.group(1))) if m else None

# ─────────────────────────────────────────────────────────────────────────────
# Deteksi header tabel
# ─────────────────────────────────────────────────────────────────────────────
def detect_header(blocks):
    """
    Kembalikan:
    - y_header: koordinat Y baris header tabel ("Tag Number")
    - x_kat: koordinat X tengah kolom Kat. dari header
    """
    HEADER_KW = ['tag number', 'deskripsi elemen']
    KAT_KW    = ['kat.', '(a-e)']

    y_header = None
    x_kat    = None

    for b in sorted(blocks, key=lambda b: b['cy']):
        t = b['text'].lower().strip()
        if y_header is None and any(k in t for k in HEADER_KW):
            y_header = b['cy']
        # Kolom Kat. header: blok PENDEK (bukan kalimat legenda) di kanan dokumen
        if x_kat is None and any(k in t for k in KAT_KW) and b['cx'] > 1000:
            if len(b['text'].strip()) <= 8:   # "Kat." atau "(A-E)" pendek
                x_kat = b['cx']
        if y_header and x_kat:
            break

    # Fallback y_header
    if y_header is None:
        for b in sorted(blocks, key=lambda b: b['cy']):
            if 'tabel inspeksi' in b['text'].lower():
                y_header = b['cy']; break

    return y_header, x_kat

# ─────────────────────────────────────────────────────────────────────────────
# OCR satu cell: crop area [x1..x2, y1..y2] dari gambar, perbesar, OCR
# ─────────────────────────────────────────────────────────────────────────────
def ocr_cell_area(img_bgr, x1, y1, x2, y2, scale=6, debug_tag=None):
    H, W = img_bgr.shape[:2]
    cx1 = max(0, int(x1)); cy1 = max(0, int(y1))
    cx2 = min(W, int(x2)); cy2 = min(H, int(y2))
    crop = img_bgr[cy1:cy2, cx1:cx2]
    if crop.size == 0: return None, 0.0

    big   = cv2.resize(crop, (crop.shape[1]*scale, crop.shape[0]*scale), cv2.INTER_CUBIC)
    gray  = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)

    # Siapkan beberapa variasi preprocessing
    _, th_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th_inv     = cv2.bitwise_not(th_otsu)
    kernel     = np.ones((2, 2), np.uint8)
    th_dilate  = cv2.dilate(th_otsu, kernel, iterations=1)

    candidates = [th_otsu, th_inv, th_dilate, gray]
    if debug_tag:
        cv2.imwrite("debug_crop_{}.png".format(debug_tag), th_otsu)

    reader    = get_reader()
    best_text = None
    best_conf = 0.0

    # Coba berbagai scale dan preprocessing
    for cell_scale in [6, 4, 8]:
        for variant in candidates:
            if cell_scale != scale:
                h_, w_ = variant.shape[:2]
                variant = cv2.resize(variant, (w_*cell_scale//scale, h_*cell_scale//scale),
                                     cv2.INTER_CUBIC) if cell_scale != scale else variant
            raw = reader.readtext(variant, detail=1, paragraph=False)
            for (_, text, conf) in raw:
                t = text.strip().upper()
                # Prioritaskan: 1 huruf kategori valid (terima conf rendah sekalipun)
                if len(t) == 1 and t in VALID_CAT and conf >= 0.05:
                    if conf > best_conf or best_text not in VALID_CAT:
                        best_conf = conf
                        best_text = t
                # Fallback: ambil teks apapun dengan conf lebih tinggi
                elif best_text not in VALID_CAT and conf > 0.1:
                    best_conf = conf
                    best_text = text.strip()

        if best_text is not None:
            break  # Sudah ada hasil, hentikan iterasi scale

    return best_text, best_conf


# ─────────────────────────────────────────────────────────────────────────────
# Parsing utama
# ─────────────────────────────────────────────────────────────────────────────
def parse(blocks, img_bgr, debug=False):
    y_header, x_kat = detect_header(blocks)
    main_img_w = img_bgr.shape[1] if img_bgr is not None else None

    print("\n  Header tabel (y)    : {:.0f}".format(y_header or 0))
    # Fallback x_kat: estimasi dari lebar gambar jika tidak terdeteksi
    if x_kat is None and main_img_w is not None:
        x_kat = main_img_w * 0.735  # posisi relatif kolom Kat. ~73.5% lebar gambar
        print("  Kolom Kat. (x)      : {:.0f} [estimasi dari lebar gambar]".format(x_kat))
    else:
        print("  Kolom Kat. (x)      : {:.0f}".format(x_kat or 0))

    if not y_header:
        print("[WARN] Header tabel tidak terdeteksi, proses semua blok.")
        y_header = 0

    # ── Ekstrak tag blocks di bawah header ───────────────────────────────────
    data_blks = [b for b in blocks if b['cy'] > y_header + 5]
    tag_blocks = []
    for b in data_blks:
        tag = parse_tag(b['text'])
        if tag:
            b = dict(b); b['tag'] = tag
            tag_blocks.append(b)

    # Urutkan tag dari atas ke bawah
    tag_blocks.sort(key=lambda x: x['cy'])

    # Deduplikasi: ambil 1 blok per tag (y paling atas)
    seen_tags = {}
    for b in tag_blocks:
        if b['tag'] not in seen_tags:
            seen_tags[b['tag']] = b
    tag_blocks = sorted(seen_tags.values(), key=lambda x: x['cy'])

    print("  Tag unik ditemukan  : {}".format(len(tag_blocks)))

    # Estimasi tinggi baris
    avg_h = float(np.median([b['h'] for b in tag_blocks])) if tag_blocks else 22.0
    print("  Tinggi baris (median): {:.1f} px".format(avg_h))

    # ── Cari kategori dari full-page OCR (spasial) ───────────────────────────
    cat_blks = []
    for b in data_blks:
        cat = norm_cat(b['text'])
        # Wajib: teks pendek (1-2 karakter) DAN confidence cukup tinggi
        # conf < 0.15 kemungkinan besar noise OCR, diabaikan → fallback ke cell-crop
        if cat and len(b['text'].strip()) <= 2 and b['conf'] >= 0.15:
            b = dict(b); b['cat'] = cat
            cat_blks.append(b)


    print("  Cat spasial         : {}".format(len(cat_blks)))

    row_tol  = avg_h * 1.6
    result   = {}
    used_cat = set()

    # Lebar zona kolom Kat. untuk cell-crop
    kat_w = 55  # ±55px dari center x_kat

    for tb in tag_blocks:
        tag   = tb['tag']
        cy_tb = tb['cy']

        # ── Strategi 1: spasial (dari full-page OCR) ─────────────────────────
        best = None; best_score = float('inf'); best_idx = None
        for i, cb in enumerate(cat_blks):
            if i in used_cat: continue
            dy = abs(cb['cy'] - cy_tb)
            if dy > row_tol: continue
            dx = cb['cx'] - tb['cx']
            if dx < -10: continue
            s = dy*3 + (abs(cb['cx']-x_kat)*0.5 if x_kat else dx*0.1)
            if s < best_score:
                best_score = s; best = cb['cat']; best_idx = i

        if best is not None and best_idx is not None:
            used_cat.add(best_idx)
            result[tag] = best
            print("  {} -> {} [spasial, score={:.1f}]".format(tag, best, best_score))
            continue

        # ── Strategi 2: cell-crop menggunakan Y dari tag block ────────────────
        if x_kat is not None and img_bgr is not None:
            pad_y  = avg_h * 0.55
            cell_x1 = x_kat - kat_w
            cell_x2 = x_kat + kat_w
            cell_y1 = cy_tb - pad_y
            cell_y2 = cy_tb + pad_y
            dbg_id  = tag if debug else None
            raw_text, conf = ocr_cell_area(img_bgr, cell_x1, cell_y1,
                                            cell_x2, cell_y2, debug_tag=dbg_id)
            cat_crop = norm_cat(raw_text)
            if cat_crop:
                result[tag] = cat_crop
                print("  {} -> {} [cell-crop, conf={:.2f}, raw='{}']".format(
                    tag, cat_crop, conf, raw_text))
                continue

        result[tag] = None
        print("  {} -> ? [tidak terdeteksi]".format(tag))

    return result

# ─────────────────────────────────────────────────────────────────────────────
# Inline fallback
# ─────────────────────────────────────────────────────────────────────────────
INLINE_RE = re.compile(
    r'(STR[-\s]?0*\d{1,3})\s*[\|\s,;\.]{0,5}\s*([ABCDE])\b', re.IGNORECASE)

def inline_fallback(blocks, tag_cat):
    for b in blocks:
        m = INLINE_RE.search(b['text'])
        if m:
            nm = re.search(r'(\d+)', m.group(1))
            if nm:
                tag = "STR-{:03d}".format(int(nm.group(1)))
                cat = m.group(2).upper()
                if tag not in tag_cat or tag_cat[tag] is None:
                    tag_cat[tag] = cat
                    print("  [inline] {} -> {}".format(tag, cat))

# ─────────────────────────────────────────────────────────────────────────────
# Build JSON
# ─────────────────────────────────────────────────────────────────────────────
def build_json(tag_cat):
    inspections = []
    count = {k: 0 for k in list(VALID_CAT) + ['UNKNOWN']}
    for tag in sorted(tag_cat):
        cat = (tag_cat[tag] or "").upper()
        if cat not in VALID_CAT:
            cat = "UNKNOWN"; priority = "UNKNOWN"; count['UNKNOWN'] += 1
        else:
            priority = PRIORITY[cat]; count[cat] += 1
        inspections.append({"tag_number": tag, "category": cat, "priority": priority})
    critical = [{"tag_number":x["tag_number"],"category":x["category"]}
                for x in inspections if x["priority"]=="HIGH"]
    return {
        "inspections": inspections,
        "summary": {
            "total_data": len(inspections),
            "jumlah_A": count['A'], "jumlah_B": count['B'],
            "jumlah_C": count['C'], "jumlah_D": count['D'],
            "jumlah_E": count['E'], "most_critical": critical,
        }
    }

def print_raw(blocks):
    print("\n" + "-"*72 + "\n  RAW OCR OUTPUT\n" + "-"*72)
    for b in sorted(blocks, key=lambda b: (round(b['cy']/15)*15, b['cx'])):
        print("  y={:5.0f} x={:5.0f}  conf={:.2f}  \"{}\"".format(
            b['cy'],b['cx'],b['conf'],b['text']))

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf",   default=DEFAULT_PDF)
    ap.add_argument("--image", default=None)
    ap.add_argument("--dpi",   default=DEFAULT_DPI, type=int)
    ap.add_argument("--scale", default=DEFAULT_SCALE, type=int, help="Scale gambar sebelum OCR")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--no-preprocess", action="store_true")
    args = ap.parse_args()

    print("="*72)
    print("  OCR OTOMATIS  --  FORM INSPEKSI STRUKTUR  ->  JSON")
    print("="*72)

    # Kumpulkan gambar
    image_paths = []
    if args.image:
        if not os.path.exists(args.image):
            print("[ERROR] {}".format(args.image)); sys.exit(1)
        image_paths = [args.image]
    elif os.path.exists(args.pdf):
        print("\n[1] Render PDF (DPI={})...".format(args.dpi))
        # Hapus cache lama agar tidak pakai gambar dari PDF berbeda
        cache_path = os.path.join(DEFAULT_IMGDIR, "page_01.png")
        if os.path.exists(cache_path):
            os.remove(cache_path)
            print("  Cache lama dihapus, render ulang...")
        image_paths = pdf_to_images(args.pdf, DEFAULT_IMGDIR, args.dpi)
    else:
        if os.path.isdir(DEFAULT_IMGDIR):
            image_paths = sorted([
                os.path.join(DEFAULT_IMGDIR, f)
                for f in os.listdir(DEFAULT_IMGDIR)
                if f.lower().endswith(('.png','.jpg','.jpeg')) and "_pre" not in f
            ])
            print("[1] Pakai {} gambar dari {}.".format(len(image_paths), DEFAULT_IMGDIR))
        else:
            print("[ERROR] Tidak ada PDF/gambar."); sys.exit(1)

    if not image_paths:
        print("[ERROR] Tidak ada gambar."); sys.exit(1)

    all_blocks = []
    all_imgs   = {}
    for img_path in image_paths:
        print("\n[2] OCR full-page: {}".format(os.path.basename(img_path)))
        scale  = 1 if args.no_preprocess else args.scale
        blocks, img_bgr = ocr_full(img_path, scale=scale)
        all_blocks.extend(blocks)
        all_imgs[img_path] = img_bgr

    if not all_blocks:
        print("[ERROR] Tidak ada teks."); sys.exit(1)

    if args.debug:
        print_raw(all_blocks)

    main_img = all_imgs.get(image_paths[0])

    print("\n[3] Parsing spasial + cell-crop...")
    tag_cat = parse(all_blocks, main_img, debug=args.debug)

    print("\n[4] Inline fallback...")
    inline_fallback(all_blocks, tag_cat)

    missing = [t for t, c in tag_cat.items() if c is None]
    if missing:
        print("\n[WARN] Masih UNKNOWN: {}".format(missing))

    print("\n[5] Menyusun JSON...")
    output = build_json(tag_cat)
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n" + "="*72)
    print("  HASIL EKSTRAKSI:")
    print("="*72)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    n_ok  = sum(1 for x in output['inspections'] if x['category'] != 'UNKNOWN')
    n_tot = output['summary']['total_data']
    print("\n  Akurasi : {}/{} tag berhasil ({:.0f}%)".format(
        n_ok, n_tot, 100*n_ok/n_tot if n_tot else 0))
    print("[OK] Tersimpan: {}".format(OUTPUT_JSON))
    print("="*72)

if __name__ == "__main__":
    main()
