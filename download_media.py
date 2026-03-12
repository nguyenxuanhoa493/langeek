import os
import sqlite3
import random
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

# Chuyển logging hoàn toàn sang file để không làm loạn giao diện (UI) tiến trình trên Console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("media_downloader.log", encoding='utf-8')
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

def download_file(url, folder, filename, session):
    if not url: return False
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    
    # Kiểm tra file đã tồn tại và có dung lượng > 0
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return True
        
    try:
        r = session.get(url, headers=get_random_headers(), timeout=15)
        if r.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(r.content)
            logging.debug(f"Downloaded: {filepath}")
            return True
        else:
            logging.warning(f"Failed to download {url}. Status code: {r.status_code}")
    except Exception as e:
        logging.error(f"Error downloading {url}: {e}")
    return False

def get_media_urls_from_db(db_path='langeek_vocab.db'):
    """Quét Database và gom nhóm tất cả các đường link ảnh/audio chưa có file ở ổ cứng, kèm theo thông tin DB để update."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    media_list = []
    
    # 1. Lấy Audio và Image từ bảng vocabularies
    try:
        cursor.execute("SELECT id, audio_url, image_url FROM vocabularies")
        vocabs = cursor.fetchall()
        for v_id, v_audio, v_image in vocabs:
            if v_audio:
                media_list.append((v_audio, 'media/audio', f'word_{v_id}.mp3', 'vocabularies', 'local_audio_path', v_id))
            if v_image:
                ext = v_image.split('?')[0].split('.')[-1]
                if ext not in ['jpg','jpeg','png','webp']: ext = 'jpeg'
                media_list.append((v_image, 'media/images', f'word_{v_id}.{ext}', 'vocabularies', 'local_image_path', v_id))
    except sqlite3.OperationalError as e:
        logging.error(f"Error reading vocabularies table: {e}")
        
    # 2. Lấy Audio từ bảng examples
    try:
        cursor.execute("SELECT id, audio_url FROM examples")
        examples = cursor.fetchall()
        for e_id, e_audio in examples:
            if e_audio:
                media_list.append((e_audio, 'media/audio', f'example_{e_id}.mp3', 'examples', 'local_audio_path', e_id))
    except sqlite3.OperationalError as e:
        logging.error(f"Error reading examples table: {e}")
        
    conn.close()
    
    # Lọc lại danh sách: chỉ giữ những file CHƯA được tải về thành công
    final_list = []
    for url, folder, filename, table, col, record_id in media_list:
        filepath = os.path.join(folder, filename)
        if not (os.path.exists(filepath) and os.path.getsize(filepath) > 0):
            final_list.append((url, folder, filename, table, col, record_id))
            
    return final_list

def update_db(db_path, table, col, record_id, filepath):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE {table} SET {col} = ? WHERE id = ?", (filepath, record_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error updating DB for {table} id {record_id}: {e}")

def download_media_workers(media_list, db_path='langeek_vocab.db', max_workers=10):
    total = len(media_list)
    if total == 0:
        tqdm.write("Tất cả file media đã được tải đầy đủ!")
        logging.info("Tất cả file media đã được tải đầy đủ!")
        return

    tqdm.write(f"Bắt đầu tải {total} file media còn thiếu với {max_workers} luồng xử lý đồng thời...")
    logging.info(f"Bắt đầu tải {total} file media còn thiếu với {max_workers} luồng xử lý đồng thời...")
    session = get_session()
    
    success_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(download_file, url, folder, filename, session): (url, folder, filename, table, col, record_id) 
                         for url, folder, filename, table, col, record_id in media_list}
                         
        with tqdm(total=total, desc="Tiến độ tải Media", unit="file", dynamic_ncols=True) as pbar:
            for future in as_completed(future_to_url):
                url, folder, filename, table, col, record_id = future_to_url[future]
                try:
                    success = future.result()
                    if success:
                        success_count += 1
                        # Update DB sau khi tải xong file này
                        filepath = os.path.join(folder, filename)
                        update_db(db_path, table, col, record_id, filepath)
                except Exception as exc:
                    logging.error(f'{url} sinh ra ngoại lệ: {exc}')
                
                pbar.update(1)
                
    tqdm.write(f"Hoàn thành! Tải thành công {success_count}/{total} files.")
    logging.info(f"Hoàn thành! Tải thành công {success_count}/{total} files.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Công cụ tách rời chuyên tải Media cho Langeek Scraper')
    parser.add_argument('--workers', type=int, default=10, help='Số luồng tải đồng thời (Mặc định: 10)')
    parser.add_argument('--db', type=str, default='langeek_vocab.db', help='Đường dẫn file database')
    args = parser.parse_args()

    if not os.path.exists(args.db):
        tqdm.write(f"LỖI: Không tìm thấy database: {args.db}. Vui lòng chạy crawler.py trước.")
        logging.error(f"Không tìm thấy database: {args.db}. Vui lòng chạy crawler.py trước.")
    else:
        pending_media = get_media_urls_from_db(args.db)
        download_media_workers(pending_media, db_path=args.db, max_workers=args.workers)
