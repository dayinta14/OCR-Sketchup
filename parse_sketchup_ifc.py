# -*- coding: utf-8 -*-
"""
parse_sketchup_ifc.py
======================
Baca tabel IFC dari form SketchUp langsung dari teks PDF (bukan OCR).
Lebih akurat karena tidak ada noise OCR.
"""

import os, re, json, sys, argparse

DEFAULT_PDF = "FORM BARUUUUUUUUUUUUUU.pdf"
OUTPUT_JSON = "hasil_sketchup_ifc.json"

IFC_RE = re.compile(
    r'\b(Ifc(?:Column|Member|Beam|Wall|Slab|Plate|Footing|Pile|Stair|Ramp'
    r'|Roof|Window|Door|Space|Building|Site|Floor|CurtainWall|Railing'
    r'|Pipe|Duct|Frame|Grid|Opening|Proxy))\b', re.IGNORECASE)

GLOBALID_RE = re.compile(r'[0-9A-Za-z_$]{20,22}')
INSTANCE_RE = re.compile(r'\b(\d{2,5})\b')
KAT_RE      = re.compile(r'\b([ABCDE])\b')

SKIP_KW = ['dibuat', 'inspektor', 'supervisor', 'approved', 'form no',
           'tanggal', 'halaman', 'nama', 'rev:', 'catatan', 'mengetahui',
           'keterangan', 'ket.', 'tag number', 'instance', 'definition',
           'deskripsi', 'no.', 'kat.']

# ─────────────────────────────────────────────────────────────────────────────
def extract_words(pdf_path):
    try:
        import fitz
    except ImportError:
        print("[ERROR] PyMuPDF tidak ada. Install: pip install pymupdf"); sys.exit(1)
    words = []
    doc = fitz.open(pdf_path)
    for page_num, page in enumerate(doc):
        for w in page.get_text("words"):
            x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
            text = text.strip()
            if not text:
                continue
            words.append({
                'text': text,
                'cx': (x0 + x1) / 2,
                'cy': (y0 + y1) / 2,
                'x1': x0, 'y1': y0, 'x2': x1, 'y2': y1,
                'page': page_num,
            })
    print("  Total kata dari PDF: {}".format(len(words)))
    return words

# ─────────────────────────────────────────────────────────────────────────────
def group_rows(words, tol=4):
    if not words:
        return []
    sw = sorted(words, key=lambda w: (w['page'], w['cy']))
    rows, cur = [], [sw[0]]
    for w in sw[1:]:
        if w['page'] == cur[-1]['page'] and abs(w['cy'] - cur[-1]['cy']) <= tol:
            cur.append(w)
        else:
            rows.append(sorted(cur, key=lambda w: w['cx']))
            cur = [w]
    if cur:
        rows.append(sorted(cur, key=lambda w: w['cx']))
    return rows

# ─────────────────────────────────────────────────────────────────────────────
def find_col_positions(rows):
    """Cari baris header dan posisi X tiap kolom."""
    header_kw = {
        'no'        : ['no', 'no.'],
        'tag'       : ['tag'],
        'instance'  : ['instance', 'instansi'],
        'definition': ['definition', 'definisi', 'globalid'],
        'deskripsi' : ['deskripsi', 'description', 'elemen'],
        'keterangan': ['keterangan', 'kat.', 'kat', 'kategori'],
    }
    for i, row in enumerate(rows):
        row_lower = [w['text'].lower().rstrip('.') for w in row]
        found = {}
        for col, kws in header_kw.items():
            for j, t in enumerate(row_lower):
                if t in kws:
                    found[col] = row[j]['cx']
                    break
        if len(found) >= 3:
            print("  Header di baris {}: {}".format(i, list(found.keys())))
            return i, found
    return None, {}

# ─────────────────────────────────────────────────────────────────────────────
def closest_col(cx, col_x):
    if not col_x:
        return None
    return min(col_x, key=lambda c: abs(col_x[c] - cx))

# ─────────────────────────────────────────────────────────────────────────────
def parse_rows(rows, header_idx, col_x):
    records = []
    for row in rows[header_idx + 1:]:
        row_text = ' '.join(w['text'] for w in row)

        # Skip baris noise/footer
        if any(sk in row_text.lower() for sk in SKIP_KW):
            continue

        # Harus ada GlobalId atau IFC tag
        has_gid = bool(GLOBALID_RE.search(row_text))
        has_ifc = bool(IFC_RE.search(row_text))
        if not has_gid and not has_ifc:
            continue

        # Kelompokkan kata ke kolom
        buckets = {c: [] for c in col_x}
        for w in row:
            col = closest_col(w['cx'], col_x)
            if col:
                buckets[col].append(w['text'])

        no_txt   = ' '.join(buckets.get('no', []))
        tag_txt  = ' '.join(buckets.get('tag', []))
        inst_txt = ' '.join(buckets.get('instance', []))
        defn_txt = ' '.join(buckets.get('definition', []))
        desc_txt = ' '.join(buckets.get('deskripsi', []))
        kat_txt  = ' '.join(buckets.get('keterangan', []))

        # Ekstrak nilai
        no_m  = re.search(r'^\s*(\d{1,3})\s*$', no_txt)
        no_v  = int(no_m.group(1)) if no_m else (len(records) + 1)

        ifc_m = IFC_RE.search(tag_txt) or IFC_RE.search(row_text)
        tag_v = ifc_m.group(1) if ifc_m else ''

        gid_m = GLOBALID_RE.search(defn_txt)
        if not gid_m:
            gid_m = GLOBALID_RE.search(row_text)
        defn_v = gid_m.group(0) if gid_m else ''

        inst_m = INSTANCE_RE.search(inst_txt)
        inst_v = inst_m.group(1) if inst_m else ''

        kat_m = KAT_RE.search(kat_txt)
        kat_v = kat_m.group(1).upper() if kat_m else ''

        if not defn_v and not tag_v:
            continue

        records.append({
            'no'        : no_v,
            'tag'       : tag_v,
            'instance'  : inst_v,
            'definition': defn_v,
            'deskripsi' : desc_txt.strip(),
            'keterangan': kat_v,
        })

    return records

# ─────────────────────────────────────────────────────────────────────────────
def merge_keterangan(output, inspeksi_json="hasil_inspeksi.json"):
    if not os.path.exists(inspeksi_json):
        print("[WARN] {} tidak ditemukan.".format(inspeksi_json))
        return output
    with open(inspeksi_json, encoding='utf-8') as f:
        data = json.load(f)
    cat_map = {x['tag_number']: x.get('category', '') for x in data.get('inspections', [])}
    print("  Kategori dari OCR inspeksi: {}".format(cat_map))
    # Map berdasarkan urutan no (STR-001 -> no=1, dst)
    for el in output.get('elements', []):
        str_id = 'STR-{:03d}'.format(el.get('no', 0))
        if not el.get('keterangan') and str_id in cat_map:
            el['keterangan'] = cat_map[str_id]
    return output

# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf",   default=DEFAULT_PDF)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--inspeksi-json", default="hasil_inspeksi.json")
    args = ap.parse_args()

    if not os.path.exists(args.pdf):
        print("[ERROR] File tidak ditemukan: {}".format(args.pdf)); sys.exit(1)

    print("=" * 72)
    print("  PARSE FORM SKETCHUP IFC  ->  JSON")
    print("=" * 72)
    print("\n[1] Baca teks dari PDF: {}...".format(args.pdf))
    words = extract_words(args.pdf)

    print("\n[2] Kelompokkan baris dan cari kolom...")
    rows = group_rows(words, tol=4)
    print("  Total baris: {}".format(len(rows)))

    header_idx, col_x = find_col_positions(rows)

    if header_idx is None:
        print("[ERROR] Header tabel tidak ditemukan!"); sys.exit(1)

    if args.debug:
        for i, row in enumerate(rows[max(0, header_idx-1):header_idx+8]):
            print("  Row {}: {}".format(header_idx-1+i, ' | '.join(w['text'] for w in row)))

    print("\n[3] Ekstrak data...")
    records = parse_rows(rows, header_idx, col_x)
    print("  Elemen ditemukan: {}".format(len(records)))

    output = {
        "source"     : args.pdf,
        "total"      : len(records),
        "elements"   : records,
        "globalid_map": {r["definition"]: r["instance"] for r in records if r["definition"]},
    }

    print("\n[4] Merge keterangan dari hasil_inspeksi.json...")
    output = merge_keterangan(output, args.inspeksi_json)

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 72)
    print("  HASIL EKSTRAKSI:")
    print("=" * 72)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print("\n[OK] Tersimpan: {}".format(OUTPUT_JSON))
    print("=" * 72)

if __name__ == "__main__":
    main()
