import requests
import json
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
}

def fetch_and_extract_next_data(url, prefix):
    response = requests.get(url, headers=headers)
    print(f"Fetching {url}... Status: {response.status_code}")
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        script = soup.find('script', id='__NEXT_DATA__')
        if script and script.string:
            data = json.loads(script.string)
            with open(f'{prefix}_next_data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Saved {prefix}_next_data.json")
        else:
            print("No __NEXT_DATA__ found")
    else:
        print("Failed to fetch")

# Category (Level a1-level)
fetch_and_extract_next_data('https://langeek.co/en/vocab/category/1/a1-level', 'category')

# Subcategory (learn vocab)
fetch_and_extract_next_data('https://langeek.co/en-VI/vocab/subcategory/1/learn', 'subcategory')

