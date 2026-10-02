import os
import io
import math
from pathlib import Path
from decimal import Decimal
from PIL import Image, ImageDraw, ImageFont
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.conf import settings

ALLOWED_ORIGINAL_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.webp', '.tiff', '.tif', '.bmp',
    '.psd', '.ai', '.eps', '.svg', '.zip', '.rar', '.7z'
}

RASTER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.tiff', '.tif', '.bmp'}

ALLOWED_PREVIEW_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}


def validate_file_size(file_obj, max_mb=None, label="tệp"):
    """
    Validate that uploaded file does not exceed size limit in MB.
    """
    if max_mb is None:
        max_mb = settings.MAX_UPLOAD_SIZE_MB
    max_bytes = max_mb * 1024 * 1024
    if file_obj.size > max_bytes:
        raise ValidationError(f"Dung lượng {label} vượt quá giới hạn cho phép ({max_mb} MB).")


def validate_file_extension(filename, allowed_extensions):
    """
    Validate file extension against an allowed set.
    """
    ext = Path(filename).suffix.lower()
    if ext not in allowed_extensions:
        allowed_str = ", ".join(sorted(allowed_extensions))
        raise ValidationError(f"Định dạng tệp '{ext}' không được hỗ trợ. Các định dạng cho phép: {allowed_str}")
    return ext


def extract_metadata_and_inspect(file_obj):
    """
    Inspects an uploaded file.
    Returns:
        dict: {
            'format': str,
            'size': int,
            'width': int or None,
            'height': int or None,
            'dpi': int or None,
            'color_mode': str,
            'is_raster': bool,
            'can_generate_preview': bool,
        }
    """
    file_name = file_obj.name
    ext = Path(file_name).suffix.lower()
    size = file_obj.size

    metadata = {
        'format': ext.lstrip('.').upper() or 'UNKNOWN',
        'size': size,
        'width': None,
        'height': None,
        'dpi': None,
        'color_mode': '',
        'is_raster': False,
        'can_generate_preview': False,
    }

    if ext in RASTER_EXTENSIONS:
        try:
            file_obj.seek(0)
            with Image.open(file_obj) as img:
                metadata['format'] = (img.format or ext.lstrip('.')).upper()
                metadata['width'] = img.width
                metadata['height'] = img.height
                metadata['color_mode'] = img.mode
                metadata['is_raster'] = True
                metadata['can_generate_preview'] = True

                # Extract DPI safely (raster only)
                dpi_info = img.info.get('dpi')
                if dpi_info:
                    if isinstance(dpi_info, (tuple, list)) and len(dpi_info) > 0:
                        try:
                            metadata['dpi'] = int(round(dpi_info[0]))
                        except (TypeError, ValueError):
                            metadata['dpi'] = None
                    elif isinstance(dpi_info, (int, float)):
                        metadata['dpi'] = int(round(dpi_info))
        except Exception:
            metadata['can_generate_preview'] = False
        finally:
            file_obj.seek(0)
    else:
        # Non-raster files: vector (SVG, AI, EPS) or PSD or archives
        metadata['is_raster'] = False
        metadata['can_generate_preview'] = False

    return metadata


def generate_watermarked_preview(source_image_file, max_dimension=1200, watermark_text="ARTFAIR  PREVIEW"):
    """
    Creates a reduced-resolution preview with an embedded semi-transparent watermark.
    Returns a ContentFile (JPEG format) ready to be saved to Artwork.preview_image.
    """
    source_image_file.seek(0)
    with Image.open(source_image_file) as img:
        # Convert image to RGBA for watermark manipulation
        rgba_img = img.convert('RGBA')

        # 1. Resize if dimension exceeds max_dimension
        orig_w, orig_h = rgba_img.size
        max_side = max(orig_w, orig_h)
        if max_side > max_dimension:
            scale = max_dimension / float(max_side)
            new_w = max(1, int(round(orig_w * scale)))
            new_h = max(1, int(round(orig_h * scale)))
            rgba_img = rgba_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        width, height = rgba_img.size

        # 2. Create watermark transparent overlay
        watermark_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark_layer)

        # Approximate font sizing based on image dimensions
        font_size = max(20, int(min(width, height) / 14))
        try:
            # Fallback to load_default if truetype not available
            font = ImageFont.load_default(size=font_size)
        except TypeError:
            font = ImageFont.load_default()

        # 3. Create a rotated watermark pattern across the image
        # Watermark text with semi-transparent white/gray stroke
        watermark_patch_size = (int(font_size * len(watermark_text) * 0.75), font_size * 3)
        patch = Image.new('RGBA', watermark_patch_size, (0, 0, 0, 0))
        patch_draw = ImageDraw.Draw(patch)

        # Draw semi-transparent watermark with subtle dark shadow for contrast
        text_color = (255, 255, 255, 110)
        shadow_color = (0, 0, 0, 90)

        # Draw diagonal text on patch
        patch_draw.text((2, 2), watermark_text, fill=shadow_color, font=font)
        patch_draw.text((0, 0), watermark_text, fill=text_color, font=font)

        # Rotate patch by 35 degrees
        rotated_patch = patch.rotate(35, expand=True, resample=Image.Resampling.BICUBIC)
        pw, ph = rotated_patch.size

        # Tile rotated patches across the image
        step_x = max(pw + 80, 200)
        step_y = max(ph + 80, 160)

        for y in range(-ph, height + ph, step_y):
            for x in range(-pw, width + pw, step_x):
                watermark_layer.alpha_composite(rotated_patch, (x, y))

        # 4. Composite watermark overlay onto the resized base image
        final_img = Image.alpha_composite(rgba_img, watermark_layer)

        # 5. Convert to RGB for JPEG output
        rgb_img = final_img.convert('RGB')
        output = io.BytesIO()
        rgb_img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)

        source_name = getattr(source_image_file, 'name', 'preview.jpg')
        stem = Path(source_name).stem
        preview_filename = f"{stem}_preview.jpg"

        return ContentFile(output.getvalue(), name=preview_filename)


def generate_license_certificate_pdf(order):
    """
    Generates an official Digital License Certificate PDF for an artwork purchase.
    Supports Vietnamese unicode characters using system TrueType fonts.
    Ensures non-exclusive license declaration and simulated payment notice.
    """
    import io
    import os
    from textwrap import wrap
    from django.utils import timezone
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Register Vietnamese TrueType fonts if available
    regular_font = 'Helvetica'
    bold_font = 'Helvetica-Bold'
    italic_font = 'Helvetica-Oblique'

    for f_name, f_file in [('Arial', 'arial.ttf'), ('Arial-Bold', 'arialbd.ttf'), ('Arial-Italic', 'ariali.ttf')]:
        win_path = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', f_file)
        if os.path.exists(win_path):
            try:
                pdfmetrics.registerFont(TTFont(f_name, win_path))
                if f_name == 'Arial':
                    regular_font = 'Arial'
                elif f_name == 'Arial-Bold':
                    bold_font = 'Arial-Bold'
                elif f_name == 'Arial-Italic':
                    italic_font = 'Arial-Italic'
            except Exception:
                pass

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # 1. Outer & Inner Decorative Borders
    c.setStrokeColor(colors.HexColor('#C52A70'))  # Berry pink
    c.setLineWidth(3.0)
    c.rect(28, 28, width - 56, height - 56)

    c.setStrokeColor(colors.HexColor('#8A2BE2'))  # Purple / Lavender
    c.setLineWidth(1.0)
    c.rect(34, 34, width - 68, height - 68)

    # Corner decorations
    c.setStrokeColor(colors.HexColor('#F472B6'))
    c.setLineWidth(0.5)
    c.rect(38, 38, width - 76, height - 76)

    # 2. Header
    c.setFont(bold_font, 11)
    c.setFillColor(colors.HexColor('#C52A70'))
    c.drawCentredString(width / 2.0, height - 65, "NỀN TẢNG BẢN QUYỀN NGHỆ THUẬT SỐ ARTFAIR")

    c.setFont(bold_font, 20)
    c.setFillColor(colors.HexColor('#2E124D'))  # Deep plum
    c.drawCentredString(width / 2.0, height - 92, "CHỨNG NHẬN QUYỀN SỬ DỤNG TÁC PHẨM")

    c.setFont(italic_font, 10)
    c.setFillColor(colors.HexColor('#6B7280'))
    c.drawCentredString(width / 2.0, height - 110, "DIGITAL ARTWORK LICENSE CERTIFICATE")

    # Separator Line
    c.setStrokeColor(colors.HexColor('#E5E7EB'))
    c.setLineWidth(1)
    c.line(55, height - 122, width - 55, height - 122)

    # 3. Certificate ID & Date Bar
    cert_code = f"CERT-{order.order_code}"
    issue_date = (order.completed_at or order.created_at or timezone.now()).strftime('%d/%m/%Y %H:%M:%S')

    c.setFillColor(colors.HexColor('#FAF5FF'))  # Soft lavender background box
    c.rect(55, height - 165, width - 110, 32, fill=True, stroke=False)

    c.setFont(bold_font, 9)
    c.setFillColor(colors.HexColor('#5B21B6'))
    c.drawString(70, height - 152, f"Mã chứng nhận: {cert_code}")
    c.drawRightString(width - 70, height - 152, f"Ngày cấp: {issue_date}")

    # 4. Details Table Box
    box_top = height - 185
    box_bottom = height - 425
    c.setStrokeColor(colors.HexColor('#E2D4EC'))
    c.setLineWidth(1)
    c.setFillColor(colors.HexColor('#FFFFFF'))
    c.roundRect(55, box_bottom, width - 110, box_top - box_bottom, radius=6, fill=True, stroke=True)

    # Artist and Buyer names
    creator = order.artwork.creator
    artist_name = creator.username
    if hasattr(creator, 'artist_profile') and creator.artist_profile and creator.artist_profile.display_name:
        artist_name = f"{creator.artist_profile.display_name} (@{creator.username})"

    buyer = order.buyer
    buyer_display = buyer.get_full_name() or buyer.username
    if buyer.email:
        buyer_display += f" ({buyer.email})"

    fields = [
        ("Tác phẩm nghệ thuật:", order.artwork.title),
        ("Nghệ sĩ sáng tác (Licensor):", artist_name),
        ("Bên nhận quyền (Licensee):", buyer_display),
        ("Gói quyền sử dụng:", f"{order.get_license_type_display()} ({order.license_type})"),
        ("Giá trị thanh toán ghi nhận:", f"{int(order.price_paid):,} VND (Mô phỏng - Sandbox)"),
        ("Mã đơn hàng liên kết:", order.order_code),
        ("Hình thức cấp phép:", "Quyền sử dụng không độc quyền (Non-exclusive License)"),
    ]

    curr_y = box_top - 24
    for label, val in fields:
        c.setFont(bold_font, 9)
        c.setFillColor(colors.HexColor('#4A2870'))
        c.drawString(72, curr_y, label)

        c.setFont(regular_font, 9)
        c.setFillColor(colors.HexColor('#1F2937'))
        val_str = str(val)
        if len(val_str) > 55:
            val_str = val_str[:52] + "..."
        c.drawString(245, curr_y, val_str)

        curr_y -= 26

    # 5. Terms Snapshot Box
    terms_box_top = box_bottom - 15
    terms_box_h = 135
    c.setStrokeColor(colors.HexColor('#E2D4EC'))
    c.setFillColor(colors.HexColor('#FFFDF9'))  # Warm subtle tint
    c.roundRect(55, terms_box_top - terms_box_h, width - 110, terms_box_h, radius=6, fill=True, stroke=True)

    c.setFont(bold_font, 9)
    c.setFillColor(colors.HexColor('#9D174D'))
    c.drawString(72, terms_box_top - 20, "ĐIỀU KHOẢN ÁP DỤNG TẠI THỜI ĐIỂM GIAO DỊCH:")

    terms_text = order.terms_snapshot or "Người mua được phép sử dụng tác phẩm theo tiêu chuẩn gói quyền đã thỏa thuận. Nghiêm cấm bán lại tệp gốc hoặc phân phối quyền thứ cấp."
    wrapped_lines = wrap(terms_text, width=78)

    c.setFont(regular_font, 8.5)
    c.setFillColor(colors.HexColor('#374151'))
    ty = terms_box_top - 38
    for line in wrapped_lines[:6]:
        c.drawString(72, ty, line)
        ty -= 15

    # 6. Legal Notice Box
    legal_y = terms_box_top - terms_box_h - 18
    c.setFont(bold_font, 8.5)
    c.setFillColor(colors.HexColor('#C52A70'))
    c.drawString(55, legal_y, "TUYÊN BỐ PHÁP LÝ & BẢO LƯU BẢN QUYỀN:")

    legal_clauses = [
        "1. Quyền sử dụng được cấp là KHÔNG ĐỘC QUYỀN. Tác phẩm có thể được cấp quyền cho nhiều bên hợp lệ khác nhau.",
        "2. Toàn bộ Bản quyền tác giả (Copyright) và quyền sở hữu trí tuệ gốc vẫn thuộc về Nghệ sĩ sáng tác.",
        "3. Chứng nhận này KHÔNG cấu thành hoặc tuyên bố việc chuyển nhượng toàn bộ bản quyền tác giả.",
        "4. Giao dịch được thực hiện và kiểm thử qua cổng thanh toán mô phỏng ARTFAIR Sandbox, không phát sinh dòng tiền thật.",
    ]

    c.setFont(regular_font, 7.8)
    c.setFillColor(colors.HexColor('#4B5563'))
    ly = legal_y - 15
    for clause in legal_clauses:
        c.drawString(55, ly, clause)
        ly -= 14

    # 7. Signature & Platform Stamp
    stamp_y = ly - 10
    c.setStrokeColor(colors.HexColor('#E5E7EB'))
    c.line(55, stamp_y, width - 55, stamp_y)

    c.setFont(bold_font, 8.5)
    c.setFillColor(colors.HexColor('#2E124D'))
    c.drawString(70, stamp_y - 20, "XÁC NHẬN BỞI HỆ THỐNG ARTFAIR")
    c.setFont(italic_font, 8)
    c.setFillColor(colors.HexColor('#6B7280'))
    c.drawString(70, stamp_y - 34, "Hệ thống xác thực điện tử tự động")

    c.setFont(bold_font, 8.5)
    c.setFillColor(colors.HexColor('#C52A70'))
    c.drawRightString(width - 70, stamp_y - 20, "TRẠNG THÁI: HỢP LỆ")
    c.setFont(regular_font, 8)
    c.setFillColor(colors.HexColor('#6B7280'))
    c.drawRightString(width - 70, stamp_y - 34, "Verified Digital License")

    # Bottom watermark/footer
    c.setFont(regular_font, 7)
    c.setFillColor(colors.HexColor('#9CA3AF'))
    c.drawCentredString(width / 2.0, 42, f"Chứng nhận điện tử ARTFAIR • https://artfair.vn • Mã xác thực: {cert_code}")

    c.save()
    return buffer.getvalue()


def _register_vietnamese_fonts():
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return 'Helvetica', 'Helvetica-Bold', 'Helvetica-Oblique'

    regular_font = 'Helvetica'
    bold_font = 'Helvetica-Bold'
    italic_font = 'Helvetica-Oblique'

    for f_name, f_file in [('Arial', 'arial.ttf'), ('Arial-Bold', 'arialbd.ttf'), ('Arial-Italic', 'ariali.ttf')]:
        win_path = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', f_file)
        if os.path.exists(win_path):
            try:
                pdfmetrics.registerFont(TTFont(f_name, win_path))
                if f_name == 'Arial':
                    regular_font = 'Arial'
                elif f_name == 'Arial-Bold':
                    bold_font = 'Arial-Bold'
                elif f_name == 'Arial-Italic':
                    italic_font = 'Arial-Italic'
            except Exception:
                pass

    return regular_font, bold_font, italic_font


def generate_commission_certificate_pdf(commission):
    """
    Generates a formal License & Delivery Certificate PDF for a COMPLETED Commission.
    Reuses the UTF-8 ReportLab canvas generator with blush & plum aesthetics.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        raise RuntimeError("ReportLab thư viện chưa được cài đặt.")

    from textwrap import wrap
    from django.utils import timezone

    regular_font, bold_font, italic_font = _register_vietnamese_fonts()

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4  # 595.27 x 841.89 points

    # 1. Background & Border
    c.setStrokeColor(colors.HexColor('#C52A70'))
    c.setLineWidth(2)
    c.rect(28, 28, width - 56, height - 56)

    c.setStrokeColor(colors.HexColor('#F3D9E2'))
    c.setLineWidth(0.8)
    c.rect(34, 34, width - 68, height - 68)

    # 2. Header
    c.setFont(bold_font, 18)
    c.setFillColor(colors.HexColor('#C52A70'))
    c.drawCentredString(width / 2.0, height - 68, "ARTFAIR PLATFORM")

    c.setFont(bold_font, 13)
    c.setFillColor(colors.HexColor('#2E124D'))
    c.drawCentredString(width / 2.0, height - 90, "CHỨNG NHẬN BÀN GIAO & QUYỀN SỬ DỤNG COMMISSION")

    c.setFont(italic_font, 9.5)
    c.setFillColor(colors.HexColor('#6B7280'))
    c.drawCentredString(width / 2.0, height - 108, "CUSTOM COMMISSION LICENSE & DELIVERY CERTIFICATE")

    # Separator Line
    c.setStrokeColor(colors.HexColor('#E5E7EB'))
    c.setLineWidth(1)
    c.line(55, height - 120, width - 55, height - 120)

    # 3. Certificate Code Bar
    cert_code = f"CERT-{commission.commission_code}"
    issue_date = (commission.completed_at or commission.paid_at or timezone.now()).strftime('%d/%m/%Y %H:%M:%S')

    c.setFillColor(colors.HexColor('#FAF5FF'))
    c.rect(55, height - 162, width - 110, 32, fill=True, stroke=False)

    c.setFont(bold_font, 9)
    c.setFillColor(colors.HexColor('#5B21B6'))
    c.drawString(70, height - 150, f"Mã chứng nhận: {cert_code}")
    c.drawRightString(width - 70, height - 150, f"Ngày nghiệm thu: {issue_date}")

    # 4. Details Box
    box_top = height - 180
    box_bottom = height - 425
    c.setStrokeColor(colors.HexColor('#E2D4EC'))
    c.setLineWidth(1)
    c.setFillColor(colors.HexColor('#FFFFFF'))
    c.roundRect(55, box_bottom, width - 110, box_top - box_bottom, radius=6, fill=True, stroke=True)

    creator = commission.creator
    artist_name = creator.username
    if hasattr(creator, 'artist_profile') and creator.artist_profile and creator.artist_profile.display_name:
        artist_name = f"{creator.artist_profile.display_name} (@{creator.username})"

    buyer = commission.buyer
    buyer_display = buyer.get_full_name() or buyer.username
    if buyer.email:
        buyer_display += f" ({buyer.email})"

    agreed_price_str = f"{int(commission.agreed_price or commission.budget):,} VND (Thanh toán mô phỏng)"

    fields = [
        ("Tên dự án Commission:", commission.title),
        ("Nghệ sĩ thực hiện (Creator):", artist_name),
        ("Bên đặt vẽ (Buyer/Licensee):", buyer_display),
        ("Gói quyền sử dụng thỏa thuận:", f"{commission.get_license_type_display()} ({commission.license_type})"),
        ("Giá trị thỏa thuận nghiệm thu:", agreed_price_str),
        ("Mã đơn đặt vẽ liên kết:", commission.commission_code),
        ("Trạng thái giao dịch:", "Đã hoàn tất & Nghiệm thu (Completed & Released)"),
    ]

    curr_y = box_top - 24
    for label, val in fields:
        c.setFont(bold_font, 9)
        c.setFillColor(colors.HexColor('#4A2870'))
        c.drawString(72, curr_y, label)

        c.setFont(regular_font, 9)
        c.setFillColor(colors.HexColor('#1F2937'))
        val_str = str(val)
        if len(val_str) > 55:
            val_str = val_str[:52] + "..."
        c.drawString(255, curr_y, val_str)

        curr_y -= 26

    # 5. Agreed Terms & Scope Box
    terms_box_top = box_bottom - 15
    terms_box_h = 135
    c.setStrokeColor(colors.HexColor('#E2D4EC'))
    c.setFillColor(colors.HexColor('#FFFDF9'))
    c.roundRect(55, terms_box_top - terms_box_h, width - 110, terms_box_h, radius=6, fill=True, stroke=True)

    c.setFont(bold_font, 9)
    c.setFillColor(colors.HexColor('#9D174D'))
    c.drawString(72, terms_box_top - 20, "PHẠM VI CÔNG VIỆC & ĐIỀU KHOẢN ĐÃ THỐNG NHẤT:")

    scope_snippet = f"Phạm vi: {commission.agreed_scope or commission.description}"
    terms_snippet = f"Điều khoản: {commission.agreed_terms or 'Cấp quyền theo gói đã chọn. Không chuyển nhượng bản quyền tác giả gốc.'}"
    full_text = f"{scope_snippet} • {terms_snippet}"
    wrapped_lines = wrap(full_text, width=78)

    c.setFont(regular_font, 8.5)
    c.setFillColor(colors.HexColor('#374151'))
    ty = terms_box_top - 38
    for line in wrapped_lines[:6]:
        c.drawString(72, ty, line)
        ty -= 15

    # 6. Legal Clauses Box
    legal_y = terms_box_top - terms_box_h - 18
    c.setFont(bold_font, 8.5)
    c.setFillColor(colors.HexColor('#C52A70'))
    c.drawString(55, legal_y, "TUYÊN BỐ PHÁP LÝ & BẢO LƯU BẢN QUYỀN COMMISSION:")

    legal_clauses = [
        "1. Quyền sử dụng được cấp theo thỏa thuận đã ký kết giữa Nghệ sĩ và Người mua trên nền tảng ARTFAIR.",
        "2. Toàn bộ Bản quyền tác giả (Copyright) và quyền nhân thân gốc vẫn thuộc về Nghệ sĩ sáng tác.",
        "3. Tác phẩm commission được bàn giao qua hệ thống bảo mật ARTFAIR và đã được người mua nghiệm thu hoàn tất.",
        "4. Giao dịch được thực hiện qua hệ thống mô phỏng ARTFAIR Sandbox, phục vụ thử nghiệm quy trình đặt vẽ.",
    ]

    c.setFont(regular_font, 7.8)
    c.setFillColor(colors.HexColor('#4B5563'))
    ly = legal_y - 15
    for clause in legal_clauses:
        c.drawString(55, ly, clause)
        ly -= 14

    # 7. Signature & Platform Stamp
    stamp_y = ly - 10
    c.setStrokeColor(colors.HexColor('#E5E7EB'))
    c.line(55, stamp_y, width - 55, stamp_y)

    c.setFont(bold_font, 8.5)
    c.setFillColor(colors.HexColor('#2E124D'))
    c.drawString(70, stamp_y - 20, "XÁC NHẬN BỞI HỆ THỐNG ARTFAIR")
    c.setFont(italic_font, 8)
    c.setFillColor(colors.HexColor('#6B7280'))
    c.drawString(70, stamp_y - 34, "Hệ thống xác thực điện tử tự động")

    c.setFont(bold_font, 8.5)
    c.setFillColor(colors.HexColor('#C52A70'))
    c.drawRightString(width - 70, stamp_y - 20, "NGHIỆM THU: HOÀN TẤT")
    c.setFont(regular_font, 8)
    c.setFillColor(colors.HexColor('#6B7280'))
    c.drawRightString(width - 70, stamp_y - 34, "Commission Verified")

    # Bottom watermark/footer
    c.setFont(regular_font, 7)
    c.setFillColor(colors.HexColor('#9CA3AF'))
    c.drawCentredString(width / 2.0, 42, f"Chứng nhận điện tử ARTFAIR • https://artfair.vn • Mã xác thực: {cert_code}")

    c.save()
    return buffer.getvalue()
