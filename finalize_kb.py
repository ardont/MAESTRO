import os
import glob

kb_dir = r"c:\Users\Maxim\Desktop\фокусы\хакатоны\рлт\агентная система поддержки\txt_dataset\roseltorg_kb"
merged_path = r"c:\Users\Maxim\Desktop\фокусы\хакатоны\рлт\агентная система поддержки\txt_dataset\roseltorg_knowledge_base_full.txt"

txt_files = glob.glob(os.path.join(kb_dir, "*.txt"))
print(f"Found {len(txt_files)} text files in {kb_dir}")

total_chars = 0
total_lines = 0

with open(merged_path, "w", encoding="utf-8") as outfile:
    outfile.write("========================================================\n")
    outfile.write("ROSELTORG KNOWLEDGE BASE - FULL EXPORT (TXT)\n")
    outfile.write(f"Total Articles Extracted: {len(txt_files)}\n")
    outfile.write("========================================================\n\n")
    
    for fpath in txt_files:
        try:
            with open(fpath, "r", encoding="utf-8") as infile:
                content = infile.read()
                outfile.write(content)
                outfile.write("\n\n" + "#"*80 + "\n\n")
                total_chars += len(content)
                total_lines += len(content.splitlines())
        except Exception as e:
            print(f"Error reading {fpath}: {e}")

print(f"Successfully generated merged file: {merged_path}")
print(f"Total Stats: {len(txt_files)} articles, {total_chars} characters, {total_lines} lines.")
