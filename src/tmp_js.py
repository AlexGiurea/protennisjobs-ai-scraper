import json
import requests
import re

urls = [
    "https://protennisjobs.com/js/search.js",
    "https://protennisjobs.com/js/responsive.js",
    "https://protennisjobs.com/js/rrssb.min.js",
    "https://protennisjobs.com/index.php?js=upm_image",
]

for url in urls:
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    text = resp.text
    if any(k in text.lower() for k in ["contact", "email", "apply", "classified", "job"]):
        hits = sorted(set(re.findall(r"https?://[^'\"\s]+", text)))
        print(url, "len", len(text), "hits", hits[:10])
        for term in ["contact", "email", "apply", "classified", "job"]:
            if term in text.lower():
                print(" term", term)
        print("---")
