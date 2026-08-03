# extract_github_links.py
import json
import re
import os

def main():
    transcript_path = r"C:\Users\DATA ENG. OLA\.gemini\antigravity\brain\86033144-bf85-4d61-ac17-b7e233ed37cb\.system_generated\logs\transcript.jsonl"
    if not os.path.exists(transcript_path):
        print(f"Transcript path not found: {transcript_path}")
        return
        
    print(f"Reading transcript: {transcript_path}")
    github_links = []
    
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            try:
                data = json.loads(line)
                # Look at user inputs and system generated content
                content = data.get("content", "")
                if not content:
                    continue
                    
                # Find all URLs matching github or skills.sh
                urls = re.findall(r'https?://[^\s()<>]+', content)
                for url in urls:
                    # Clean trailing punctuation
                    url = url.rstrip('.,;:"\'`')
                    if "github" in url or "skills" in url:
                        if url not in github_links:
                            github_links.append(url)
            except Exception as e:
                pass
                
    print("\n=== Extracted Links ===")
    if not github_links:
        print("No matching links found.")
    for link in github_links:
        print(link)

if __name__ == "__main__":
    main()
