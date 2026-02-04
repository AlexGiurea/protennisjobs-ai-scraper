import json
import os
import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

with open(os.path.join(DATA_DIR, "cookies.json"), "r", encoding="utf-8") as f:
    cookies = json.load(f)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})
for k, v in cookies.items():
    session.cookies.set(k, v)

url = "https://protennisjobs.com/tennis-jobs/25080/tennis-pickleball-professional"
resp = session.get(url, headers={"Referer": "https://protennisjobs.com/category/tennis-professional/"})
soup = BeautifulSoup(resp.text, 'html.parser')
for s in soup.find_all('script'):
    src = s.get('src')
    if src:
        print(src)
