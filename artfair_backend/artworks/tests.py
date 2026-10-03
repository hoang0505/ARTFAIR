import io
from decimal import Decimal
from PIL import Image
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from rest_framework.test import APIClient
from rest_framework import status

from artworks.models import Category, Tag, Artwork, ArtworkFile, LicenseOption, Order, Withdrawal, get_creator_financials

User = get_user_model()


def make_test_image(filename="test.png", color=(100, 150, 200), width=800, height=600):
    output = io.BytesIO()
    img = Image.new('RGB', (width, height), color=color)
    img.save(output, format='PNG')
    output.seek(0)
    return SimpleUploadedFile(filename, output.getvalue(), content_type='image/png')


class ArtworksTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.admin = User.objects.create_superuser(
            username='admin_test',
            email='admin@test.local',
            password='AdminPassword123!'
        )
        self.creator1 = User.objects.create_user(
            username='creator_one',
            email='creator1@test.local',
            password='CreatorPassword123!',
            role=User.Role.CREATOR
        )
        self.creator2 = User.objects.create_user(
            username='creator_two',
            email='creator2@test.local',
            password='CreatorPassword123!',
            role=User.Role.CREATOR
        )
        self.buyer = User.objects.create_user(
            username='buyer_one',
            email='buyer1@test.local',
            password='BuyerPassword123!',
            role=User.Role.BUYER
        )

        # Taxonomies
        self.category = Category.objects.create(
            name='Digital Art',
            slug='digital-art',
            description='Kỹ thuật số'
        )
        self.tag_cyber = Tag.objects.create(name='cyberpunk', slug='cyberpunk')
        self.tag_fantasy = Tag.objects.create(name='fantasy', slug='fantasy')

    def test_buyer_cannot_create_artwork(self):
        """
        Buyer must be forbidden from creating artwork.
        """
        self.client.force_login(self.buyer)
        response = self.client.post(reverse('artworks:creator_artwork_list_create'), {
            'title': 'Tranh của Buyer',
            'category_id': self.category.id,
            'description': 'Mô tả',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_creator_can_create_artwork_and_backend_assigns_owner(self):
        """
        Creator creates artwork; backend automatically assigns creator from request.user,
        ignoring any fake creator_id sent by the client.
        """
        self.client.force_login(self.creator1)
        response = self.client.post(reverse('artworks:creator_artwork_list_create'), {
            'title': 'Bình Minh Cyberpunk',
            'category_id': self.category.id,
            'description': 'Tác phẩm mới',
            'creator_id': self.creator2.id,  # Fake owner ID attempt
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        artwork = Artwork.objects.get(id=response.data['id'])
        # Confirms backend assigned creator1
        self.assertEqual(artwork.creator, self.creator1)
        self.assertNotEqual(artwork.creator, self.creator2)
        self.assertEqual(artwork.status, Artwork.Status.DRAFT)

    def test_creator_cannot_modify_other_creator_artwork(self):
        """
        Creator 2 cannot update or delete Creator 1's artwork.
        """
        artwork = Artwork.objects.create(
            creator=self.creator1,
            title='Tác phẩm của Creator 1',
            category=self.category,
            status=Artwork.Status.DRAFT
        )

        self.client.force_login(self.creator2)
        response = self.client.patch(
            reverse('artworks:creator_artwork_detail', kwargs={'pk': artwork.id}),
            {'title': 'Tên bị hack'}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        artwork.refresh_from_db()
        self.assertEqual(artwork.title, 'Tác phẩm của Creator 1')

    def test_draft_and_archived_hidden_from_public_catalog(self):
        """
        Public catalog only shows PUBLISHED works.
        DRAFT and ARCHIVED works are hidden and return 404 on public detail.
        """
        art_published = Artwork.objects.create(
            creator=self.creator1,
            title='Tác phẩm Công Khai',
            category=self.category,
            status=Artwork.Status.PUBLISHED
        )
        art_draft = Artwork.objects.create(
            creator=self.creator1,
            title='Tác phẩm Bản Nháp',
            category=self.category,
            status=Artwork.Status.DRAFT
        )
        art_archived = Artwork.objects.create(
            creator=self.creator1,
            title='Tác phẩm Lưu Trữ',
            category=self.category,
            status=Artwork.Status.ARCHIVED
        )

        # Public list
        list_res = self.client.get(reverse('artworks:public_artwork_list'))
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        returned_ids = [item['id'] for item in list_res.data['results']]
        self.assertIn(art_published.id, returned_ids)
        self.assertNotIn(art_draft.id, returned_ids)
        self.assertNotIn(art_archived.id, returned_ids)

        # Public detail
        detail_published = self.client.get(reverse('artworks:public_artwork_detail', kwargs={'lookup': art_published.slug}))
        self.assertEqual(detail_published.status_code, status.HTTP_200_OK)

        detail_draft = self.client.get(reverse('artworks:public_artwork_detail', kwargs={'lookup': art_draft.slug}))
        self.assertEqual(detail_draft.status_code, status.HTTP_404_NOT_FOUND)

        detail_archived = self.client.get(reverse('artworks:public_artwork_detail', kwargs={'lookup': art_archived.slug}))
        self.assertEqual(detail_archived.status_code, status.HTTP_404_NOT_FOUND)

    def test_creator_can_view_own_drafts_in_my_artworks(self):
        """
        Creator can view their own drafts and archived works in /my-artworks/.
        """
        art_draft = Artwork.objects.create(
            creator=self.creator1,
            title='Bản Nháp Riêng',
            category=self.category,
            status=Artwork.Status.DRAFT
        )

        self.client.force_login(self.creator1)
        res = self.client.get(reverse('artworks:creator_artwork_list_create'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        returned_ids = [item['id'] for item in res.data['results']]
        self.assertIn(art_draft.id, returned_ids)

    def test_unique_license_option_constraint(self):
        """
        Enforce that each artwork can have at most one option for each license type.
        """
        artwork = Artwork.objects.create(
            creator=self.creator1,
            title='Test License Artwork',
            category=self.category,
            status=Artwork.Status.DRAFT
        )
        LicenseOption.objects.create(
            artwork=artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            price=Decimal('100000')
        )
        with self.assertRaises(IntegrityError):
            LicenseOption.objects.create(
                artwork=artwork,
                license_type=LicenseOption.LicenseType.PERSONAL,
                price=Decimal('200000')
            )

    def test_publish_conditions_enforcement(self):
        """
        Publishing an artwork requires:
        1. Preview image
        2. Original deliverable file
        3. Both active PERSONAL and COMMERCIAL license options with price > 0
        """
        artwork = Artwork.objects.create(
            creator=self.creator1,
            title='Artwork Ready To Publish Test',
            category=self.category,
            status=Artwork.Status.DRAFT
        )

        self.client.force_login(self.creator1)
        publish_url = reverse('artworks:creator_artwork_publish', kwargs={'pk': artwork.id})

        # Step 1: Attempt to publish empty artwork -> 400
        res1 = self.client.post(publish_url)
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('blocking_reasons', res1.data)
        self.assertGreater(len(res1.data['blocking_reasons']), 0)

        # Step 2: Upload original raster file (automatically creates preview image)
        file_upload_url = reverse('artworks:creator_artwork_file_upload', kwargs={'artwork_id': artwork.id})
        test_file = make_test_image("master_art.png", width=1600, height=1200)
        upload_res = self.client.post(file_upload_url, {'file': test_file}, format='multipart')
        self.assertEqual(upload_res.status_code, status.HTTP_200_OK)

        artwork.refresh_from_db()
        self.assertTrue(bool(artwork.preview_image))
        self.assertTrue(hasattr(artwork, 'original_file'))

        # Step 3: Still missing license options -> 400
        res2 = self.client.post(publish_url)
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

        # Step 4: Add only PERSONAL license -> still missing COMMERCIAL -> 400
        license_url = reverse('artworks:creator_artwork_licenses', kwargs={'artwork_id': artwork.id})
        self.client.post(license_url, {
            'license_type': LicenseOption.LicenseType.PERSONAL,
            'price': '200000',
            'terms': 'Điều khoản cá nhân'
        })
        res3 = self.client.post(publish_url)
        self.assertEqual(res3.status_code, status.HTTP_400_BAD_REQUEST)

        # Step 5: Add COMMERCIAL license with price > 0 -> Now ready!
        self.client.post(license_url, {
            'license_type': LicenseOption.LicenseType.COMMERCIAL,
            'price': '1500000',
            'terms': 'Điều khoản thương mại'
        })

        # Step 6: Publish succeeds!
        res_success = self.client.post(publish_url)
        self.assertEqual(res_success.status_code, status.HTTP_200_OK)

        artwork.refresh_from_db()
        self.assertEqual(artwork.status, Artwork.Status.PUBLISHED)

    def test_secure_file_download_protection(self):
        """
        Original files are private:
        - Anonymous guests get 401
        - Buyers get 403
        - Other creators get 403
        - Creator owner gets 200
        - Admin gets 200
        - Public API does not reveal file paths
        """
        artwork = Artwork.objects.create(
            creator=self.creator1,
            title='Protected Download Test',
            category=self.category,
            status=Artwork.Status.PUBLISHED
        )
        test_file = make_test_image("confidential_master.png")
        ArtworkFile.objects.create(
            artwork=artwork,
            file=test_file,
            original_filename='confidential_master.png',
            file_format='PNG',
            file_size_bytes=1024,
            dpi=300
        )

        download_url = reverse('artworks:artwork_download_file', kwargs={'artwork_id': artwork.id})

        # 1. Anonymous guest
        res_guest = self.client.get(download_url)
        self.assertIn(res_guest.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        # 2. Buyer
        self.client.force_login(self.buyer)
        res_buyer = self.client.get(download_url)
        self.assertEqual(res_buyer.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Other Creator
        self.client.force_login(self.creator2)
        res_other = self.client.get(download_url)
        self.assertEqual(res_other.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Artwork Owner (Creator 1)
        self.client.force_login(self.creator1)
        res_owner = self.client.get(download_url)
        self.assertEqual(res_owner.status_code, status.HTTP_200_OK)
        self.assertIn('attachment', res_owner.get('Content-Disposition', ''))

        # 5. Admin
        self.client.force_login(self.admin)
        res_admin = self.client.get(download_url)
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

        # 6. Verify public detail API does not contain raw file path
        self.client.logout()
        pub_detail = self.client.get(reverse('artworks:public_artwork_detail', kwargs={'lookup': artwork.slug}))
        self.assertEqual(pub_detail.status_code, status.HTTP_200_OK)
        self.assertNotIn('protected_media', str(pub_detail.data))
        self.assertNotIn('confidential_master.png', str(pub_detail.data.get('file_metadata', {})))

    def test_price_and_license_filtering(self):
        """
        Verify multi-tier price and license filtering.
        """
        art_cheap = Artwork.objects.create(
            creator=self.creator1,
            title='Cheap Artwork',
            category=self.category,
            status=Artwork.Status.PUBLISHED
        )
        LicenseOption.objects.create(
            artwork=art_cheap,
            license_type=LicenseOption.LicenseType.COMMERCIAL,
            price=Decimal('500000')
        )

        art_expensive = Artwork.objects.create(
            creator=self.creator1,
            title='Expensive Artwork',
            category=self.category,
            status=Artwork.Status.PUBLISHED
        )
        LicenseOption.objects.create(
            artwork=art_expensive,
            license_type=LicenseOption.LicenseType.COMMERCIAL,
            price=Decimal('5000000')
        )

        # Filter commercial <= 1,000,000
        url = reverse('artworks:public_artwork_list') + '?license_type=COMMERCIAL&max_price=1000000'
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        returned_ids = [item['id'] for item in res.data['results']]
        self.assertIn(art_cheap.id, returned_ids)
        self.assertNotIn(art_expensive.id, returned_ids)


class Screen02OrderAndPaymentTests(TestCase):
    """
    Test suite for Screen 02:
    - Order creation & backend price enforcement
    - Anti-self-purchase for creators
    - Simulated payment gateway (Success, Failed, Cancel)
    - Granting / withholding download access to original deliverable file
    - Already-owned restrictions & multi-buyer non-exclusive sales
    - Cross-user order isolation
    - Artwork detail page view rendering
    """
    def setUp(self):
        self.client = APIClient()

        self.creator = User.objects.create_user(
            username='artist_mai',
            email='mai@test.local',
            password='ArtistPassword123!',
            role=User.Role.CREATOR
        )
        self.buyer1 = User.objects.create_user(
            username='buyer_hoa',
            email='hoa@test.local',
            password='BuyerPassword123!',
            role=User.Role.BUYER
        )
        self.buyer2 = User.objects.create_user(
            username='buyer_lan',
            email='lan@test.local',
            password='BuyerPassword123!',
            role=User.Role.BUYER
        )

        self.category = Category.objects.create(name='Digital Art', slug='digital-art')

        # Published artwork
        self.artwork = Artwork.objects.create(
            creator=self.creator,
            title='Sen Hồng Bình Minh',
            slug='sen-hong-binh-minh',
            category=self.category,
            status=Artwork.Status.PUBLISHED,
            preview_image=make_test_image("preview.png")
        )

        # Original deliverable file
        self.art_file = ArtworkFile.objects.create(
            artwork=self.artwork,
            file=make_test_image("master_sen.png"),
            original_filename='master_sen.png',
            file_format='PNG',
            file_size_bytes=2048,
            width=3840,
            height=2160,
            dpi=300,
            color_mode='RGB'
        )

        # Licenses
        self.lic_personal = LicenseOption.objects.create(
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            price=Decimal('250000'),
            terms='Chỉ dùng mục đích cá nhân, phi thương mại.'
        )
        self.lic_commercial = LicenseOption.objects.create(
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.COMMERCIAL,
            price=Decimal('850000'),
            terms='Được dùng cho sản phẩm thương mại và truyền thông.'
        )

    def test_anonymous_user_cannot_create_order(self):
        """Guests cannot create purchase orders; must authenticate first."""
        order_url = reverse('artworks:order_create')
        res = self.client.post(order_url, {
            'artwork_id': self.artwork.id,
            'license_type': 'PERSONAL'
        })
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_creator_cannot_buy_own_artwork(self):
        """Creators are forbidden from buying license of their own artwork."""
        self.client.force_login(self.creator)
        order_url = reverse('artworks:order_create')
        res = self.client.post(order_url, {
            'artwork_id': self.artwork.id,
            'license_type': 'PERSONAL'
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('không thể tự mua', str(res.data))

    def test_price_is_100_percent_backend_enforced(self):
        """
        Price must be enforced directly from database; client-tampered prices are ignored.
        """
        self.client.force_login(self.buyer1)
        order_url = reverse('artworks:order_create')
        # Attempt to pass a malicious price of 1,000 VND
        res = self.client.post(order_url, {
            'artwork_id': self.artwork.id,
            'license_type': 'PERSONAL',
            'price': 1000,
            'price_paid': 1000
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        created_order = Order.objects.get(order_code=res.data['order_code'])
        # Confirms real price 250,000 VND is stored
        self.assertEqual(created_order.price_paid, Decimal('250000'))
        self.assertEqual(created_order.status, Order.Status.PENDING)

    def test_payment_simulation_success_and_download_grant(self):
        """
        Simulated SUCCESS payment completes order, updates timestamp, and unlocks file download.
        Artwork remains PUBLISHED (never marked SOLD).
        """
        self.client.force_login(self.buyer1)
        # 1. Create order
        res_create = self.client.post(reverse('artworks:order_create'), {
            'artwork_id': self.artwork.id,
            'license_type': 'PERSONAL'
        })
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        order_code = res_create.data['order_code']

        # 2. Before payment, download is forbidden
        dl_url = reverse('artworks:artwork_download_file', kwargs={'artwork_id': self.artwork.id})
        res_dl_before = self.client.get(dl_url)
        self.assertEqual(res_dl_before.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Simulate payment SUCCESS
        pay_url = reverse('artworks:order_simulate_payment', kwargs={'order_code': order_code})
        res_pay = self.client.post(pay_url, {'action': 'SUCCESS'})
        self.assertEqual(res_pay.status_code, status.HTTP_200_OK)
        self.assertEqual(res_pay.data['order']['status'], Order.Status.COMPLETED)

        # Order in DB is completed
        order = Order.objects.get(order_code=order_code)
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertIsNotNone(order.completed_at)

        # 4. After SUCCESS payment, download file is granted!
        res_dl_after = self.client.get(dl_url)
        self.assertEqual(res_dl_after.status_code, status.HTTP_200_OK)
        self.assertIn('attachment', res_dl_after.get('Content-Disposition', ''))

        # 5. Artwork remains PUBLISHED (non-exclusive)
        self.artwork.refresh_from_db()
        self.assertEqual(self.artwork.status, Artwork.Status.PUBLISHED)

    def test_non_exclusive_multiple_buyers_can_purchase_same_artwork(self):
        """
        Multiple buyers can buy the exact same license type on the same artwork.
        Both buyers gain deliverable file access.
        """
        # Buyer 1 buys PERSONAL
        self.client.force_login(self.buyer1)
        res1 = self.client.post(reverse('artworks:order_create'), {
            'artwork_id': self.artwork.id,
            'license_type': 'PERSONAL'
        })
        self.client.post(reverse('artworks:order_simulate_payment', kwargs={'order_code': res1.data['order_code']}), {
            'action': 'SUCCESS'
        })

        # Buyer 2 also buys PERSONAL on same artwork
        self.client.force_login(self.buyer2)
        res2 = self.client.post(reverse('artworks:order_create'), {
            'artwork_id': self.artwork.id,
            'license_type': 'PERSONAL'
        })
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.client.post(reverse('artworks:order_simulate_payment', kwargs={'order_code': res2.data['order_code']}), {
            'action': 'SUCCESS'
        })

        # Both have download access
        dl_url = reverse('artworks:artwork_download_file', kwargs={'artwork_id': self.artwork.id})
        self.assertEqual(self.client.get(dl_url).status_code, status.HTTP_200_OK)

        self.client.force_login(self.buyer1)
        self.assertEqual(self.client.get(dl_url).status_code, status.HTTP_200_OK)

    def test_cannot_rebuy_already_owned_license_but_can_buy_other_license(self):
        """
        If buyer already owns PERSONAL, attempting to purchase PERSONAL again returns 400 with already_owned=True.
        However, purchasing COMMERCIAL is allowed.
        """
        self.client.force_login(self.buyer1)
        # Buy and complete PERSONAL
        res = self.client.post(reverse('artworks:order_create'), {
            'artwork_id': self.artwork.id,
            'license_type': 'PERSONAL'
        })
        self.client.post(reverse('artworks:order_simulate_payment', kwargs={'order_code': res.data['order_code']}), {
            'action': 'SUCCESS'
        })

        # Try to buy PERSONAL again
        res_dup = self.client.post(reverse('artworks:order_create'), {
            'artwork_id': self.artwork.id,
            'license_type': 'PERSONAL'
        })
        self.assertEqual(res_dup.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(res_dup.data.get('already_owned'))

        # Buyer CAN buy COMMERCIAL
        res_comm = self.client.post(reverse('artworks:order_create'), {
            'artwork_id': self.artwork.id,
            'license_type': 'COMMERCIAL'
        })
        self.assertEqual(res_comm.status_code, status.HTTP_201_CREATED)

    def test_payment_failed_and_cancel_actions(self):
        """
        Simulated FAILED or CANCEL do not grant access to deliverable files.
        """
        self.client.force_login(self.buyer1)
        # Order 1: FAILED
        res1 = self.client.post(reverse('artworks:order_create'), {
            'artwork_id': self.artwork.id,
            'license_type': 'PERSONAL'
        })
        code1 = res1.data['order_code']
        res_fail = self.client.post(reverse('artworks:order_simulate_payment', kwargs={'order_code': code1}), {
            'action': 'FAILED'
        })
        self.assertEqual(res_fail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_fail.data['order']['status'], Order.Status.FAILED)

        # Order 2: CANCEL
        res2 = self.client.post(reverse('artworks:order_create'), {
            'artwork_id': self.artwork.id,
            'license_type': 'COMMERCIAL'
        })
        code2 = res2.data['order_code']
        res_cancel = self.client.post(reverse('artworks:order_simulate_payment', kwargs={'order_code': code2}), {
            'action': 'CANCEL'
        })
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        self.assertEqual(res_cancel.data['order']['status'], Order.Status.CANCELLED)

        # No download access
        dl_url = reverse('artworks:artwork_download_file', kwargs={'artwork_id': self.artwork.id})
        self.assertEqual(self.client.get(dl_url).status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_access_or_pay_other_user_order(self):
        """
        User B is forbidden from paying or modifying User A's order.
        """
        self.client.force_login(self.buyer1)
        res = self.client.post(reverse('artworks:order_create'), {
            'artwork_id': self.artwork.id,
            'license_type': 'PERSONAL'
        })
        order_code = res.data['order_code']

        # Buyer 2 attempts to simulate payment on Buyer 1's order
        self.client.force_login(self.buyer2)
        res_hack = self.client.post(reverse('artworks:order_simulate_payment', kwargs={'order_code': order_code}), {
            'action': 'SUCCESS'
        })
        self.assertEqual(res_hack.status_code, status.HTTP_403_FORBIDDEN)

        # Buyer 2 cannot retrieve Buyer 1's order
        res_get = self.client.get(reverse('artworks:order_detail', kwargs={'order_code': order_code}))
        self.assertEqual(res_get.status_code, status.HTTP_404_NOT_FOUND)

    def test_prevent_duplicate_payment_if_already_completed(self):
        """
        Submitting payment for an already completed order does not double-charge or change state.
        """
        self.client.force_login(self.buyer1)
        res = self.client.post(reverse('artworks:order_create'), {
            'artwork_id': self.artwork.id,
            'license_type': 'PERSONAL'
        })
        order_code = res.data['order_code']
        pay_url = reverse('artworks:order_simulate_payment', kwargs={'order_code': order_code})

        res_first = self.client.post(pay_url, {'action': 'SUCCESS'})
        self.assertEqual(res_first.status_code, status.HTTP_200_OK)

        # Send second time
        res_second = self.client.post(pay_url, {'action': 'SUCCESS'})
        self.assertEqual(res_second.status_code, status.HTTP_200_OK)
        self.assertIn('thành công trước đó', res_second.data['detail'])

    def test_artwork_detail_page_renders_successfully(self):
        """
        GET /artworks/<slug>/ returns 200 and contains artwork title, prices, terms and specs.
        """
        res = self.client.get(reverse('artwork_detail', kwargs={'slug': self.artwork.slug}))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        content = res.content.decode('utf-8')
        self.assertIn('Sen Hồng Bình Minh', content)
        self.assertIn('250000', content)
        self.assertIn('850000', content)
        self.assertIn('Quyền sử dụng không độc quyền', content)
        self.assertIn('300 DPI', content)


class Screen03CreatorStudioTests(TestCase):
    """
    Test suite for Screen 03:
    - Studio URL access control (Buyer forbidden, Guest forbidden, Creator allowed)
    - 3-Step Publishing Wizard (Publish now vs. Save draft)
    - Real watermarked preview generation from raster files
    - Non-raster (PSD/ZIP) requirement for supplementary preview
    - Editing artwork information, prices, replacing files
    - Creator cannot edit other creator's artwork
    - Publishing and archiving lifecycle
    - Historical order price integrity when creator changes prices
    """
    def setUp(self):
        self.client = APIClient()

        self.creator1 = User.objects.create_user(
            username='studio_artist_one',
            email='artist1@test.local',
            password='ArtistPassword123!',
            role=User.Role.CREATOR
        )
        self.creator2 = User.objects.create_user(
            username='studio_artist_two',
            email='artist2@test.local',
            password='ArtistPassword123!',
            role=User.Role.CREATOR
        )
        self.buyer = User.objects.create_user(
            username='studio_buyer_one',
            email='buyer_studio@test.local',
            password='BuyerPassword123!',
            role=User.Role.BUYER
        )

        self.category = Category.objects.create(name='Concept Art', slug='concept-art')
        self.tag_scifi = Tag.objects.create(name='scifi', slug='scifi')

    def test_buyer_forbidden_from_studio_url(self):
        """Buyers are strictly forbidden from accessing Studio URL directly (HTTP 403)."""
        self.client.force_login(self.buyer)
        res = self.client.get(reverse('creator_studio'))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Người mua (Buyer)', res.content.decode('utf-8'))

    def test_guest_forbidden_from_studio_url(self):
        """Guests are forbidden from accessing Studio URL directly (HTTP 403)."""
        res = self.client.get(reverse('creator_studio'))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_creator_can_access_studio_url(self):
        """Creators can access Studio URL (HTTP 200) with dashboard metrics."""
        self.client.force_login(self.creator1)
        res = self.client.get(reverse('creator_studio'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        content = res.content.decode('utf-8')
        self.assertIn('Studio của bạn', content)
        self.assertIn('Tổng doanh thu', content)
        self.assertIn('Đăng tác phẩm', content)

    def test_publish_wizard_success_and_watermark_generation(self):
        """
        Creator uses 3-step publish wizard to publish artwork:
        - Uploads raster PNG
        - Watermark preview is automatically generated
        - Master file is securely stored
        - PERSONAL and COMMERCIAL licenses are configured
        - Status becomes PUBLISHED
        """
        self.client.force_login(self.creator1)
        test_file = make_test_image("starship_final.png", width=1920, height=1080)

        url = reverse('artworks:creator_studio_publish_wizard')
        data = {
            'action': 'publish',
            'title': 'Chiến Hạm Sao Thổ',
            'description': 'Mô tả tác phẩm viễn tưởng không gian.',
            'category_id': self.category.id,
            'tag_ids': str(self.tag_scifi.id),
            'file': test_file,
            'personal_price': '200000',
            'personal_terms': 'Phi thương mại.',
            'commercial_price': '800000',
            'commercial_terms': 'Thương mại.',
            'rights_confirmed': 'true'
        }

        res = self.client.post(url, data, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['artwork']['status'], Artwork.Status.PUBLISHED)

        artwork = Artwork.objects.get(pk=res.data['artwork']['id'])
        self.assertEqual(artwork.creator, self.creator1)
        self.assertEqual(artwork.status, Artwork.Status.PUBLISHED)
        self.assertTrue(bool(artwork.preview_image))
        self.assertTrue(hasattr(artwork, 'original_file'))
        self.assertEqual(artwork.original_file.file_format, 'PNG')
        self.assertEqual(artwork.license_options.count(), 2)

    def test_publish_wizard_save_draft(self):
        """
        Creator saves artwork as DRAFT via wizard.
        """
        self.client.force_login(self.creator1)
        test_file = make_test_image("draft_sketch.png")
        url = reverse('artworks:creator_studio_publish_wizard')
        data = {
            'action': 'draft',
            'title': 'Bản Phác Thảo Cũ',
            'category_id': self.category.id,
            'file': test_file,
            'personal_price': '100000'
        }
        res = self.client.post(url, data, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['artwork']['status'], Artwork.Status.DRAFT)

    def test_publish_wizard_fails_without_rights_confirmation(self):
        """Publishing requires explicit rights confirmation checkbox."""
        self.client.force_login(self.creator1)
        test_file = make_test_image("unconfirmed.png")
        url = reverse('artworks:creator_studio_publish_wizard')
        data = {
            'action': 'publish',
            'title': 'Tranh Chưa Xác Nhận',
            'category_id': self.category.id,
            'file': test_file,
            'personal_price': '100000',
            'commercial_price': '300000',
            'rights_confirmed': 'false'
        }
        res = self.client.post(url, data, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rights_confirmed', res.data)

    def test_non_raster_file_requires_custom_preview(self):
        """
        PSD/AI/ZIP files cannot be automatically rendered by Pillow without specialized raster engine;
        system requires supplementary preview_image.
        """
        self.client.force_login(self.creator1)
        fake_psd = SimpleUploadedFile("artwork_layers.psd", b"8BPSfakePSDcontent", content_type="application/octet-stream")

        url = reverse('artworks:creator_studio_publish_wizard')
        # Attempt without preview_image
        data_no_prev = {
            'action': 'publish',
            'title': 'Dự Án PSD Nhiều Lớp',
            'category_id': self.category.id,
            'file': fake_psd,
            'personal_price': '250000',
            'commercial_price': '900000',
            'rights_confirmed': 'true'
        }
        res_no_prev = self.client.post(url, data_no_prev, format='multipart')
        self.assertEqual(res_no_prev.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('preview_image', res_no_prev.data)

        # Upload with supplementary JPG preview succeeds
        fake_psd.seek(0)
        custom_jpg = make_test_image("psd_preview.jpg")
        data_with_prev = {
            'action': 'publish',
            'title': 'Dự Án PSD Nhiều Lớp',
            'category_id': self.category.id,
            'file': fake_psd,
            'preview_image': custom_jpg,
            'personal_price': '250000',
            'commercial_price': '900000',
            'rights_confirmed': 'true'
        }
        res_with_prev = self.client.post(url, data_with_prev, format='multipart')
        self.assertEqual(res_with_prev.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_with_prev.data['artwork']['status'], Artwork.Status.PUBLISHED)

    def test_creator_can_edit_own_artwork_and_change_prices(self):
        """Creator can edit title, category, description, and license prices."""
        self.client.force_login(self.creator1)
        art = Artwork.objects.create(
            creator=self.creator1,
            title='Tranh Ban Đầu',
            category=self.category,
            status=Artwork.Status.DRAFT
        )

        edit_url = reverse('artworks:creator_studio_edit_wizard', kwargs={'pk': art.id})
        res = self.client.post(edit_url, {
            'title': 'Tranh Đã Sửa Đổi Tên',
            'description': 'Mô tả mới',
            'personal_price': '300000',
            'commercial_price': '1000000'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        art.refresh_from_db()
        self.assertEqual(art.title, 'Tranh Đã Sửa Đổi Tên')
        self.assertEqual(art.license_options.get(license_type=LicenseOption.LicenseType.PERSONAL).price, Decimal('300000'))

    def test_creator_cannot_edit_other_creator_artwork(self):
        """Creator 2 cannot edit Creator 1's artwork (HTTP 403)."""
        art_creator1 = Artwork.objects.create(
            creator=self.creator1,
            title='Bản Quyền Creator 1',
            category=self.category,
            status=Artwork.Status.DRAFT
        )

        self.client.force_login(self.creator2)
        edit_url = reverse('artworks:creator_studio_edit_wizard', kwargs={'pk': art_creator1.id})
        res = self.client.post(edit_url, {'title': 'Đổi Tên Giả Mạo'})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        art_creator1.refresh_from_db()
        self.assertEqual(art_creator1.title, 'Bản Quyền Creator 1')

    def test_creator_archive_and_republish(self):
        """Creator can archive and republish their artworks."""
        self.client.force_login(self.creator1)
        art = Artwork.objects.create(
            creator=self.creator1,
            title='Tranh Phát Hành và Lưu Trữ',
            category=self.category,
            status=Artwork.Status.PUBLISHED,
            preview_image=make_test_image("p.png")
        )
        ArtworkFile.objects.create(
            artwork=art,
            file=make_test_image("m.png"),
            original_filename='m.png',
            file_format='PNG',
            file_size_bytes=1024
        )
        LicenseOption.objects.create(artwork=art, license_type=LicenseOption.LicenseType.PERSONAL, price=Decimal('100000'))
        LicenseOption.objects.create(artwork=art, license_type=LicenseOption.LicenseType.COMMERCIAL, price=Decimal('500000'))

        # 1. Archive
        res_arch = self.client.post(reverse('artworks:creator_artwork_archive', kwargs={'pk': art.id}))
        self.assertEqual(res_arch.status_code, status.HTTP_200_OK)
        art.refresh_from_db()
        self.assertEqual(art.status, Artwork.Status.ARCHIVED)

        # 2. Republish
        res_pub = self.client.post(reverse('artworks:creator_artwork_publish', kwargs={'pk': art.id}))
        self.assertEqual(res_pub.status_code, status.HTTP_200_OK)
        art.refresh_from_db()
        self.assertEqual(art.status, Artwork.Status.PUBLISHED)

    def test_historical_orders_preserve_price_after_license_edit(self):
        """
        When creator edits license price, existing completed orders maintain their
        original historical price_paid and terms_snapshot.
        """
        self.client.force_login(self.creator1)
        art = Artwork.objects.create(
            creator=self.creator1,
            title='Tranh Lịch Sử Giá',
            category=self.category,
            status=Artwork.Status.PUBLISHED,
            preview_image=make_test_image("art.png")
        )
        lic_pers = LicenseOption.objects.create(
            artwork=art,
            license_type=LicenseOption.LicenseType.PERSONAL,
            price=Decimal('200000'),
            terms='Điều khoản lúc đầu'
        )

        # Buyer buys at 200,000 VND
        order = Order.objects.create(
            buyer=self.buyer,
            artwork=art,
            license_type=LicenseOption.LicenseType.PERSONAL,
            license_option=lic_pers,
            price_paid=Decimal('200000'),
            terms_snapshot='Điều khoản lúc đầu',
            status=Order.Status.COMPLETED
        )

        # Creator updates price to 500,000 VND
        self.client.force_login(self.creator1)
        edit_url = reverse('artworks:creator_studio_edit_wizard', kwargs={'pk': art.id})
        self.client.post(edit_url, {'personal_price': '500000', 'personal_terms': 'Điều khoản mới'})

        # Verify historical order is unchanged
        order.refresh_from_db()
        self.assertEqual(order.price_paid, Decimal('200000'))
        self.assertEqual(order.terms_snapshot, 'Điều khoản lúc đầu')

        # Current license option has new price
        lic_pers.refresh_from_db()
        self.assertEqual(lic_pers.price, Decimal('500000'))




class Screen04DashboardAndPersonalHubTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.creator = User.objects.create_user(
            username='artist_test4',
            email='artist4@test.local',
            password='Password123!',
            role=User.Role.CREATOR
        )
        self.buyer1 = User.objects.create_user(
            username='buyer_test4',
            email='buyer4@test.local',
            password='Password123!',
            role=User.Role.BUYER
        )
        self.buyer2 = User.objects.create_user(
            username='buyer_other4',
            email='buyer_other4@test.local',
            password='Password123!',
            role=User.Role.BUYER
        )

        self.category = Category.objects.create(name='Minh họa 4', slug='minh-hoa-4')

        # Create artwork
        self.artwork = Artwork.objects.create(
            title='Bình Minh Saigon 4',
            creator=self.creator,
            category=self.category,
            preview_image=make_test_image('preview4.png'),
            status=Artwork.Status.PUBLISHED
        )

        self.lic_pers = LicenseOption.objects.create(
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            price=Decimal('150000'),
            terms='Điều khoản cá nhân'
        )

        self.lic_comm = LicenseOption.objects.create(
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.COMMERCIAL,
            price=Decimal('500000'),
            terms='Điều khoản thương mại'
        )

        self.artwork_file = ArtworkFile.objects.create(
            artwork=self.artwork,
            file=SimpleUploadedFile('master4.png', b'MASTER_FILE_BINARY_CONTENT', content_type='image/png'),
            original_filename='master4.png',
            file_format='PNG',
            file_size_bytes=26,
            width=800,
            height=600
        )

    def test_dashboard_page_requires_auth(self):
        # Anonymous user gets redirected to home
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn('/?auth=login', response.url)

        # Authenticated buyer gets 200
        self.client.force_login(self.buyer1)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Authenticated creator gets 200
        self.client.force_login(self.creator)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_library_lists_only_completed_orders_and_distinct_licenses(self):
        # Buyer1 buys PERSONAL (COMPLETED)
        order_pers = Order.objects.create(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            license_option=self.lic_pers,
            price_paid=Decimal('150000'),
            terms_snapshot='Điều khoản cá nhân',
            status=Order.Status.COMPLETED
        )

        # Buyer1 buys COMMERCIAL (COMPLETED)
        order_comm = Order.objects.create(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.COMMERCIAL,
            license_option=self.lic_comm,
            price_paid=Decimal('500000'),
            terms_snapshot='Điều khoản thương mại',
            status=Order.Status.COMPLETED
        )

        # Buyer1 creates pending order (NOT completed)
        order_pending = Order.objects.create(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            license_option=self.lic_pers,
            price_paid=Decimal('150000'),
            status=Order.Status.PENDING
        )

        self.client.force_login(self.buyer1)
        url = reverse('artworks:my_library_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)  # Only completed orders

        licenses_found = {item['license_type'] for item in results}
        self.assertIn('PERSONAL', licenses_found)
        self.assertIn('COMMERCIAL', licenses_found)

        for item in results:
            self.assertTrue(item['has_original_file'])
            self.assertIn('/download-file/', item['download_url'])
            self.assertIn('/certificate/', item['certificate_url'])

    def test_download_permission_and_archived_artwork(self):
        order = Order.objects.create(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            license_option=self.lic_pers,
            price_paid=Decimal('150000'),
            status=Order.Status.COMPLETED
        )

        download_url = reverse('artworks:artwork_download_file', kwargs={'artwork_id': self.artwork.id})

        # Buyer1 can download
        self.client.force_login(self.buyer1)
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Buyer2 (not purchased) gets 403 Forbidden
        self.client.force_login(self.buyer2)
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # When artwork is archived, buyer1 STILL retains download right
        self.artwork.status = Artwork.Status.ARCHIVED
        self.artwork.save()

        self.client.force_login(self.buyer1)
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_order_certificate_pdf_export(self):
        order = Order.objects.create(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            license_option=self.lic_pers,
            price_paid=Decimal('150000'),
            terms_snapshot='Quyền cá nhân tại thời điểm giao dịch',
            status=Order.Status.COMPLETED
        )

        cert_url = reverse('artworks:order_certificate_pdf', kwargs={'order_code': order.order_code})

        # Buyer1 can export PDF
        self.client.force_login(self.buyer1)
        response = self.client.get(cert_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

        # Buyer2 gets 403 Forbidden
        self.client.force_login(self.buyer2)
        response = self.client.get(cert_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Pending order cannot export certificate (400 Bad Request)
        pending_order = Order.objects.create(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.COMMERCIAL,
            license_option=self.lic_comm,
            price_paid=Decimal('500000'),
            status=Order.Status.PENDING
        )
        pending_cert_url = reverse('artworks:order_certificate_pdf', kwargs={'order_code': pending_order.order_code})
        self.client.force_login(self.buyer1)
        response = self.client.get(pending_cert_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_revenue_ledger_and_no_duplicates(self):
        # Order 1: 150,000 VND (COMPLETED)
        Order.objects.create(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            license_option=self.lic_pers,
            price_paid=Decimal('150000'),
            status=Order.Status.COMPLETED
        )

        # Order 2: 500,000 VND (COMPLETED)
        Order.objects.create(
            buyer=self.buyer2,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.COMMERCIAL,
            license_option=self.lic_comm,
            price_paid=Decimal('500000'),
            status=Order.Status.COMPLETED
        )

        # Order 3: 150,000 VND (PENDING - not yet paid)
        Order.objects.create(
            buyer=self.buyer2,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            license_option=self.lic_pers,
            price_paid=Decimal('150000'),
            status=Order.Status.PENDING
        )

        # Creator checks dashboard metrics
        self.client.force_login(self.creator)
        url = reverse('artworks:creator_dashboard_metrics')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data['total_completed_sales_count'], 2)
        self.assertEqual(data['total_revenue'], 650000)
        self.assertEqual(data['available_balance'], 650000)
        self.assertEqual(data['total_withdrawn'], 0)
        self.assertEqual(len(data['sales_transactions']), 2)

        # Non-creator gets 403 Forbidden
        self.client.force_login(self.buyer1)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_creator_withdrawal_success_and_overdraw_protection(self):
        # Create 600,000 VND in completed sales for creator
        Order.objects.create(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.COMMERCIAL,
            license_option=self.lic_comm,
            price_paid=Decimal('600000'),
            status=Order.Status.COMPLETED
        )

        self.client.force_login(self.creator)
        withdraw_url = reverse('artworks:creator_withdrawals')

        # 1. Try to overdraw (withdraw 700,000 > 600,000) -> 400
        res_over = self.client.post(withdraw_url, {'amount': 700000})
        self.assertEqual(res_over.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('vượt quá số dư', res_over.data['detail'])

        # 2. Try zero or negative -> 400
        res_zero = self.client.post(withdraw_url, {'amount': 0})
        self.assertEqual(res_zero.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Successful withdrawal of 200,000 VND
        res_ok1 = self.client.post(withdraw_url, {'amount': 200000, 'note': 'Rút đợt 1'})
        self.assertEqual(res_ok1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_ok1.data['new_available_balance'], 400000)
        self.assertEqual(res_ok1.data['total_withdrawn'], 200000)

        # 4. Withdraw remaining 400,000 VND
        res_ok2 = self.client.post(withdraw_url, {'amount': 400000, 'note': 'Rút hết'})
        self.assertEqual(res_ok2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_ok2.data['new_available_balance'], 0)
        self.assertEqual(res_ok2.data['total_withdrawn'], 600000)

        # 5. Try to withdraw when balance is 0 -> 400
        res_empty = self.client.post(withdraw_url, {'amount': 50000})
        self.assertEqual(res_empty.status_code, status.HTTP_400_BAD_REQUEST)

        # 6. Non-creator cannot withdraw -> 403 Forbidden
        self.client.force_login(self.buyer1)
        res_buyer = self.client.post(withdraw_url, {'amount': 10000})
        self.assertEqual(res_buyer.status_code, status.HTTP_403_FORBIDDEN)

    def test_simulate_payment_notifications_and_isolation(self):
        from accounts.models import Notification

        # Create pending order for buyer1 on artwork owned by self.creator
        order = Order.objects.create(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.COMMERCIAL,
            license_option=self.lic_comm,
            price_paid=Decimal('500000'),
            terms_snapshot='Điều khoản thương mại',
            status=Order.Status.PENDING
        )

        pay_url = reverse('artworks:order_simulate_payment', kwargs={'order_code': order.order_code})

        # 1. Action FAILED: Order status changes to FAILED, NO notification created for creator
        self.client.force_login(self.buyer1)
        res_failed = self.client.post(pay_url, {'action': 'FAILED'})
        self.assertEqual(res_failed.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.FAILED)
        self.assertEqual(Notification.objects.filter(recipient=self.creator).count(), 0)

        # 2. Reset to PENDING and test CANCEL: NO notification created for creator
        order.status = Order.Status.PENDING
        order.save(update_fields=['status'])
        res_cancel = self.client.post(pay_url, {'action': 'CANCEL'})
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(Notification.objects.filter(recipient=self.creator).count(), 0)

        # 3. Action SUCCESS: Order status changes to COMPLETED, creator receives notification
        order.status = Order.Status.PENDING
        order.save(update_fields=['status'])
        res_success = self.client.post(pay_url, {'action': 'SUCCESS'})
        self.assertEqual(res_success.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)

        # Verify Creator notification
        creator_notifs = Notification.objects.filter(recipient=self.creator)
        self.assertEqual(creator_notifs.count(), 1)
        creator_n = creator_notifs.first()
        self.assertIn(self.artwork.title, creator_n.message)
        self.assertIn(order.order_code, creator_n.message)
        self.assertIn('500,000 VND', creator_n.message)
        self.assertIn(order.get_license_type_display(), creator_n.message)
        self.assertEqual(creator_n.notification_type, Notification.NotificationType.CREATOR_SALE)
        self.assertEqual(creator_n.target_url, '/dashboard/#tab-revenue')

        # Verify Buyer also received their notification
        buyer_notifs = Notification.objects.filter(recipient=self.buyer1)
        self.assertEqual(buyer_notifs.count(), 1)

        # Verify other users received NO notifications (isolation)
        self.assertEqual(Notification.objects.filter(recipient=self.buyer2).count(), 0)

        # 4. Idempotency: Repeated request does NOT duplicate notification
        res_repeat = self.client.post(pay_url, {'action': 'SUCCESS'})
        self.assertEqual(res_repeat.status_code, status.HTTP_200_OK)
        self.assertEqual(Notification.objects.filter(recipient=self.creator).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.buyer1).count(), 1)

    def test_artwork_filter_artist_case_insensitive(self):
        """
        Verify that ?artist=<username> filters artworks case-insensitively.
        """
        art = Artwork.objects.create(
            creator=self.creator,
            title='Art by Creator',
            category=self.category,
            status=Artwork.Status.PUBLISHED
        )

        # Query uppercase
        url = reverse('artworks:public_artwork_list') + f'?artist={self.creator.username.upper()}'
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get('results', res.data)
        ids = [item['id'] for item in results]
        self.assertIn(art.id, ids)

    def test_pending_order_creation_is_idempotent(self):
        """
        Verify that multiple attempts to create an order for the same artwork
        and license type while one is already PENDING returns the existing order
        instead of creating duplicate database records.
        """
        self.client.force_login(self.buyer1)
        url = reverse('artworks:order_create')
        payload = {
            'artwork_id': self.artwork.id,
            'license_type': LicenseOption.LicenseType.PERSONAL
        }

        # 1st creation
        res1 = self.client.post(url, payload)
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        order_code1 = res1.data['order_code']

        # 2nd creation (user double-clicks or re-initiates)
        res2 = self.client.post(url, payload)
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        order_code2 = res2.data['order_code']

        self.assertEqual(order_code1, order_code2)
        # Verify only 1 pending order exists in database
        count = Order.objects.filter(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            status=Order.Status.PENDING
        ).count()
        self.assertEqual(count, 1)

    def test_payment_simulation_idempotency_prevents_duplicate_financials(self):
        """
        Verify that calling simulate-payment SUCCESS multiple times does not
        duplicate revenue in financials or create multiple notifications.
        """
        order = Order.objects.create(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            license_option=self.lic_pers,
            price_paid=Decimal('150000'),
            terms_snapshot='Điều khoản cá nhân',
            status=Order.Status.PENDING
        )
        pay_url = reverse('artworks:order_simulate_payment', kwargs={'order_code': order.order_code})
        self.client.force_login(self.buyer1)

        # 1st success payment
        res1 = self.client.post(pay_url, {'action': 'SUCCESS'})
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        fin1 = get_creator_financials(self.creator)
        self.assertEqual(fin1['total_revenue'], Decimal('150000'))

        # 2nd success payment (e.g. network retry or rapid click)
        res2 = self.client.post(pay_url, {'action': 'SUCCESS'})
        self.assertEqual(res2.status_code, status.HTTP_200_OK)

        fin2 = get_creator_financials(self.creator)
        self.assertEqual(fin2['total_revenue'], Decimal('150000'))
        self.assertEqual(fin2['available_balance'], Decimal('150000'))

    def test_download_file_fallback_for_preview_only_artwork(self):
        """
        Verify that an artwork with only preview_image (and no ArtworkFile record)
        falls back gracefully to preview_image instead of returning 404.
        """
        preview_art = Artwork.objects.create(
            title='Preview Only Art',
            creator=self.creator,
            category=self.category,
            preview_image=make_test_image('preview_only.png'),
            status=Artwork.Status.PUBLISHED
        )
        lic = LicenseOption.objects.create(
            artwork=preview_art,
            license_type=LicenseOption.LicenseType.PERSONAL,
            price=Decimal('100000'),
            terms='Terms'
        )
        Order.objects.create(
            buyer=self.buyer1,
            artwork=preview_art,
            license_type=LicenseOption.LicenseType.PERSONAL,
            license_option=lic,
            price_paid=Decimal('100000'),
            status=Order.Status.COMPLETED
        )

        dl_url = reverse('artworks:artwork_download_file', kwargs={'artwork_id': preview_art.id})
        self.client.force_login(self.buyer1)
        res = self.client.get(dl_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'image/png')

    def test_download_file_with_token_query_param(self):
        """
        Verify that a buyer can download their purchased artwork file via ?token=
        query param when unauthenticated in session (cross-origin scenario).
        """
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=self.buyer1)

        # Buyer1 buys artwork
        Order.objects.create(
            buyer=self.buyer1,
            artwork=self.artwork,
            license_type=LicenseOption.LicenseType.PERSONAL,
            license_option=self.lic_pers,
            price_paid=Decimal('150000'),
            status=Order.Status.COMPLETED
        )

        dl_url = reverse('artworks:artwork_download_file', kwargs={'artwork_id': self.artwork.id})

        # Anonymous client without session
        anon_client = APIClient()

        # 1. Without token -> 401 Unauthorized
        res_no_token = anon_client.get(dl_url)
        self.assertEqual(res_no_token.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. With invalid token -> 401 Unauthorized
        res_bad_token = anon_client.get(f'{dl_url}?token=invalid_token_123')
        self.assertEqual(res_bad_token.status_code, status.HTTP_401_UNAUTHORIZED)

        # 3. With valid token -> 200 OK
        res_valid_token = anon_client.get(f'{dl_url}?token={token.key}')
        self.assertEqual(res_valid_token.status_code, status.HTTP_200_OK)



