# ARTFAIR - Nền tảng Giao dịch Quyền sử dụng Tác phẩm Nghệ thuật & Commission

Dự án Django & Django REST Framework cung cấp giao diện Web Gallery kết nối trực tiếp với hệ thống backend quản lý tài khoản, hồ sơ nghệ sĩ (Creator), danh mục, tags, tác phẩm và đa tầng gói quyền sử dụng (PERSONAL / COMMERCIAL) với cơ chế đóng watermark tự động, kho lưu trữ tệp gốc an toàn và hệ thống xuất chứng nhận bản quyền PDF tiếng Việt.

---

## 1. Công nghệ sử dụng
- **Python**: 3.12+
- **Django**: 6.1 (LTS/Stable) - phục vụ cả Web Templates & REST API trên cùng 1 server.
- **Django REST Framework**: 3.18
- **Django Filter**: 26.1
- **Pillow**: 12.3 (Xử lý hình ảnh, thu nhỏ độ phân giải và đóng watermark tự động)
- **ReportLab**: 5.0 (Sinh file chứng nhận bản quyền PDF chuẩn typography tiếng Việt)
- **Frontend**: Django Templates, HTML5 Semantic, CSS3 Custom Properties (Palette Hồng phấn - Lavender - Berry pink theo thiết kế mẫu), Vanilla JavaScript kết nối REST API.
- **Database**: SQLite (Phù hợp giai đoạn phát triển).
- **Xác thực**: Django Session Authentication kết hợp cơ chế chống giả mạo CSRF (`X-CSRFToken`).

---

## 2. Cấu trúc thư mục dự án (Kiến trúc phân tách Backend & Frontend)

Hệ thống đã được tổ chức tách biệt giữa mã nguồn Backend và mã nguồn Giao diện Frontend:

```text
ARTFAIR/
├── artfair_backend/                    # MÃ NGUỒN BACKEND VÀ CẤU HÌNH HỆ THỐNG
│   ├── .venv/                          # Môi trường ảo Python
│   ├── accounts/                       # Ứng dụng quản lý tài khoản, phân quyền & hồ sơ nghệ sĩ
│   │   ├── migrations/                 # Migration User & ArtistProfile
│   │   ├── models.py                   # User (Buyer/Creator) & ArtistProfile
│   │   ├── serializers.py              # Serializer đăng ký, đăng nhập, hồ sơ
│   │   ├── permissions.py              # IsCreator, IsOwnerOrReadOnly
│   │   ├── views.py                    # API Auth, Me, ArtistProfile, Public profile
│   │   ├── signals.py                  # Tự động tạo ArtistProfile cho Creator
│   │   ├── urls.py                     # Định tuyến /api/accounts/
│   │   ├── admin.py                    # Quản trị User & ArtistProfile trong Django Admin
│   │   └── tests.py                    # Test suite tài khoản, phân quyền, bảo mật mật khẩu
│   ├── artworks/                       # Ứng dụng quản lý tác phẩm, bản quyền, đơn hàng & rút tiền
│   │   ├── management/commands/
│   │   │   └── seed_demo.py            # Command khởi tạo dữ liệu mẫu (idempotent)
│   │   ├── migrations/                 # Migration Category, Tag, Artwork, ArtworkFile, LicenseOption, Order, Withdrawal
│   │   ├── models.py                   # Artwork, Category, Tag, ArtworkFile, LicenseOption, Order, Withdrawal
│   │   ├── filters.py                  # Lọc theo danh mục, nghệ sĩ, loại quyền, khoảng giá
│   │   ├── utils.py                    # Đóng watermark Pillow, xuất chứng nhận PDF tiếng Việt, kiểm tra file
│   │   ├── serializers.py              # Serializer tác phẩm, tệp gốc, gói quyền, thư viện tranh, rút tiền
│   │   ├── views.py                    # API catalog, studio, download tệp gốc, checkout, thư viện, rút tiền
│   │   ├── urls.py                     # Định tuyến /api/artworks/
│   │   ├── admin.py                    # Quản trị tác phẩm, đơn hàng & yêu cầu rút tiền trong Django Admin
│   │   └── tests.py                    # Test suite toàn diện (44 bài test kiểm tra 100% tính năng)
│   ├── config/                         # Cấu hình trung tâm dự án Django
│   │   ├── settings.py                 # Cấu hình bảo mật, DB, Media, DRF, trỏ TEMPLATES & STATIC sang frontend/
│   │   ├── urls.py                     # Root URL: '/' (Trang chủ), '/artworks/<slug>/', '/studio/', '/dashboard/', '/api/'
│   │   ├── views.py                    # Template Views: home, detail, studio, dashboard & api_root_overview
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── media/                          # Thư mục chứa ảnh công khai (preview đã đóng watermark, avatar)
│   │   └── previews/
│   ├── protected_media/                # KHO LƯU TỆP GỐC BÀN GIAO (BẢO MẬT, RIÊNG TƯ, CHỈ TẢI SAU KHI MUA)
│   │   └── original_files/
│   ├── templates/                      # [BẢN DỰ PHÒNG CŨ] Không sửa bản này, chỉnh sửa tại frontend/templates/
│   ├── static/                         # [BẢN DỰ PHÒNG CŨ] Không sửa bản này, chỉnh sửa tại frontend/static/
│   ├── .env                            # Biến môi trường cục bộ (SECRET_KEY, DEBUG, ALLOWED_HOSTS, CSRF)
│   ├── .env.example                    # Mẫu cấu hình môi trường
│   ├── .gitignore                      # Bỏ qua tệp nhạy cảm, database, .venv, media
│   ├── db.sqlite3                      # SQLite database
│   ├── manage.py                       # Django CLI
│   ├── requirements.txt                # Danh sách thư viện và phiên bản chính xác
│   └── README.md                       # Tài liệu hướng dẫn sử dụng
│
└── frontend/                           # MÃ NGUỒN GIAO DIỆN CHÍNH (ĐƯỢC DJANGO ƯU TIÊN SỬ DỤNG)
    ├── templates/                      # Toàn bộ mã nguồn giao diện HTML Django Templates
    │   ├── base.html                   # Khung chung, Navbar, Auth Modal, Toast, Footer
    │   ├── home.html                   # Màn hình 01: Trang chủ & Khám phá tác phẩm
    │   ├── artwork_detail.html         # Màn hình 02: Chi tiết tác phẩm, chọn gói quyền & thanh toán mô phỏng
    │   ├── studio.html                 # Màn hình 03: Creator Studio & Wizard đăng bán 3 bước
    │   ├── studio_forbidden.html       # Màn hình thông báo chặn quyền 403 khi Buyer/Khách truy cập Studio
    │   └── dashboard.html              # Màn hình 04: Quản lý cá nhân, Kho tranh, Đơn hàng, Dashboard doanh thu & Rút tiền
    └── static/                         # Toàn bộ tài nguyên tĩnh Web
        ├── css/
        │   └── artfair.css             # Toàn bộ CSS chuẩn thiết kế (Palette Hồng - Lavender, Responsive)
        ├── js/
        │   └── artfair.js              # Bộ điều khiển JS: Session auth, CSRF, filters, modal, wizard, checkout, dashboard
        └── images/
            └── hero_decor.svg          # Minh họa hoa nghệ thuật trang trí Hero banner
```

---

## 3. Quy tắc chỉnh sửa mã nguồn
- **Khi chỉnh sửa giao diện HTML/CSS/JS**: Thực hiện trực tiếp trong thư mục `frontend/` (`frontend/templates/` và `frontend/static/`). Django đã được cấu hình trỏ trực tiếp đến đây và cập nhật ngay khi lưu tệp.
- **Khi chỉnh sửa backend**: Thực hiện trong thư mục `artfair_backend/` (các models, views, serializers, urls, permissions).
- **Bản cũ trong `artfair_backend/templates/` và `artfair_backend/static/`**: Được giữ lại làm bản dự phòng an toàn, **không tiếp tục chỉnh sửa bản cũ này**.

---

## 4. Hướng dẫn chạy server trên Windows

### A. Chạy bằng Command Prompt (CMD)
```cmd
REM 1. Di chuyển vào thư mục backend
cd C:\Users\Admin\Desktop\ARTFAIR\artfair_backend

REM 2. Kích hoạt môi trường ảo
.venv\Scripts\activate.bat

REM 3. Chạy kiểm thử tự động (44 tests)
python manage.py test

REM 4. Khởi chạy máy chủ
python manage.py runserver
```

*Hoặc chạy trực tiếp bằng 1 lệnh:*
```cmd
C:\Users\Admin\Desktop\ARTFAIR\artfair_backend\.venv\Scripts\python.exe C:\Users\Admin\Desktop\ARTFAIR\artfair_backend\manage.py runserver
```

### B. Chạy bằng PowerShell
```powershell
# 1. Di chuyển vào thư mục backend
cd C:\Users\Admin\Desktop\ARTFAIR\artfair_backend

# 2. Kích hoạt môi trường ảo
.venv\Scripts\Activate.ps1

# 3. Chạy kiểm thử tự động (44 tests)
python manage.py test

# 4. Khởi chạy máy chủ
python manage.py runserver
```

**Địa chỉ truy cập trên trình duyệt:**
- **Trang chủ & Khám phá**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Chi tiết tác phẩm**: [http://127.0.0.1:8000/artworks/chien-ham-khong-gian-lac-hong/](http://127.0.0.1:8000/artworks/chien-ham-khong-gian-lac-hong/)
- **Creator Studio**: [http://127.0.0.1:8000/studio/](http://127.0.0.1:8000/studio/)
- **Khu vực cá nhân & Dashboard**: [http://127.0.0.1:8000/dashboard/](http://127.0.0.1:8000/dashboard/)
- **API Overview (JSON)**: [http://127.0.0.1:8000/api/](http://127.0.0.1:8000/api/)
- **Django Admin**: [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

## 5. Tài khoản quản trị & Dữ liệu mẫu (Demo Accounts)

| Loại tài khoản | Username | Mật khẩu | Quyền hạn & Chức năng |
| :--- | :--- | :--- | :--- |
| **Quản trị viên (Admin)** | `admin` | `Admin@123456` | Toàn quyền Django Admin, xem & tải mọi tệp gốc |
| **Nghệ sĩ 1 (Creator)** | `creator_an` | `Creator@123456` | Có ArtistProfile, quản lý tranh trên Studio, xem Dashboard doanh thu & Rút tiền mô phỏng |
| **Nghệ sĩ 2 (Creator)** | `creator_binh` | `Creator@123456` | Có ArtistProfile, quản lý tranh trên Studio, xem Dashboard doanh thu |
| **Người mua (Buyer)** | `buyer_chi` | `Buyer@123456` | Mua quyền sử dụng, truy cập Kho tác phẩm đã mua, Tải tệp gốc, Xuất chứng nhận PDF |

---

## 6. Danh sách API Endpoints

### A. Giao diện Web Templates
- `GET /`: Màn hình 01 - Trang chủ & Khám phá tác phẩm.
- `GET /artworks/<slug>/`: Màn hình 02 - Chi tiết tác phẩm, chọn quyền PERSONAL/COMMERCIAL & thanh toán.
- `GET /studio/`: Màn hình 03 - Creator Studio (Chặn Buyer/Guest, cấp phép Creator).
- `GET /dashboard/`: Màn hình 04 - Quản lý cá nhân, Kho tác phẩm, Đơn hàng, Dashboard doanh thu & Rút tiền.

### B. Xác thực & Hồ sơ (`/api/accounts/`)
- `GET /api/accounts/auth/csrf/`: Lấy CSRF token và thiết lập cookie CSRF.
- `POST /api/accounts/auth/register/`: Đăng ký tài khoản (hỗ trợ chọn Buyer hoặc Creator).
- `POST /api/accounts/auth/login/`: Đăng nhập session.
- `POST /api/accounts/auth/logout/`: Đăng xuất session.
- `GET, PATCH /api/accounts/me/`: Xem và cập nhật hồ sơ cá nhân (first_name, last_name, email).
- `GET, PATCH /api/accounts/artist-profile/`: Creator xem/sửa hồ sơ nghệ sĩ (display_name, bio, avatar, cover_image, is_accepting_commissions).
- `GET /api/accounts/artists/<username>/`: Xem hồ sơ nghệ sĩ công khai.

### C. Khám phá, Thư viện & Chứng nhận (`/api/artworks/`)
- `GET /api/artworks/categories/`: Danh mục nghệ thuật.
- `GET /api/artworks/tags/`: Danh sách thẻ.
- `GET /api/artworks/`: Danh sách tác phẩm đã phát hành kèm bộ lọc, tìm kiếm, phân trang.
- `GET /api/artworks/<lookup>/`: Chi tiết tác phẩm công khai.
- `GET /api/artworks/<id>/download-file/`: Tải tệp bàn giao gốc (Chủ sở hữu, Admin hoặc Buyer đã thanh toán thành công).
- `GET /api/artworks/library/my-library/`: Danh sách tác phẩm trong kho bản quyền của Buyer hiện tại (kèm liên kết tải tệp và xuất PDF).
- `GET /api/artworks/orders/<order_code>/certificate/`: Xuất tệp PDF chứng nhận quyền sử dụng tác phẩm tiếng Việt có mã chứng nhận duy nhất.

### D. Đơn hàng & Thanh toán mô phỏng (`/api/artworks/orders/`)
- `POST /api/artworks/orders/`: Khởi tạo đơn mua quyền sử dụng (`artwork_id`, `license_type`).
- `GET /api/artworks/orders/my-orders/`: Danh sách đơn mua của người dùng hiện tại (kèm tiến độ 3 bước: Tạo đơn -> Thanh toán -> Cấp quyền).
- `GET /api/artworks/orders/<order_code>/`: Chi tiết đơn hàng.
- `POST /api/artworks/orders/<order_code>/simulate-payment/`: Cổng thanh toán mô phỏng Sandbox (SUCCESS / FAILED / CANCEL).

### E. Creator Studio & Rút tiền (`/api/artworks/my-artworks/` & `/api/artworks/creator/`)
- `GET, POST /api/artworks/my-artworks/`: Danh sách tác phẩm của Creator và tạo tác phẩm mới.
- `POST /api/artworks/my-artworks/publish-wizard/`: Wizard 3 bước đăng bán tác phẩm (tải tệp gốc, đóng watermark, kiểm tra lỗi, định giá).
- `POST /api/artworks/my-artworks/<id>/edit-wizard/`: Chỉnh sửa tác phẩm (bảo lưu giá lịch sử các đơn cũ).
- `POST /api/artworks/my-artworks/<id>/publish/`: Phát hành tác phẩm.
- `POST /api/artworks/my-artworks/<id>/archive/`: Lưu trữ tác phẩm.
- `GET /api/artworks/creator/dashboard-metrics/`: Thống kê doanh thu, số dư khả dụng, biểu đồ xu hướng tuần và sổ giao dịch bán tranh của Creator.
- `POST /api/artworks/creator/withdrawals/`: Tạo yêu cầu rút tiền mô phỏng (kiểm tra nguyên tử số dư > 0 và <= số dư khả dụng, không cho số dư âm).

---

## 7. Quy tắc nghiệp vụ tài chính & Chứng nhận Màn hình 4

1. **Phí nền tảng:** Giai đoạn phát triển này tạm tính **0%** (100% số tiền đơn mua thành công được ghi nhận vào doanh thu và số dư của nghệ sĩ sáng tác).
2. **Ghi nhận doanh thu:** Chỉ những đơn hàng có trạng thái `COMPLETED` mới được ghi nhận doanh thu. Các đơn `PENDING`, `FAILED` hoặc `CANCELLED` tuyệt đối không ghi nhận doanh thu và không cấp quyền tải file hay xuất chứng nhận.
3. **Số dư khả dụng & Rút tiền mô phỏng:** 
   - `Số dư khả dụng = Tổng doanh thu đơn thành công - Tổng số tiền đã rút`.
   - Giao dịch rút tiền là mô phỏng trong môi trường Sandbox, không yêu cầu thẻ hay số tài khoản ngân hàng thật.
   - Thao tác rút tiền được bọc trong giao dịch cơ sở dữ liệu nguyên tử (`transaction.atomic()`), ngăn chặn rút quá số dư hoặc tạo số dư âm.
4. **Chứng nhận PDF bản quyền:**
   - Hỗ trợ đầy đủ tiếng Việt có dấu qua font chữ hệ thống TrueType.
   - Mỗi đơn hàng thành công được gắn với một mã chứng nhận xác thực duy nhất: `CERT-{order_code}`. Việc xuất lại nhiều lần sẽ giữ nguyên định danh chứng nhận.
   - Văn bản pháp lý khẳng định rõ: **Quyền được cấp là quyền không độc quyền (Non-exclusive License)**; **Bản quyền tác giả gốc vẫn thuộc về Nghệ sĩ sáng tác**; Không cấu thành việc chuyển nhượng toàn bộ bản quyền tác giả.
5. **Bảo toàn kho bản quyền khi tác phẩm ngừng bán:** Người mua đã thanh toán thành công vẫn giữ nguyên vĩnh viễn quyền truy cập kho tranh, quyền tải tệp gốc và quyền xuất PDF chứng nhận ngay cả khi tác giả lưu trữ hoặc ngừng phát hành tác phẩm trên sàn.
