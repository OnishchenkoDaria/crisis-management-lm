import os
import requests
import re

# more robust version of fetching data using request
# and efficient for VPN user
if not os.path.exists("the-verdict.txt"):
    url = (
        "https://raw.githubusercontent.com/rasbt/"
        "LLMs-from-scratch/main/ch02/01_main-chapter-code/"
        "the-verdict.txt"
    )
    file_path = "the-verdict.txt"

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    with open(file_path, "wb") as f:
        f.write(response.content)

with open("the-verdict.txt", "r", encoding="utf-8") as f:
    raw_text = f.read()

result = re.split(r'([,.:;?_!"()\']|--|\s)', raw_text)
# strip whitespace from each item and then filter out any empty strings
tokenised = [item.strip() for item in result if item.strip()]

all_words = sorted(set(tokenised)) # sorted unique alphabetic order
vocabulary_size = len(all_words)

vocab = {token:integer for integer,token in enumerate(all_words)}

#show all entries
for i, item in enumerate(vocab.items()):
    print(item)
    if i >= 50:
        break