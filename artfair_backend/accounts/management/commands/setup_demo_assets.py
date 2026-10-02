import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.conf import settings
from accounts.models import ArtistProfile

User = get_user_model()


class Command(BaseCommand):
    help = (
        'Idempotently sets up illustrative avatars and public domain cover art for specific '
        'demo creator accounts (admin, creator_an, creator_binh). Does not overwrite existing user uploads. '
        'Supports --dry-run.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate actions and output planned changes without modifying database or files.'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        self.stdout.write(self.style.NOTICE(f">>> ARTFAIR Demo Assets Setup (Dry Run: {dry_run})"))

        frontend_dir = Path(settings.BASE_DIR).parent / 'frontend'
        static_images_dir = frontend_dir / 'static' / 'images'
        curated_dir = static_images_dir / 'curated'
        avatars_dir = static_images_dir / 'avatars'

        # Demo profile configuration map
        demo_artists = {
            'admin': {
                'avatar_file': avatars_dir / 'avatar_admin.png',
                'avatar_name': 'avatar_admin.png',
                'cover_file': curated_dir / 'renoir_bouquet_chrysanthemums_1881.jpg',
                'cover_name': 'cover_renoir_chrysanthemums_1881.jpg',
                'cover_caption': 'Dữ liệu minh họa — Tranh gốc: Bouquet of Chrysanthemums (Auguste Renoir, 1881 - Public Domain CC0)'
            },
            'creator_an': {
                'avatar_file': avatars_dir / 'avatar_creator_an.png',
                'avatar_name': 'avatar_creator_an.png',
                'cover_file': curated_dir / 'monet_water_lilies_1906.jpg',
                'cover_name': 'cover_monet_water_lilies_1906.jpg',
                'cover_caption': 'Dữ liệu minh họa — Tranh gốc: Water Lilies (Claude Monet, 1906 - Public Domain CC0)'
            },
            'creator_binh': {
                'avatar_file': avatars_dir / 'avatar_creator_binh.png',
                'avatar_name': 'avatar_creator_binh.png',
                'cover_file': curated_dir / 'vangogh_irises_1890.jpg',
                'cover_name': 'cover_vangogh_irises_1890.jpg',
                'cover_caption': 'Dữ liệu minh họa — Tranh gốc: Irises (Vincent van Gogh, 1890 - Public Domain CC0)'
            }
        }

        updated_count = 0

        for username, config in demo_artists.items():
            user = User.objects.filter(username=username).first()
            if not user:
                self.stdout.write(self.style.WARNING(f"[-] Bỏ qua: Không tìm thấy tài khoản {username}"))
                continue

            if not user.is_creator:
                self.stdout.write(self.style.WARNING(f"[-] Bỏ qua: Tài khoản {username} không có vai trò CREATOR"))
                continue

            profile, _ = ArtistProfile.objects.get_or_create(
                user=user,
                defaults={'display_name': user.username}
            )

            needs_save = False
            changes = []

            # Check Avatar
            if not profile.avatar:
                if config['avatar_file'].exists():
                    changes.append(f"Avatar: {config['avatar_name']}")
                    if not dry_run:
                        with open(config['avatar_file'], 'rb') as f:
                            profile.avatar.save(config['avatar_name'], ContentFile(f.read()), save=False)
                        needs_save = True
                else:
                    self.stdout.write(self.style.ERROR(f"(!) File avatar không tồn tại: {config['avatar_file']}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"[=] {username}: Đã có avatar, giữ nguyên (không ghi đè)"))

            # Check Cover Image
            if not profile.cover_image:
                if config['cover_file'].exists():
                    changes.append(f"Cover: {config['cover_name']}")
                    if not dry_run:
                        with open(config['cover_file'], 'rb') as f:
                            profile.cover_image.save(config['cover_name'], ContentFile(f.read()), save=False)
                        needs_save = True
                else:
                    self.stdout.write(self.style.ERROR(f"(!) File cover không tồn tại: {config['cover_file']}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"[=] {username}: Đã có cover_image, giữ nguyên (không ghi đè)"))

            # If bio doesn't mention demo attribution, append clear demo note
            demo_note = config['cover_caption']
            if demo_note not in profile.bio:
                changes.append("Bổ sung ghi chú nguồn tranh minh họa")
                if not dry_run:
                    if profile.bio:
                        profile.bio = f"{profile.bio.rstrip()}\n\n[{demo_note}]"
                    else:
                        profile.bio = f"[{demo_note}]"
                    needs_save = True

            if changes:
                if dry_run:
                    self.stdout.write(self.style.NOTICE(f"[DRY-RUN] Sẽ cập nhật cho {username}: {', '.join(changes)}"))
                else:
                    profile.save()
                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS(f"[+] Đã cập nhật cho {username}: {', '.join(changes)}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"[=] {username}: Đầy đủ dữ liệu, không cần thay đổi"))

        self.stdout.write(self.style.SUCCESS(f">>> Hoàn tất setup demo assets. Tổng số tài khoản cập nhật: {updated_count}"))
