# find_python_processes.py
import subprocess

def main():
    for name in ["python.exe", "python3.exe", "python3.13.exe"]:
        try:
            print(f"=== Querying {name} ===")
            output = subprocess.check_output(f"wmic process where \"name='{name}'\" get ProcessID, CommandLine", shell=True)
            print(output.decode('utf-8', errors='ignore'))
        except Exception as e:
            print(f"Failed for {name}:", e)

if __name__ == "__main__":
    main()
