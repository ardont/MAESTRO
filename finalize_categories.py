import os
import glob

DATASET_DIR = r"c:\Users\Maxim\Desktop\фокусы\хакатоны\рлт\агентная система поддержки\dataset"
LEG_DIR = os.path.join(DATASET_DIR, "1_legislation")
INST_DIR = os.path.join(DATASET_DIR, "2_instructions")
INST_OFFICIAL_DIR = os.path.join(INST_DIR, "roseltorg_official_docs")
INST_KB_DIR = os.path.join(INST_DIR, "roseltorg_kb_articles")

# 1. Legislation Combined
leg_combined_path = os.path.join(DATASET_DIR, "legislation_combined.txt")
leg_files = glob.glob(os.path.join(LEG_DIR, "*.txt"))
leg_chars = 0
leg_lines = 0

with open(leg_combined_path, "w", encoding="utf-8") as leg_out:
    leg_out.write("========================================================\n")
    leg_out.write("ЗАКОНОДАТЕЛЬНАЯ СФЕРА - СВОДНЫЙ ФАЙЛ (TXT)\n")
    leg_out.write(f"Всего законов и нормативно-правовых актов: {len(leg_files)}\n")
    leg_out.write("========================================================\n\n")
    for lf in leg_files:
        with open(lf, "r", encoding="utf-8") as infile:
            text = infile.read()
            leg_out.write(f"DOCUMENT FILE: {os.path.basename(lf)}\n{'='*60}\n")
            leg_out.write(text)
            leg_out.write("\n\n" + "#"*80 + "\n\n")
            leg_chars += len(text)
            leg_lines += len(text.splitlines())

print(f"[LEGISLATION] Saved {leg_combined_path}")
print(f"  -> {len(leg_files)} files, {leg_chars} chars, {leg_lines} lines")

# 2. Instructions Combined
inst_combined_path = os.path.join(DATASET_DIR, "instructions_combined.txt")
inst_files = glob.glob(os.path.join(INST_DIR, "*.txt")) + \
             glob.glob(os.path.join(INST_OFFICIAL_DIR, "*.txt")) + \
             glob.glob(os.path.join(INST_KB_DIR, "*.txt"))

inst_chars = 0
inst_lines = 0

with open(inst_combined_path, "w", encoding="utf-8") as inst_out:
    inst_out.write("========================================================\n")
    inst_out.write("ИНСТРУКЦИИ И РЕГЛАМЕНТЫ - СВОДНЫЙ ФАЙЛ (TXT)\n")
    inst_out.write(f"Всего инструкций, регламентов и статей: {len(inst_files)}\n")
    inst_out.write("========================================================\n\n")
    for inf in inst_files:
        with open(inf, "r", encoding="utf-8") as infile:
            text = infile.read()
            inst_out.write(f"DOCUMENT FILE: {os.path.basename(inf)}\n{'='*60}\n")
            inst_out.write(text)
            inst_out.write("\n\n" + "#"*80 + "\n\n")
            inst_chars += len(text)
            inst_lines += len(text.splitlines())

print(f"[INSTRUCTIONS] Saved {inst_combined_path}")
print(f"  -> {len(inst_files)} files, {inst_chars} chars, {inst_lines} lines")

# 3. Full Complete Dataset Combined
full_combined_path = os.path.join(DATASET_DIR, "full_dataset_combined.txt")
with open(full_combined_path, "w", encoding="utf-8") as full_out:
    full_out.write("========================================================\n")
    full_out.write("ПОЛНАЯ БАЗА ЗНАНИЙ (ЗАКОНОДАТЕЛЬСТВО + ИНСТРУКЦИИ)\n")
    full_out.write(f"Законодательная сфера: {len(leg_files)} документов\n")
    full_out.write(f"Сфера инструкций и регламентов: {len(inst_files)} документов\n")
    full_out.write("========================================================\n\n")
    with open(leg_combined_path, "r", encoding="utf-8") as f1:
        full_out.write(f1.read())
    full_out.write("\n\n" + "="*100 + "\n\n")
    with open(inst_combined_path, "r", encoding="utf-8") as f2:
        full_out.write(f2.read())

print(f"[FULL DATASET] Saved {full_combined_path}")
print(f"  -> Total chars: {leg_chars + inst_chars}, Total lines: {leg_lines + inst_lines}")
