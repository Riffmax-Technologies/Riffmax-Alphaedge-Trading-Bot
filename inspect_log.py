import pandas as pd, os, sys
path = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/brain/86033144-bf85-4d61-ac17-b7e233ed37cb/trade_log.xlsx"
if not os.path.exists(path):
    print('Log file not found')
    sys.exit(0)

df = pd.read_excel(path, engine='openpyxl')
print('Rows in log:', len(df))
print(df.head())
