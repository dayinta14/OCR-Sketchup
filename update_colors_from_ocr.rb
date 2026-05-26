# update_colors_from_ocr.rb
# Otomatis baca hasil_sketchup_ifc.json -> deteksi elemen -> warnai

require 'json'

model      = Sketchup.active_model
json_path  = File.join(File.dirname(__FILE__), 'hasil_sketchup_ifc.json')

unless File.exist?(json_path)
  puts "[ERROR] File tidak ditemukan: #{json_path}"
  return
end

data       = JSON.parse(File.read(json_path, encoding: 'utf-8'))
elements   = data['elements'] || []

warna = {
  'A' => { r: 0,   g: 200, b: 0,   label: 'Baik_A'     },
  'B' => { r: 0,   g: 100, b: 255, label: 'Perhatian_B' },
  'C' => { r: 255, g: 220, b: 0,   label: 'Sedang_C'    },
  'D' => { r: 255, g: 120, b: 0,   label: 'Buruk_D'     },
  'E' => { r: 220, g: 0,   b: 0,   label: 'Kritis_E'    },
}

# Bangun map: nama_instance => { kat, no, ifc_type }
instance_map = {}
elements.each do |el|
  inst = el['instance'].to_s.strip
  kat  = (el['keterangan'] || el['kategori'] || '').to_s.strip.upcase
  instance_map[inst] = { kat: kat, no: el['no'], ifc_type: el['tag'] }
end

puts "=" * 60
puts "  UPDATE WARNA - auto-deteksi dari JSON"
puts "=" * 60
puts "Elemen dari JSON: #{instance_map.keys.join(', ')}"
puts ""

# Warnai semua Face di dalam entity secara rekursif
def paint_all_faces(entities, mat)
  entities.each do |sub|
    if sub.is_a?(Sketchup::Face)
      sub.material         = mat
      sub.back_material    = mat
    elsif sub.is_a?(Sketchup::Group)
      paint_all_faces(sub.entities, mat)
    elsif sub.is_a?(Sketchup::ComponentInstance)
      sub.material = mat
      paint_all_faces(sub.definition.entities, mat)
    end
  end
end

# Kumpulkan SEMUA ComponentInstance rekursif beserta namanya
def collect_components(entities, result = [])
  entities.each do |e|
    if e.is_a?(Sketchup::ComponentInstance)
      result << e
      collect_components(e.definition.entities, result)
    elsif e.is_a?(Sketchup::Group)
      collect_components(e.entities, result)
    end
  end
  result
end

all_comps = collect_components(model.entities)
puts "Total ComponentInstance ditemukan: #{all_comps.size}"
puts ""

model.start_operation('Update Warna Inspeksi', true)

updated   = 0
not_found = []

instance_map.each do |inst_name, info|
  kat      = info[:kat]
  no       = info[:no]
  ifc_type = info[:ifc_type]
  col      = warna[kat]

  unless col
    puts "[SKIP] No.#{no} - Kategori '#{kat}' tidak dikenal"
    next
  end

  # Cari component yang namanya cocok (e.name atau e.definition.name)
  targets = all_comps.select do |e|
    e.name.to_s == inst_name ||
    (e.respond_to?(:definition) && e.definition.name.to_s == inst_name)
  end

  if targets.empty?
    puts "[NOT FOUND] No.#{no} #{ifc_type} Instance=#{inst_name}"
    not_found << inst_name
    next
  end

  mat_name = "Inspeksi_#{kat}_#{col[:label]}"
  mat      = model.materials[mat_name] || model.materials.add(mat_name)
  mat.color = Sketchup::Color.new(col[:r], col[:g], col[:b])
  mat.alpha = 0.9

  targets.each do |ent|
    ent.material = mat
    paint_all_faces(ent.definition.entities, mat)
  end

  puts "[OK] No.#{no} #{ifc_type} Instance=#{inst_name} (#{targets.size} component) -> Kat.#{kat} [#{col[:label]}]"
  updated += 1
end

model.commit_operation
model.active_view.invalidate

puts ""
puts "=" * 60
puts "  SELESAI: #{updated}/#{instance_map.size} diwarnai"
puts "  Tidak ditemukan: #{not_found.join(', ')}" unless not_found.empty?
puts ""
puts "  Jika warna belum tampak:"
puts "  -> View -> Face Style -> Shaded with Textures"
puts "=" * 60
