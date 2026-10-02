import io
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import ArtistProfile
from artworks.models import Artwork, Category, get_creator_financials
from commissions.models import Commission, CommissionProposal, CommissionEvent

User = get_user_model()


class CommissionFeatureTests(TestCase):
    def setUp(self):
        # 1. Create Users
        self.creator_user = User.objects.create_user(
            username='artist_mai',
            email='mai@example.com',
            password='Password123!',
            role=User.Role.CREATOR
        )
        self.artist_profile, _ = ArtistProfile.objects.get_or_create(user=self.creator_user)
        self.artist_profile.display_name = 'Họa Sĩ Mai'
        self.artist_profile.bio = 'Chuyên vẽ minh họa phong cảnh và phong cách fantasy.'
        self.artist_profile.is_accepting_commissions = True
        self.artist_profile.save()

        self.buyer_user = User.objects.create_user(
            username='buyer_nam',
            email='nam@example.com',
            password='Password123!',
            role=User.Role.BUYER
        )

        self.other_user = User.objects.create_user(
            username='stranger_hoa',
            email='hoa@example.com',
            password='Password123!',
            role=User.Role.BUYER
        )

        # 2. Create Artworks for Creator (1 Published, 1 Draft)
        self.category = Category.objects.create(name='Minh Họa', slug='minh-hoa')
        dummy_img = SimpleUploadedFile("preview.jpg", b"fake_image_bytes", content_type="image/jpeg")

        self.published_artwork = Artwork.objects.create(
            creator=self.creator_user,
            title='Bình Minh Trên Đồi',
            slug='binh-minh-tren-doi',
            category=self.category,
            status=Artwork.Status.PUBLISHED,
            preview_image=dummy_img
        )

        self.draft_artwork = Artwork.objects.create(
            creator=self.creator_user,
            title='Tranh Chưa Đăng',
            slug='tranh-chua-dang',
            category=self.category,
            status=Artwork.Status.DRAFT,
            preview_image=dummy_img
        )

        self.client = Client()

    def test_public_artist_profile_page(self):
        """Artist profile shows only PUBLISHED artworks and correct creator info."""
        response = self.client.get(f'/artists/{self.creator_user.username}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Họa Sĩ Mai')
        self.assertContains(response, 'Bình Minh Trên Đồi')
        self.assertNotContains(response, 'Tranh Chưa Đăng')

    def test_artist_not_accepting_commissions_validation(self):
        """Cannot submit commission if artist is not accepting commissions."""
        self.artist_profile.is_accepting_commissions = False
        self.artist_profile.save()

        self.client.force_login(self.buyer_user)
        payload = {
            'creator_username': self.creator_user.username,
            'title': 'Vẽ chân dung anime',
            'description': 'Mô tả chi tiết brief',
            'budget': '500000',
            'deadline': (timezone.now() + timezone.timedelta(days=10)).date().isoformat(),
            'license_type': 'PERSONAL'
        }
        response = self.client.post('/api/commissions/', data=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('tạm ngừng nhận yêu cầu đặt vẽ', str(response.data))

    def test_cannot_self_commission(self):
        """Creator cannot commission themselves."""
        self.client.force_login(self.creator_user)
        payload = {
            'creator_username': self.creator_user.username,
            'title': 'Tự đặt vẽ',
            'description': 'Brief tự vẽ',
            'budget': '500000',
            'deadline': (timezone.now() + timezone.timedelta(days=10)).date().isoformat(),
            'license_type': 'PERSONAL'
        }
        response = self.client.post('/api/commissions/', data=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('không thể tự gửi yêu cầu đặt vẽ cho chính mình', str(response.data))

    def test_commission_full_lifecycle_and_escrow(self):
        """
        Complete lifecycle test:
        1. Buyer creates request
        2. Creator submits proposal
        3. Buyer accepts and simulates escrow payment
        4. Creator delivers final deliverable
        5. Buyer requests revision
        6. Creator re-delivers
        7. Buyer completes and releases escrow
        8. Creator available balance verified
        9. PDF Certificate verified
        """
        # Step 1: Buyer creates request
        self.client.force_login(self.buyer_user)
        ref_file = SimpleUploadedFile("moodboard.png", b"test_reference_content", content_type="image/png")
        payload = {
            'creator_username': self.creator_user.username,
            'title': 'Thiết kế bìa sách',
            'description': 'Phong cách sơn dầu huyền bí',
            'budget': '1200000',
            'deadline': (timezone.now() + timezone.timedelta(days=14)).date().isoformat(),
            'license_type': 'COMMERCIAL',
            'reference_file': ref_file
        }
        create_resp = self.client.post('/api/commissions/', data=payload)
        self.assertEqual(create_resp.status_code, 201)
        commission_id = create_resp.data['id']
        commission = Commission.objects.get(id=commission_id)
        self.assertEqual(commission.status, Commission.Status.REQUESTED)
        self.assertTrue(bool(commission.reference_image))

        # Initial financial check: 0 balance
        fin_before = get_creator_financials(self.creator_user)
        self.assertEqual(fin_before['available_balance'], Decimal('0'))

        # Step 2: Creator submits proposal
        self.client.force_login(self.creator_user)
        proposal_payload = {
            'price': '1500000',
            'delivery_date': (timezone.now() + timezone.timedelta(days=12)).date().isoformat(),
            'scope_of_work': 'Vẽ bìa sách 300dpi, 2 concept phác thảo',
            'max_revisions': '2',
            'license_terms': 'Quyền thương mại không độc quyền'
        }
        prop_resp = self.client.post(f'/api/commissions/{commission_id}/submit-proposal/', data=proposal_payload)
        self.assertEqual(prop_resp.status_code, 200)
        commission.refresh_from_db()
        self.assertEqual(commission.status, Commission.Status.QUOTED)
        self.assertEqual(commission.proposals.count(), 1)
        self.assertEqual(commission.active_proposal.price, Decimal('1500000'))

        # Step 3: Buyer accepts and simulates escrow payment
        self.client.force_login(self.buyer_user)
        pay_resp = self.client.post(f'/api/commissions/{commission_id}/accept-and-pay/', data={'action': 'SUCCESS'})
        self.assertEqual(pay_resp.status_code, 200)
        commission.refresh_from_db()
        self.assertEqual(commission.status, Commission.Status.IN_PROGRESS)
        self.assertTrue(commission.is_paid)
        self.assertFalse(commission.is_escrow_released)
        self.assertEqual(commission.agreed_price, Decimal('1500000'))
        self.assertEqual(commission.agreed_max_revisions, 2)

        # Creator available balance must still be 0 because escrow has NOT been released yet!
        fin_in_progress = get_creator_financials(self.creator_user)
        self.assertEqual(fin_in_progress['available_balance'], Decimal('0'))

        # Step 4: Creator delivers final deliverable
        self.client.force_login(self.creator_user)
        final_file = SimpleUploadedFile("cover_master.png", b"master_hi_res_pixels", content_type="image/png")
        deliv_resp = self.client.post(
            f'/api/commissions/{commission_id}/deliver/',
            data={'delivery_file': final_file, 'delivery_note': 'Bản hoàn thiện đầu tiên'}
        )
        self.assertEqual(deliv_resp.status_code, 200)
        commission.refresh_from_db()
        self.assertEqual(commission.status, Commission.Status.DELIVERED)

        # Step 5: Buyer requests revision (revision 1/2)
        self.client.force_login(self.buyer_user)
        rev_resp = self.client.post(
            f'/api/commissions/{commission_id}/request-revision/',
            data={'revision_note': 'Xin vui lòng chỉnh cho tông màu ấm hơn một chút.'}
        )
        self.assertEqual(rev_resp.status_code, 200)
        commission.refresh_from_db()
        self.assertEqual(commission.status, Commission.Status.REVISION_REQUESTED)
        self.assertEqual(commission.revisions_used, 1)

        # Step 6: Creator delivers revision
        self.client.force_login(self.creator_user)
        rev_file = SimpleUploadedFile("cover_master_v2.png", b"master_v2_pixels", content_type="image/png")
        deliv2_resp = self.client.post(
            f'/api/commissions/{commission_id}/deliver/',
            data={'delivery_file': rev_file, 'delivery_note': 'Đã chỉnh sửa tông ấm'}
        )
        self.assertEqual(deliv2_resp.status_code, 200)
        commission.refresh_from_db()
        self.assertEqual(commission.status, Commission.Status.DELIVERED)

        # Step 7: Buyer completes and approves commission
        self.client.force_login(self.buyer_user)
        comp_resp = self.client.post(f'/api/commissions/{commission_id}/complete/')
        self.assertEqual(comp_resp.status_code, 200)
        commission.refresh_from_db()
        self.assertEqual(commission.status, Commission.Status.COMPLETED)
        self.assertTrue(commission.is_escrow_released)

        # Step 8: Creator financial check - exactly 1,500,000 VND credited
        fin_after = get_creator_financials(self.creator_user)
        self.assertEqual(fin_after['commission_revenue'], Decimal('1500000'))
        self.assertEqual(fin_after['available_balance'], Decimal('1500000'))

        # Idempotency check: completing again should be rejected
        comp_again = self.client.post(f'/api/commissions/{commission_id}/complete/')
        self.assertEqual(comp_again.status_code, 400)

        # Step 9: PDF Certificate export
        cert_resp = self.client.get(f'/api/commissions/{commission_id}/certificate/')
        self.assertEqual(cert_resp.status_code, 200)
        self.assertEqual(cert_resp['Content-Type'], 'application/pdf')

    def test_commission_security_and_isolation(self):
        """Unauthorized third party cannot view or download commission files."""
        # Create a private commission between buyer and creator
        commission = Commission.objects.create(
            buyer=self.buyer_user,
            creator=self.creator_user,
            title='Đơn bảo mật',
            description='Ý tưởng riêng tư',
            budget=Decimal('800000'),
            deadline=(timezone.now() + timezone.timedelta(days=7)).date(),
            reference_image=SimpleUploadedFile("secret_ref.png", b"top_secret", content_type="image/png"),
            reference_filename="secret_ref.png"
        )

        # Stranger tries to view details via API (isolated queryset returns 404 or 403)
        self.client.force_login(self.other_user)
        resp = self.client.get(f'/api/commissions/{commission.id}/')
        self.assertIn(resp.status_code, [403, 404])

        # Stranger tries to download reference file
        dl_resp = self.client.get(f'/api/commissions/{commission.id}/download-reference/')
        self.assertEqual(dl_resp.status_code, 403)

        # Stranger tries to access tracking page
        page_resp = self.client.get(f'/commissions/{commission.id}/')
        self.assertEqual(page_resp.status_code, 403)
