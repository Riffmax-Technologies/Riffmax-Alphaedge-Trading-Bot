# kill_other_pythons.py
import os
import subprocess
import sys

def main():
    my_pid = os.getpid()
    print(f"My PID: {my_pid}")
    
    # We query all python3.13.exe processes
    for name in ["python.exe", "python3.exe", "python3.13.exe"]:
        try:
            output = subprocess.check_output(f"wmic process where \"name='{name}'\" get ProcessID", shell=True)
            lines = output.decode('utf-8', errors='ignore').strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line or "ProcessId" in line:
                    continue
                try:
                    pid = int(line)
                    if pid != my_pid:
                        print(f"Killing process {pid}...")
                        subprocess.call(f"taskkill /F /PID {pid}", shell=True)
                except ValueError:
                    pass
        except Exception as e:
            print(f"Failed for {name}: {e}")

if __name__ == "__main__":
    main()
