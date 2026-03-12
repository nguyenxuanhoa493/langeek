# Langeek Crawler

Mô tả
-----
Trình thu thập dữ liệu (crawler) đơn giản cho dự án Langeek. Script chính nằm trong `crawler.py`.

Yêu cầu
-------
- Python 3.8+
- (Tùy chọn) `requirements.txt` nếu dự án cần thư viện bên ngoài

Cài đặt
-------
1. Tạo môi trường ảo (khuyến nghị):

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Cài dependencies (nếu có):

   ```bash
   pip install -r requirements.txt
   ```

Sử dụng
-------
- Chạy crawler:

  ```bash
  python crawler.py
  ```

Cấu hình
--------
- Chỉnh sửa các tham số trong `crawler.py` để thay đổi nguồn dữ liệu, thời gian chờ, hoặc định dạng đầu ra.


Lưu ý: Định dạng chính xác và tên trường có thể thay đổi trong `crawler.py` — chỉnh sửa code nếu bạn muốn xuất ra trường hoặc định dạng khác (ví dụ: thêm `source_id`, `images`, hoặc `summary`).

Cơ sở dữ liệu (SQLite)
--------
Crawler lưu dữ liệu vào file SQLite `langeek_vocab.db` (tạo bởi hàm `init_db()` trong `crawler.py`). Các bảng và cột chính được tạo như sau:

```sql
CREATE TABLE IF NOT EXISTS levels (
   id INTEGER PRIMARY KEY,
   title TEXT,
   original_title TEXT,
   url_id TEXT
);

CREATE TABLE IF NOT EXISTS subcategories (
   id INTEGER PRIMARY KEY,
   level_id INTEGER,
   title TEXT,
   original_title TEXT,
   url_id TEXT,
   position INTEGER
);

CREATE TABLE IF NOT EXISTS vocabularies (
   id INTEGER PRIMARY KEY,
   subcategory_id INTEGER,
   word TEXT,
   pronunciation TEXT,
   pronunciation_ipa TEXT,
   audio_url TEXT,
   local_audio_path TEXT,
   meaning_vi TEXT,
   synonyms TEXT,
   image_url TEXT,
   local_image_path TEXT
);

CREATE TABLE IF NOT EXISTS examples (
   id INTEGER PRIMARY KEY,
   vocab_id INTEGER,
   example_en TEXT,
   example_vi TEXT,
   audio_url TEXT,
   local_audio_path TEXT
);
```

Giải thích các bảng chính:

- **levels**: thông tin các cấp (level) - `id`, `title`, `original_title`, `url_id`.
- **subcategories**: các danh mục con thuộc `levels` - `level_id` tham chiếu đến `levels.id`; có `position` để sắp xếp.
- **vocabularies**: từ vựng thuộc `subcategories` - lưu `word`, `pronunciation`, `meaning_vi`, `synonyms` (chuỗi phân cách bằng dấu phẩy), đường dẫn âm thanh/hình ảnh và đường dẫn cục bộ sau khi tải về.
- **examples**: câu ví dụ cho từ vựng - `vocab_id` tham chiếu đến `vocabularies.id`, kèm audio nếu có.

Ghi chú:

- `synonyms` được lưu dưới dạng chuỗi (dấu phẩy) trong cột `synonyms`. Bạn có thể thay bằng bảng riêng nếu cần truy vấn nâng cao.
- Mặc định không bật ràng buộc foreign key trong SQLite; nếu cần, hãy bật `PRAGMA foreign_keys = ON` khi kết nối.
- File cơ sở dữ liệu tạo tại repo root: `langeek_vocab.db`. Bạn có thể xóa hoặc đổi tên để khởi tạo lại database.

Đóng góp
--------
- Mở issue hoặc gửi pull request để đóng góp.

License
-------
- Thêm file `LICENSE` nếu cần (mặc định chưa có).

Liên hệ
-------
- Thêm tên/tài khoản liên hệ tại đây nếu muốn.
