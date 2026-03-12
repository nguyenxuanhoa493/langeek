import requests
import json
from bs4 import BeautifulSoup

url = 'https://langeek.co/en/vocab'
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
}

response = requests.get(url, headers=headers)
print(f"Status Code: {response.status_code}")

if response.status_code == 200:
    html = response.text
    with open('langeek_vocab.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    soup = BeautifulSoup(html, 'html.parser')
    scripts = soup.find_all('script')
    for i, script in enumerate(scripts):
        if script.string and ('__NEXT_DATA__' in script.string or 'vocab' in script.string):
            print(f"Found potentially useful script tag {i}")
            with open(f'script_{i}.js', 'w', encoding='utf-8') as f:
                f.write(script.string)
    
    links = soup.find_all('a', href=True)
    level_links = [link['href'] for link in links if 'category' in link['href'] or 'level' in link['href']]
    print(f"Found {len(level_links)} level links")
    for l in set(level_links[:10]):
        print(l)
else:
    print("Failed to fetch.")
