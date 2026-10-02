# CẨM NANG TRIỂN KHAI ARTFAIR LÊN HOSTING PYTHONANYWHERE (Step-by-Step Production Guide)

Tài liệu này hướng dẫn chi tiết từng bước đưa hệ thống ARTFAIR (Frontend + Backend Django) lên dịch vụ hosting đám mây **PythonAnywhere** để bạn bè, khách hàng hoặc đối tác có thể truy cập 24/7 từ bất kỳ thiết bị nào qua Internet ngay cả khi máy tính cá nhân của bạn tắt.

---

## I. Đánh giá tính tương thích & Giới hạn gói dịch vụ PythonAnywhere

| Tiêu chí | Cấu hình ARTFAIR | Gói Free (Beginner) | Gói Hacker ($5/tháng) | Đánh giá & Khuyến nghị |
| :--- | :--- | :--- | :--- | :--- |
| **Python Version** | Python 3.12.x | Hỗ trợ 3.10, 3.11, 3.12 | Hỗ trợ 3.10, 3.11, 3.12 | Hoàn toàn tương thích |
| **Django Version** | Django 6.1.1 / DRF 3.18 | Hỗ trợ đầy đủ trong virtualenv | Hỗ trợ đầy đủ trong virtualenv | Hoàn toàn tương thích |
| **Tên miền (Domain)** | `<username>.pythonanywhere.com` | Miễn phí tên miền con con | Tên miền riêng (Custom domain) | Đạt chuẩn |
| **Dung lượng ổ đĩa (Disk)** | ~80 MB code + media | 512 MB | 1 GB | Đủ cho bản thử nghiệm & demo |
| **Cơ sở dữ liệu (Database)** | SQLite3 (`db.sqlite3`) | Lưu trữ bền vững trên ổ đĩa | SQLite3 hoặc MySQL tích hợp | File SQLite tồn tại vĩnh viễn, không mất khi reload server |
| **File tải lên & Bản quyền** | Public media + Protected media | Phục vụ tốt qua Nginx & Django View | Phục vụ tốt | Đảm bảo tách biệt file công khai và file bảo vệ |
| **Duy trì hoạt động** | 24/7 | Cần bấm nút gia hạn 3 tháng/lần | Chạy liên tục không cần gia hạn | Gói Free gửi email nhắc nhở trước khi hết hạn 3 tháng |
| **Mạng ra ngoài (Outbound)** | Tải ảnh từ thư mục nội bộ (curated) | Bị giới hạn whitelist (pip, github OK) | Mở toàn bộ Internet | ARTFAIR đã tải sẵn toàn bộ ảnh mẫu CC0 cục bộ, chạy mượt mà trên gói Free |

---

## II. Các bước triển khai chi tiết

### Bước 1: Đăng ký tài khoản PythonAnywhere
1. Truy cập [https://www.pythonanywhere.com/](https://www.pythonanywhere.com/) và chọn **Sign up**.
2. Chọn gói **Create a Beginner account** (Miễn phí).
3. Đặt **Username** (Lưu ý: Tên miền website của bạn sẽ là `https://<username>.pythonanywhere.com`, ví dụ đặt username là `artfairdemo` thì link sẽ là `https://artfairdemo.pythonanywhere.com`).
4. Nhập Email, mật khẩu và xác nhận email kích hoạt tài khoản.

---

### Bước 2: Đưa mã nguồn dự án lên PythonAnywhere
Có 2 cách đơn giản để đưa mã nguồn lên:

#### Cách A: Sử dụng Git (Khuyến nghị nếu bạn dùng GitHub)
1. Đẩy code từ máy lên kho riêng (Private repository) trên GitHub (lưu ý: `.gitignore` đã chặn file `.env` và `db.sqlite3`).
2. Trên PythonAnywhere Dashboard, bấm vào mục **Consoles** -> mở một **Bash console**.
3. Chạy lệnh clone:
   ```bash
   git clone https://github.com/<your-github-username>/ARTFAIR.git
   ```

#### Cách B: Nén và Upload trực tiếp từ máy tính (Không cần Git)
1. Trên máy tính của bạn, chọn thư mục dự án `C:\Users\Admin\Desktop\ARTFAIR\`.
2. Nén thành file `ARTFAIR.zip` (loại trừ thư mục `.venv`).
3. Mở tab **Files** trên PythonAnywhere Dashboard, tải file `ARTFAIR.zip` lên thư mục `/home/<username>/`.
4. Mở **Bash console** và giải nén:
   ```bash
   unzip ARTFAIR.zip -d ARTFAIR
   ```

---

### Bước 3: Tạo môi trường ảo (Virtualenv) với Python 3.12
Trong cửa sổ **Bash console** trên PythonAnywhere, chạy các lệnh sau:

```bash
# 1. Tạo virtualenv với Python 3.12
mkvirtualenv --python=/usr/bin/python3.12 artfair-venv

# 2. Chuyển vào thư mục backend và cài đặt thư viện
cd ~/ARTFAIR/artfair_backend
pip install -r requirements.txt
```

---

### Bước 4: Thiết lập file môi trường sản xuất (`.env`)
1. Tạo một khóa bí mật an toàn ngẫu nhiên bằng lệnh:
   ```bash
   python3 -c 'import secrets; print(secrets.token_urlsafe(50))'
   ```
2. Tạo file `.env` tại `~/ARTFAIR/artfair_backend/.env`:
   ```bash
   nano ~/ARTFAIR/artfair_backend/.env
   ```
3. Dán nội dung cấu hình sau (thay `<username>` bằng tên tài khoản PythonAnywhere của bạn và dán khóa bí mật vừa tạo):
   ```ini
   SECRET_KEY=paste-khoa-bi-mat-vua-tao-tai-day
   DEBUG=False
   ALLOWED_HOSTS=<username>.pythonanywhere.com,localhost,127.0.0.1
   CSRF_TRUSTED_ORIGINS=https://<username>.pythonanywhere.com
   SECURE_COOKIES=True
   MAX_UPLOAD_SIZE_MB=50
   MAX_PREVIEW_SIZE_MB=10
   ```
4. Nhấn `Ctrl + O` -> `Enter` để lưu, sau đó nhấn `Ctrl + X` để thoát nano.

---

### Bước 5: Chạy Migration và Thu gom Static Files
Vẫn trong **Bash console** (đang ở `~/ARTFAIR/artfair_backend` và đã kích hoạt `artfair-venv`):

```bash
# 1. Cập nhật cấu trúc database SQLite
python manage.py migrate

# 2. Thu gom toàn bộ CSS, JS, ảnh nghệ thuật mẫu vào thư mục staticfiles để Nginx phục vụ
python manage.py collectstatic --noinput

# 3. Tạo tài khoản quản trị Administrator (nhập username và password tương tác)
python manage.py createsuperuser

# 4. Gắn tài nguyên nghệ thuật mẫu cho các họa sĩ demo
python manage.py setup_demo_assets
```

---

### Bước 6: Cấu hình Web App trên tab "Web" của PythonAnywhere

1. Chuyển sang tab **Web** trên thanh điều hướng của PythonAnywhere Dashboard.
2. Bấm nút **Add a new web app** -> Chọn **Next** -> Chọn **Manual configuration (not Django)** -> Chọn **Python 3.12** -> **Next**.
3. Cuộn xuống cấu hình các mục sau:

#### A. Virtualenv
- Bấm vào đường dẫn **Virtualenv** và điền chính xác:
  ```text
  /home/<username>/.virtualenvs/artfair-venv
  ```

#### B. Code paths
- **Source code:** `/home/<username>/ARTFAIR/artfair_backend`
- **Working directory:** `/home/<username>/ARTFAIR/artfair_backend`

#### C. Cấu hình file WSGI (WSGI configuration file)
- Bấm vào link file WSGI: `/var/www/<username>_pythonanywhere_com_wsgi.py`.
- **Xóa toàn bộ nội dung mẫu có sẵn**, sau đó dán đoạn mã sau vào:

```python
import os
import sys
from dotenv import load_dotenv

# Đường dẫn dự án trên hosting
PA_USERNAME = '<username>'  # Thay bằng username của bạn
PROJECT_HOME = f'/home/{PA_USERNAME}/ARTFAIR'
BACKEND_DIR = f'{PROJECT_HOME}/artfair_backend'

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if PROJECT_HOME not in sys.path:
    sys.path.insert(1, PROJECT_HOME)

# Nạp biến môi trường
env_path = os.path.join(BACKEND_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```
- Bấm **Save** ở góc trên bên phải.

#### D. Cấu hình bảng Static Files (Tối ưu tốc độ tải trang qua Nginx)
Cuộn xuống mục **Static files** và thêm chính xác 2 dòng sau (bấm *Enter URL* và *Enter path*):

| URL | Directory Path | Chức năng |
| :--- | :--- | :--- |
| `/static/` | `/home/<username>/ARTFAIR/artfair_backend/staticfiles` | Phục vụ CSS, JavaScript, font chữ, icon và ảnh mẫu CC0 |
| `/media/` | `/home/<username>/ARTFAIR/artfair_backend/media` | Phục vụ ảnh xem thử (preview watermarked) và avatar |

> [!CAUTION]
> **Tuyệt đối KHÔNG cấu hình thư mục `/protected_media/` vào bảng Static files!**
> Thư mục `protected_media/` chứa file gốc có độ phân giải cao của tác phẩm. Nó chỉ được phép tải thông qua API Django sau khi người dùng đã thanh toán thành công và có quyền truy cập hợp lệ.

---

### Bước 7: Reload và Kiểm tra website trực tiếp

1. Cuộn lên đầu tab **Web**, bấm nút to màu xanh lá: **Reload <username>.pythonanywhere.com**.
2. Mở trình duyệt và truy cập:
   - **Trang chủ:** `https://<username>.pythonanywhere.com/`
   - **Trang Quản trị Admin:** `https://<username>.pythonanywhere.com/admin/`
3. Kiểm tra các chức năng:
   - Đăng ký tài khoản người mua và nghệ sĩ mới.
   - Thử nghiệm chức năng lưu tác phẩm yêu thích, đặt vẽ commission, vào Creator Studio.
   - Kiểm tra ảnh đại diện, banner Monet và Renoir hiển thị sắc nét.

---

## III. Bảo trì, Cập nhật & Xử lý sự cố

1. **Xem Log lỗi khi gặp sự cố:**
   - Tại tab **Web**, xem 3 file log:
     - `Error log`: Ghi nhận lỗi Python/Django (500 Internal Server Error).
     - `Server log`: Ghi nhận khởi động máy chủ WSGI.
     - `Access log`: Ghi nhận lượt truy cập của người dùng.
2. **Gia hạn gói Free (Beginner):**
   - Mỗi 3 tháng, đăng nhập vào PythonAnywhere và bấm nút **"Run until 3 months from today"** trên tab Web để duy trì website luôn hoạt động.
3. **Sao lưu dữ liệu định kỳ:**
   - Tại tab **Files**, bạn có thể tải về file `~/ARTFAIR/artfair_backend/db.sqlite3` về máy tính bất cứ lúc nào để lưu trữ dữ liệu an toàn.
