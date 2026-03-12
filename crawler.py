import os
import sqlite3
import requests
import json
from bs4 import BeautifulSoup
import time
import argparse
import random
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

# Chuyển logging hoàn toàn sang file để không làm loạn giao diện (UI) tiến trình trên Console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("crawler.log", encoding='utf-8')
    ]
)

USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/114.0'
]

def get_random_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS)
    }

BASE_URL = 'https://langeek.co'

def get_session():
    session = requests.Session()
    retry = Retry(
        total=5,
        read=5,
        connect=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def random_sleep(min_time=0.5, max_time=2.0):
    time.sleep(random.uniform(min_time, max_time))

def download_file(url, folder, filename, session):
    if not url: return None
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return filepath
        
    try:
        r = session.get(url, headers=get_random_headers(), timeout=15)
        if r.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(r.content)
            return filepath
        else:
            logging.warning(f"Failed to download {url}. Status code: {r.status_code}")
    except Exception as e:
        logging.error(f"Error downloading {url}: {e}")
    return None

def init_db():
    conn = sqlite3.connect('langeek_vocab.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS levels (
        id INTEGER PRIMARY KEY, title TEXT, original_title TEXT, url_id TEXT
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS subcategories (
        id INTEGER PRIMARY KEY, level_id INTEGER, title TEXT, original_title TEXT, url_id TEXT, position INTEGER,
        status TEXT DEFAULT 'PENDING'
    )''')
    
    try:
        cursor.execute("ALTER TABLE subcategories ADD COLUMN status TEXT DEFAULT 'PENDING'")
    except sqlite3.OperationalError:
        pass

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

def get_next_data(url, session):
    try:
        r = session.get(url, headers=get_random_headers(), timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            if script:
                return json.loads(script.string)
        else:
            logging.warning(f"Failed to fetch {url}. Status code: {r.status_code}")
    except Exception as e:
        logging.error(f"Error fetching next data for {url}: {e}")
    return None

def scrape_levels(conn, session, limit_levels=None, limit_subcats=None):
    cursor = conn.cursor()
    tqdm.write(f"Fetching main page: {BASE_URL}/en/vocab")
    logging.info(f"Fetching main page: {BASE_URL}/en/vocab")
    data = get_next_data(f'{BASE_URL}/en/vocab', session)
    if not data:
        tqdm.write("Failed to get __NEXT_DATA__ from main page")
        logging.error("Failed to get __NEXT_DATA__ from main page")
        return
    
    try:
        collections = data['props']['pageProps']['initialState']['static']['collections']
        levels = collections['level-based']['categories']
        
        if limit_levels:
            levels = levels[:limit_levels]
            
        total_levels = len(levels)
        tqdm.write(f"Found {total_levels} levels to scrape structure.")
        logging.info(f"Found {total_levels} levels to scrape.")
        
        for lv in tqdm(levels, desc="[Phase 1] Trích xuất cấu trúc (Levels)  ", unit="level", dynamic_ncols=True):
            cursor.execute('INSERT OR IGNORE INTO levels (id, title, original_title, url_id) VALUES (?, ?, ?, ?)',
                           (lv['id'], lv['title'], lv.get('originalTitle', ''), lv['urlId']))
            logging.info(f"LEVEL: {lv['title']} (ID: {lv['id']})")
            
            scrape_subcategories(conn, session, lv['id'], lv['urlId'], limit_subcats)
            random_sleep()
            
    except KeyError as e:
        logging.error(f"Data structure changed: {e}")
        tqdm.write(f"Data structure changed: {e}")
    conn.commit()

def scrape_subcategories(conn, session, level_id, level_url_id, limit_subcats=None):
    cursor = conn.cursor()
    url = f'{BASE_URL}/en/vocab/category/{level_id}/{level_url_id}'
    logging.info(f"  Fetching subcategories for level {level_id}... {url}")
    data = get_next_data(url, session)
    if not data: return
    
    try:
        subcats = data['props']['pageProps']['initialState']['static']['category']['subCategories']
        
        if limit_subcats:
            subcats = subcats[:limit_subcats]
            
        for sub in subcats:
            cursor.execute('''INSERT OR IGNORE INTO subcategories
                              (id, level_id, title, original_title, url_id, position, status)
                              VALUES (?, ?, ?, ?, ?, ?, 'PENDING')''',
                           (sub['id'], level_id, sub['title'], sub.get('originalTitle', ''), sub.get('urlId', ''), sub.get('position', 0)))
            logging.info(f"    -> SUBCATEGORY: {sub['title']} (ID: {sub['id']})")
            conn.commit()
            random_sleep(0.5, 1.0)
    except Exception as e:
        logging.error(f"Error scraping subcategory for level {level_id}: {e}")

def download_media_workers(media_list, session, max_workers=10):
    results = {}
    total = len(media_list)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(download_file, url, folder, filename, session): (url, folder, filename) for url, folder, filename in media_list}
        
        with tqdm(total=total, desc="    Tải media song song", unit="file", leave=False, dynamic_ncols=True) as pbar:
            for future in as_completed(future_to_url):
                url, folder, filename = future_to_url[future]
                try:
                    filepath = future.result()
                    results[url] = filepath
                except Exception as exc:
                    logging.error(f'{url} generated an exception: {exc}')
                pbar.update(1)
    return results

def process_pending_subcategories(conn, session, download_media=False, limit_subcats=None):
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM subcategories WHERE status != 'DONE'")
    pending = cursor.fetchall()
    
    if limit_subcats:
        pending = pending[:limit_subcats]
        
    total_pending = len(pending)
    tqdm.write(f"\nFound {total_pending} pending subcategories to scrape vocabulary.")
    logging.info(f"Found {total_pending} pending subcategories to scrape vocabulary.")
    
    if total_pending == 0:
        return
        
    for sub_id, title in tqdm(pending, desc="[Phase 2] Cào từ vựng (Subcategories)", unit="subcat", dynamic_ncols=True):
        logging.info(f"Processing subcategory: {title} (ID: {sub_id})")
        
        cursor.execute("UPDATE subcategories SET status = 'PROCESSING' WHERE id = ?", (sub_id,))
        conn.commit()
        
        cursor.execute("DELETE FROM examples WHERE vocab_id IN (SELECT id FROM vocabularies WHERE subcategory_id = ?)", (sub_id,))
        cursor.execute("DELETE FROM vocabularies WHERE subcategory_id = ?", (sub_id,))
        conn.commit()
        
        success = scrape_vocab(conn, session, sub_id, download_media=download_media)
        
        if success:
            cursor.execute("UPDATE subcategories SET status = 'DONE' WHERE id = ?", (sub_id,))
        else:
            cursor.execute("UPDATE subcategories SET status = 'ERROR' WHERE id = ?", (sub_id,))
        conn.commit()
        random_sleep(1.0, 3.0)

def scrape_vocab(conn, session, subcategory_id, download_media=False):
    cursor = conn.cursor()
    
    url = f'{BASE_URL}/en-VI/vocab/subcategory/{subcategory_id}/learn'
    logging.info(f"      Fetching vocabulary for subcategory {subcategory_id}...")
    data = get_next_data(url, session)
    if not data: return False
    
    try:
        cards = data['props']['pageProps']['initialState']['static']['subcategory']['cards']
        total_cards = len(cards)
        logging.info(f"      Found {total_cards} words. Processing data to Database...")
        
        media_to_download = []
        
        for card in tqdm(cards, desc="    Chiết xuất từ vựng", unit="word", leave=False, dynamic_ncols=True):
            c_id = card['id']
            trans = card['mainTranslation']
            if not trans: continue
            
            word = trans.get('title', '')
            pronunciation = trans.get('pronunciation', '')
            
            audio_url = trans.get('titleVoice', '')
            local_audio = ''
            if download_media and audio_url:
                local_audio = os.path.join('media', 'audio', f'word_{c_id}.mp3')
                media_to_download.append((audio_url, 'media/audio', f'word_{c_id}.mp3'))
            
            image_url = trans.get('wordPhoto', {}).get('photo', '')
            local_img = ''
            if download_media and image_url:
                ext = image_url.split('?')[0].split('.')[-1]
                if ext not in ['jpg','jpeg','png','webp']: ext = 'jpeg'
                local_img = os.path.join('media', 'images', f'word_{c_id}.{ext}')
                media_to_download.append((image_url, 'media/images', f'word_{c_id}.{ext}'))
            
            loc_props = trans.get('localizedProperties') or {}
            meaning_vi = loc_props.get('translation', '')
            
            nlp = (trans.get('metadata') or {}).get('nlpAnalyzedData') or {}
            pronunciation_ipa = nlp.get('pronunciationIPA', '')
            
            synonyms = []
            for syn in trans.get('synonyms', []):
                synonyms.append(syn.get('word', ''))
            
            cluster = trans.get('synonymCluster')
            if cluster:
                for c in cluster.get('translations', []):
                    if c.get('word') != word and c.get('word') not in synonyms:
                        synonyms.append(c.get('word', ''))
                    
            synonyms_str = ', '.join(synonyms)
            
            cursor.execute('''
                INSERT INTO vocabularies 
                (id, subcategory_id, word, pronunciation, pronunciation_ipa, audio_url, local_audio_path, meaning_vi, synonyms, image_url, local_image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (c_id, subcategory_id, word, pronunciation, pronunciation_ipa, audio_url, local_audio, meaning_vi, synonyms_str, image_url, local_img))
            
            for ex in trans.get('examples', []):
                ex_id = ex['id']
                ex_en = ex.get('example', '')
                ex_loc_props = ex.get('localizedProperties') or {}
                ex_vi = ex_loc_props.get('example', '')
                ex_audio = ex.get('exampleVoice', '')
                ex_local_audio = ''
                if download_media and ex_audio:
                    ex_local_audio = os.path.join('media', 'audio', f'example_{ex_id}.mp3')
                    media_to_download.append((ex_audio, 'media/audio', f'example_{ex_id}.mp3'))
                
                cursor.execute('''
                    INSERT INTO examples
                    (id, vocab_id, example_en, example_vi, audio_url, local_audio_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (ex_id, c_id, ex_en, ex_vi, ex_audio, ex_local_audio))
                
        # Commit DB chốt text xong
        conn.commit()
        
        # Thiết lập đa luồng tải media ở cuối cùng sau khi cắm text
        if media_to_download:
            logging.info(f"      Downloading {len(media_to_download)} media files concurrently...")
            download_media_workers(media_to_download, session, max_workers=10)
            
        logging.info(f"      => Completed subcategory {subcategory_id}.")
        return True
    except Exception as e:
        logging.error(f"Error scraping vocab for subcat {subcategory_id}: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Langeek Vocab Scraper')
    parser.add_argument('--limit-levels', type=int, help='Limit number of levels to scrape (for testing)')
    parser.add_argument('--limit-subcats', type=int, help='Limit number of subcategories per level (for testing)')
    parser.add_argument('--download-media', action='store_true', help='Download media files (audio, images)')
    args = parser.parse_args()

    tqdm.write("Starting crawler...")
    logging.info("Starting crawler...")
    conn = init_db()
    session = get_session()
    
    tqdm.write("\n--- PHASE 1: Fetching Database Structure ---")
    scrape_levels(conn, session, limit_levels=args.limit_levels, limit_subcats=args.limit_subcats)
    
    tqdm.write("\n--- PHASE 2: Sraping Vocabulary Data ---")
    process_pending_subcategories(conn, session, download_media=args.download_media, limit_subcats=args.limit_subcats)
    
    conn.close()
    tqdm.write("\nCrawler finished successfully!")
    logging.info("Crawler finished!")
