import io
from decimal import Decimal
from PIL import Image, ImageDraw
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from accounts.models import ArtistProfile
from artworks.models import Category, Tag, Artwork, ArtworkFile, LicenseOption
from artworks.utils import generate_watermarked_preview

User = get_user_model()


def create_sample_master_image(title, width=2400, height=1600, bg_color=(20, 24, 40), accent_color=(255, 107, 107)):
    """
    Creates a realistic high-resolution artwork master file using Pillow.
    """
    img = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Draw background geometric / aesthetic art patterns
    for i in range(12):
        step = i * 60
        draw.rectangle(
            [100 + step, 100 + step, width - 100 - step, height - 100 - step],
            outline=(
                (bg_color[0] + i * 15) % 255,
                (bg_color[1] + i * 18) % 255,
                (bg_color[2] + i * 20) % 255
            ),
            width=6
        )

    # Draw vibrant central elements
    cx, cy = width // 2, height // 2
    r = min(width, height) // 3
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent_color, outline=(255, 255, 255), width=10)

    inner_r = r // 2
    draw.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r], fill=(255, 220, 100), outline=(50, 50, 50), width=6)

    # Add text banner
    draw.rectangle([100, height - 250, width - 100, height - 100], fill=(10, 10, 15))
    draw.text((150, height - 200), f"ARTFAIR MASTER FILE - {title.upper()}", fill=(255, 255, 255))
    draw.text((150, height - 150), "ORIGINAL RESOLUTION 2400x1600 - 300 DPI - RGB HIGH DEFINITION", fill=(180, 200, 220))

    output = io.BytesIO()
    img.save(output, format='PNG', dpi=(300, 300))
    output.seek(0)
    return output.getvalue()


class Command(BaseCommand):
    help = 'Seeds idempotent demo data for ARTFAIR development (Admin, Creators, Buyer, Categories, Tags, Artworks).'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(">>> Khởi tạo dữ liệu mẫu ARTFAIR..."))

        # 1. Superuser / Admin
        admin_user, admin_created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@artfair.local',
                'role': User.Role.CREATOR,
                'is_staff': True,
                'is_superuser': True,
                'is_email_verified': True,
            }
        )
        if admin_created:
            admin_user.set_password('Admin@123456')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("[+] Tạo tài khoản Admin: admin / Admin@123456"))
        else:
            self.stdout.write(self.style.WARNING("[-] Tài khoản Admin đã tồn tại: admin"))

        # 2. Creators
        c1, c1_created = User.objects.get_or_create(
            username='creator_an',
            defaults={
                'email': 'an.nguyen@artfair.local',
                'role': User.Role.CREATOR,
                'is_email_verified': True,
            }
        )
        if c1_created:
            c1.set_password('Creator@123456')
            c1.save()
            profile = c1.artist_profile
            profile.display_name = 'An Nguyễn Digital Art'
            profile.bio = 'Họa sĩ minh họa 2D chuyên phong cách Cyberpunk và Fantasy tại TP. Hồ Chí Minh.'
            profile.is_accepting_commissions = True
            profile.save()
            self.stdout.write(self.style.SUCCESS("[+] Tạo Creator 1: creator_an / Creator@123456"))
        else:
            self.stdout.write(self.style.WARNING("[-] Creator 1 đã tồn tại: creator_an"))

        c2, c2_created = User.objects.get_or_create(
            username='creator_binh',
            defaults={
                'email': 'binh.tran@artfair.local',
                'role': User.Role.CREATOR,
                'is_email_verified': True,
            }
        )
        if c2_created:
            c2.set_password('Creator@123456')
            c2.save()
            profile = c2.artist_profile
            profile.display_name = 'Bình Trần 3D Studio'
            profile.bio = 'Chuyên gia dựng hình 3D nhân vật và concept art phong cảnh viễn tưởng.'
            profile.is_accepting_commissions = False
            profile.save()
            self.stdout.write(self.style.SUCCESS("[+] Tạo Creator 2: creator_binh / Creator@123456"))
        else:
            self.stdout.write(self.style.WARNING("[-] Creator 2 đã tồn tại: creator_binh"))

        # 3. Buyer
        b1, b1_created = User.objects.get_or_create(
            username='buyer_chi',
            defaults={
                'email': 'chi.le@artfair.local',
                'role': User.Role.BUYER,
                'is_email_verified': True,
            }
        )
        if b1_created:
            b1.set_password('Buyer@123456')
            b1.save()
            self.stdout.write(self.style.SUCCESS("[+] Tạo Buyer: buyer_chi / Buyer@123456"))
        else:
            self.stdout.write(self.style.WARNING("[-] Buyer đã tồn tại: buyer_chi"))

        # 4. Categories
        cat_data = [
            ('Digital Painting', 'digital-painting', 'Tranh vẽ kỹ thuật số 2D độ phân giải cao.'),
            ('3D Art', '3d-art', 'Mô hình và kết xuất đồ họa 3D render chân thực.'),
            ('Concept Art', 'concept-art', 'Ý tưởng thiết kế bối cảnh, vũ khí và nhân vật.'),
            ('Illustration', 'illustration', 'Minh họa sách báo, bìa truyện và truyền thông.'),
        ]
        categories = {}
        for name, slug, desc in cat_data:
            cat, _ = Category.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'description': desc}
            )
            categories[slug] = cat

        # 5. Tags
        tag_data = ['cyberpunk', 'fantasy', 'portrait', 'landscape', 'anime', 'scifi', 'concept-art', '3d-render']
        tags = {}
        for t in tag_data:
            tag_obj, _ = Tag.objects.get_or_create(slug=t, defaults={'name': t})
            tags[t] = tag_obj

        # 6. Artworks
        # Artwork 1: Published by creator_an
        art1, art1_created = Artwork.objects.get_or_create(
            slug='sai-gon-2077-dem-mua-neon',
            defaults={
                'creator': c1,
                'title': 'Sài Gòn Năm 2077 - Đêm Mưa Neon',
                'description': 'Bức tranh phong cảnh Cyberpunk Sài Gòn tương lai rực rỡ ánh đèn neon dưới cơn mưa đêm.',
                'category': categories['digital-painting'],
                'status': Artwork.Status.PUBLISHED,
            }
        )
        if art1_created or not hasattr(art1, 'original_file'):
            art1.tags.set([tags['cyberpunk'], tags['scifi'], tags['landscape']])
            master_bytes = create_sample_master_image("Sài Gòn 2077 Đêm Mưa Neon", bg_color=(15, 10, 35), accent_color=(0, 240, 255))
            master_file = ContentFile(master_bytes, name="saigon_2077_master.png")

            # Generate watermarked preview
            preview_file = generate_watermarked_preview(master_file, max_dimension=1200)
            art1.preview_image.save(preview_file.name, preview_file, save=True)

            ArtworkFile.objects.update_or_create(
                artwork=art1,
                defaults={
                    'file': master_file,
                    'original_filename': 'saigon_2077_master.png',
                    'file_format': 'PNG',
                    'file_size_bytes': len(master_bytes),
                    'width': 2400,
                    'height': 1600,
                    'dpi': 300,
                    'color_mode': 'RGB',
                }
            )

            LicenseOption.objects.update_or_create(
                artwork=art1,
                license_type=LicenseOption.LicenseType.PERSONAL,
                defaults={
                    'price': Decimal('250000'),
                    'terms': 'Sử dụng làm hình nền máy tính, điện thoại hoặc in ấn treo tường cá nhân.',
                    'is_active': True,
                }
            )
            LicenseOption.objects.update_or_create(
                artwork=art1,
                license_type=LicenseOption.LicenseType.COMMERCIAL,
                defaults={
                    'price': Decimal('1500000'),
                    'terms': 'Sử dụng cho bìa sách, ấn phẩm quảng cáo, video YouTube thương mại không độc quyền.',
                    'is_active': True,
                }
            )
            self.stdout.write(self.style.SUCCESS("[+] Tạo tác phẩm PUBLISHED: Sài Gòn Năm 2077 - Đêm Mưa Neon"))

        # Artwork 2: Draft by creator_an
        art2, art2_created = Artwork.objects.get_or_create(
            slug='nu-chien-binh-hoa-sen',
            defaults={
                'creator': c1,
                'title': 'Nữ Chiến Binh Hoa Sen',
                'description': 'Phác thảo nhân vật phong cách Fantasy kết hợp họa tiết hoa sen truyền thống.',
                'category': categories['concept-art'],
                'status': Artwork.Status.DRAFT,
            }
        )
        if art2_created or not hasattr(art2, 'original_file'):
            art2.tags.set([tags['fantasy'], tags['portrait']])
            master_bytes = create_sample_master_image("Nữ Chiến Binh Hoa Sen", bg_color=(40, 20, 25), accent_color=(255, 120, 180))
            master_file = ContentFile(master_bytes, name="nu_chien_binh_draft.png")

            preview_file = generate_watermarked_preview(master_file, max_dimension=1000)
            art2.preview_image.save(preview_file.name, preview_file, save=True)

            ArtworkFile.objects.update_or_create(
                artwork=art2,
                defaults={
                    'file': master_file,
                    'original_filename': 'nu_chien_binh_draft.png',
                    'file_format': 'PNG',
                    'file_size_bytes': len(master_bytes),
                    'width': 2400,
                    'height': 1600,
                    'dpi': 300,
                    'color_mode': 'RGB',
                }
            )

            # Only has personal license, missing commercial -> keeping it DRAFT
            LicenseOption.objects.update_or_create(
                artwork=art2,
                license_type=LicenseOption.LicenseType.PERSONAL,
                defaults={
                    'price': Decimal('300000'),
                    'terms': 'Sử dụng cho mục đích cá nhân phi thương mại.',
                    'is_active': True,
                }
            )
            self.stdout.write(self.style.SUCCESS("[+] Tạo tác phẩm DRAFT: Nữ Chiến Binh Hoa Sen"))

        # Artwork 3: Published by creator_binh
        art3, art3_created = Artwork.objects.get_or_create(
            slug='chien-ham-khong-gian-lac-hong',
            defaults={
                'creator': c2,
                'title': 'Chiến Hạm Không Gian Lạc Hồng',
                'description': 'Mô hình render 3D chi tiết trạm vũ trụ và chiến hạm mang hoa văn chim Lạc.',
                'category': categories['3d-art'],
                'status': Artwork.Status.PUBLISHED,
            }
        )
        if art3_created or not hasattr(art3, 'original_file'):
            art3.tags.set([tags['scifi'], tags['concept-art']])
            master_bytes = create_sample_master_image("Chiến Hạm Lạc Hồng 3D", width=3000, height=2000, bg_color=(10, 20, 30), accent_color=(255, 190, 0))
            master_file = ContentFile(master_bytes, name="lac_hong_battleship_master.png")

            preview_file = generate_watermarked_preview(master_file, max_dimension=1200)
            art3.preview_image.save(preview_file.name, preview_file, save=True)

            ArtworkFile.objects.update_or_create(
                artwork=art3,
                defaults={
                    'file': master_file,
                    'original_filename': 'lac_hong_battleship_master.png',
                    'file_format': 'PNG',
                    'file_size_bytes': len(master_bytes),
                    'width': 3000,
                    'height': 2000,
                    'dpi': 300,
                    'color_mode': 'RGB',
                }
            )

            LicenseOption.objects.update_or_create(
                artwork=art3,
                license_type=LicenseOption.LicenseType.PERSONAL,
                defaults={
                    'price': Decimal('450000'),
                    'terms': 'Sử dụng cho hình nền, in ấn trang trí cá nhân.',
                    'is_active': True,
                }
            )
            LicenseOption.objects.update_or_create(
                artwork=art3,
                license_type=LicenseOption.LicenseType.COMMERCIAL,
                defaults={
                    'price': Decimal('3200000'),
                    'terms': 'Quyền sử dụng làm asset bối cảnh phim ngắn hoạt hình, bìa game, marketing.',
                    'is_active': True,
                }
            )
            self.stdout.write(self.style.SUCCESS("[+] Tạo tác phẩm PUBLISHED: Chiến Hạm Không Gian Lạc Hồng"))

        # Artwork 4: Archived by creator_binh
        art4, art4_created = Artwork.objects.get_or_create(
            slug='phac-thao-quai-vat-bien-dong',
            defaults={
                'creator': c2,
                'title': 'Phác Thảo Quái Vật Biển Đông',
                'description': 'Bản phác thảo lưu trữ sinh vật biển thần thoại cổ xưa.',
                'category': categories['concept-art'],
                'status': Artwork.Status.ARCHIVED,
            }
        )
        if art4_created or not hasattr(art4, 'original_file'):
            art4.tags.set([tags['fantasy']])
            master_bytes = create_sample_master_image("Quái Vật Biển Đông", bg_color=(20, 30, 25), accent_color=(120, 220, 150))
            master_file = ContentFile(master_bytes, name="quai_vat_bien_dong.png")

            preview_file = generate_watermarked_preview(master_file, max_dimension=1000)
            art4.preview_image.save(preview_file.name, preview_file, save=True)

            ArtworkFile.objects.update_or_create(
                artwork=art4,
                defaults={
                    'file': master_file,
                    'original_filename': 'quai_vat_bien_dong.png',
                    'file_format': 'PNG',
                    'file_size_bytes': len(master_bytes),
                    'width': 2400,
                    'height': 1600,
                    'dpi': 300,
                    'color_mode': 'RGB',
                }
            )

            LicenseOption.objects.update_or_create(
                artwork=art4,
                license_type=LicenseOption.LicenseType.PERSONAL,
                defaults={
                    'price': Decimal('150000'),
                    'terms': 'Sử dụng cá nhân.',
                    'is_active': True,
                }
            )
            LicenseOption.objects.update_or_create(
                artwork=art4,
                license_type=LicenseOption.LicenseType.COMMERCIAL,
                defaults={
                    'price': Decimal('1000000'),
                    'terms': 'Sử dụng thương mại.',
                    'is_active': True,
                }
            )
            self.stdout.write(self.style.SUCCESS("[+] Tạo tác phẩm ARCHIVED: Phác Thảo Quái Vật Biển Đông"))

        self.stdout.write(self.style.SUCCESS(">>> Hoàn tất khởi tạo dữ liệu mẫu ARTFAIR thành công!"))
