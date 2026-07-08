import pandas as pd
import os
import glob

# Find the xlsx file
base = r"D:\SDK\HIK SDK"
xlsx_files = glob.glob(os.path.join(base, "**", "*.xlsx"), recursive=True)
print("Found xlsx files:")
for f in xlsx_files:
    print(f"  {f}")

# Read the ISAPI guide xlsx
for f in xlsx_files:
    if "ISAPI" in f and "指南" in f:
        print(f"\n=== Reading: {f} ===")
        try:
            all_sheets = pd.read_excel(f, sheet_name=None)
            print(f"Sheets: {list(all_sheets.keys())}")
            for name, df in all_sheets.items():
                print(f"\n--- Sheet: {name} (rows={len(df)}) ---")
                # Search for relevant keywords
                for idx, row in df.iterrows():
                    row_str = ' '.join([str(v) for v in row.values if pd.notna(v)])
                    if any(kw in row_str.lower() for kw in ['daynight', 'ircut', 'dss', 'filter', '日夜', '慢快门', '滤镜', 'ir_cut', 'ir cut']):
                        print(f"  Row {idx}: {row_str[:300]}")
        except Exception as e:
            print(f"Error: {e}")
