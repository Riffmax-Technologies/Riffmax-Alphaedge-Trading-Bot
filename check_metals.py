# check_metals.py
import os
path = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/scratch/alphaedge_trading.log"
if os.path.exists(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    print("=== Checking for Metals Filter actions today ===")
    count = 0
    for line in lines[-2000:]: # Look at recent log lines
        if "Correlation" in line or "XAU" in line or "XAG" in line:
            if "Successfully connected" not in line and "Successfully disconnected" not in line and "Scanning all" not in line:
                print(line.strip())
                count += 1
    if count == 0:
        print("No metals signals recorded in the last 2000 lines.")
else:
    print("Log not found")
