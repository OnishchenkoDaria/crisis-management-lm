import os
import urllib.request

if not os.path.exists('the-verdict.txt'):
    url = (
        "https://raw.githubusercontent.com/rasbt/"
        "LLMs-from-scratch/main/ch02/01_main-chapter-code/"
        "the-verdict.txt"
    )
    filepath = "the-verdict.txt"
    urllib.request.urlretrieve(url, filepath)

with open("the-verdict.txt", "r", encoding="utf-8") as f:
    raw_text = f.read()

print(raw_text)