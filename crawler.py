import os
import sqlite3
import requests
import json
from bs4 import BeautifulSoup
import time
import argparse

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
}

BASE_URL = 'https://langeek.co'

def download_file(url, folder, filename):
    if not url: return None
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    if os.path.exists(filepath):
        return filepath
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(r.content)
            return filepath
    except Exception as e:
        print(f"Error downloading {url}: {e}")
    return None

def init_db():
    conn = sqlite3.connect('langeek_vocab.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS levels (
        id INTEGER PRIMARY KEY, title TEXT, original_title TEXT, url_id TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS subcategories (
        id INTEGER PRIMARY KEY, level_id INTEGER, title TEXT, original_title TEXT, url_id TEXT, position INTEGER
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS vocabularies (
        id INTEGER PRIMARY KEY, subcategory_id INTEGER, word TEXT, pronunciation TEXT,
        pronunciation_ipa TEXT, audio_url TEXT, local_audio_path TEXT,
        meaning_vi TEXT, synonyms TEXT, image_url TEXT, local_image_path TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS examples (
        id INTEGER PRIMARY KEY, vocab_id INTEGER, example_en TEXT, example_vi TEXT,
        audio_url TEXT, local_audio_path TEXT
    )''')
    conn.commit()
    return conn

def get_next_data(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            if script:
                return json.loads(script.string)
    except Exception as e:
        print(f"Error fetching next data for {url}: {e}")
    return None

def scrape_levels(limit_levels=None, limit_subcats=None):
    conn = init_db()
    cursor = conn.cursor()
    print(f"Fetching main page: {BASE_URL}/en/vocab")
    data = get_next_data(f'{BASE_URL}/en/vocab')
    if not data:
        print("Failed to get __NEXT_DATA__ from main page")
        return
    
    try:
        collections = data['props']['pageProps']['initialState']['static']['collections']
        # The user wants "các Level". It is in 'level-based'
        levels = collections['level-based']['categories']
        
        if limit_levels:
            levels = levels[:limit_levels]
            
        total_levels = len(levels)
        print(f"Found {total_levels} levels to scrape.")
        for i, lv in enumerate(levels, 1):
            cursor.execute('INSERT OR IGNORE INTO levels (id, title, original_title, url_id) VALUES (?, ?, ?, ?)',
                           (lv['id'], lv['title'], lv.get('originalTitle', ''), lv['urlId']))
            print(f"\n[{i}/{total_levels}] LEVEL: {lv['title']} (ID: {lv['id']})")
            
            # Scrape subcategories for each level
            scrape_subcategories(conn, lv['id'], lv['urlId'], limit_subcats)
            
    except KeyError as e:
        print("Data structure changed:", e)
    conn.commit()
    conn.close()

def scrape_subcategories(conn, level_id, level_url_id, limit_subcats=None):
    cursor = conn.cursor()
    url = f'{BASE_URL}/en/vocab/category/{level_id}/{level_url_id}'
    print(f"Fetching subcategories for level {level_id}... {url}")
    data = get_next_data(url)
    if not data: return
    
    try:
        subcats = data['props']['pageProps']['initialState']['static']['category']['subCategories']
        
        if limit_subcats:
            subcats = subcats[:limit_subcats]
            
        total_subcats = len(subcats)
        print(f"  Found {total_subcats} subcategories.")
        for j, sub in enumerate(subcats, 1):
            cursor.execute('''INSERT OR IGNORE INTO subcategories
                              (id, level_id, title, original_title, url_id, position)
                              VALUES (?, ?, ?, ?, ?, ?)''',
                           (sub['id'], level_id, sub['title'], sub.get('originalTitle', ''), sub.get('urlId', ''), sub.get('position', 0)))
            print(f"  -> [{j}/{total_subcats}] SUBCATEGORY: {sub['title']} (ID: {sub['id']})")
            conn.commit()
            
            # Scrape vocab for each subcategory
            scrape_vocab(conn, sub['id'])
            time.sleep(1) # Be nice
    except Exception as e:
        print(f"Error scraping subcategory for level {level_id}: {e}")

def scrape_vocab(conn, subcategory_id):
    cursor = conn.cursor()
    
    # Needs en-VI context to get Vietnamese translations
    url = f'{BASE_URL}/en-VI/vocab/subcategory/{subcategory_id}/learn'
    print(f"    Fetching vocabulary for subcategory {subcategory_id}...")
    data = get_next_data(url)
    if not data: return
    
    try:
        cards = data['props']['pageProps']['initialState']['static']['subcategory']['cards']
        total_cards = len(cards)
        print(f"    Found {total_cards} words. Downloading and saving...")
        for k, card in enumerate(cards, 1):
            c_id = card['id']
            trans = card['mainTranslation']
            if not trans: continue
            
            word = trans.get('title', '')
            pronunciation = trans.get('pronunciation', '')
            
            audio_url = trans.get('titleVoice', '')
            local_audio = ''
            if audio_url:
                local_audio = download_file(audio_url, 'media/audio', f'word_{c_id}.mp3')
            
            image_url = trans.get('wordPhoto', {}).get('photo', '')
            local_img = ''
            if image_url:
                ext = image_url.split('?')[0].split('.')[-1]
                if ext not in ['jpg','jpeg','png','webp']: ext = 'jpeg'
                local_img = download_file(image_url, 'media/images', f'word_{c_id}.{ext}')
            
            # Meaning VI
            meaning_vi = trans.get('localizedProperties', {}).get('translation', '')
            
            # IPA
            nlp = trans.get('metadata', {}).get('nlpAnalyzedData', {})
            pronunciation_ipa = nlp.get('pronunciationIPA', '')
            
            # Synonyms
            synonyms = []
            for syn in trans.get('synonyms', []):
                synonyms.append(syn.get('word', ''))
            
            # Maybe synonymCluster
            cluster = trans.get('synonymCluster')
            if cluster:
                for c in cluster.get('translations', []):
                    # avoid duplicate of itself
                    if c.get('word') != word and c.get('word') not in synonyms:
                        synonyms.append(c.get('word', ''))
                    
            synonyms_str = ', '.join(synonyms)
            
            cursor.execute('''
                INSERT OR REPLACE INTO vocabularies 
                (id, subcategory_id, word, pronunciation, pronunciation_ipa, audio_url, local_audio_path, meaning_vi, synonyms, image_url, local_image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (c_id, subcategory_id, word, pronunciation, pronunciation_ipa, audio_url, local_audio, meaning_vi, synonyms_str, image_url, local_img))
            
            # Examples
            for ex in trans.get('examples', []):
                ex_id = ex['id']
                ex_en = ex.get('example', '')
                ex_vi = ex.get('localizedProperties', {}).get('example', '')
                ex_audio = ex.get('exampleVoice', '')
                ex_local_audio = ''
                if ex_audio:
                    ex_local_audio = download_file(ex_audio, 'media/audio', f'example_{ex_id}.mp3')
                
                cursor.execute('''
                    INSERT OR REPLACE INTO examples
                    (id, vocab_id, example_en, example_vi, audio_url, local_audio_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (ex_id, c_id, ex_en, ex_vi, ex_audio, ex_local_audio))
                
            if k % 10 == 0 or k == total_cards:
                print(f"      ... processed {k}/{total_cards} words")
                
        conn.commit()
        print(f"    => Completed subcategory {subcategory_id}.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error scraping vocab for subcat {subcategory_id}: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Langeek Vocab Scraper')
    parser.add_argument('--limit-levels', type=int, help='Limit number of levels to scrape (for testing)')
    parser.add_argument('--limit-subcats', type=int, help='Limit number of subcategories per level (for testing)')
    args = parser.parse_args()

    print("Starting crawler...")
    scrape_levels(limit_levels=args.limit_levels, limit_subcats=args.limit_subcats)
    print("Crawler finished!")
