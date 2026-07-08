import glob, os

base = r"D:\SDK\HIK SDK"
pdf_files = glob.glob(os.path.join(base, "**", "*.pdf"), recursive=True)
print(f"Found {len(pdf_files)} PDF files:")
for f in pdf_files:
    print(f"  {len(f)} bytes: {f}")
    if "ISAPI" in f and "球" in f:
        print(f"\n==> TARGET: {f}")
        # Test reading with raw bytes path
        try:
            with open(f, "rb") as fp:
                header = fp.read(10)
                print(f"    Header: {header}")
                print(f"    PDF valid!")
        except Exception as e:
            print(f"    Error: {e}")
