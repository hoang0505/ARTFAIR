from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import ArtistProfile

User = get_user_model()


class AccountsAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_registration_buyer_hashes_password_and_normalizes_email(self):
        """
        Verify registration hashes password, normalizes email, and sets default fields.
        """
        payload = {
            'username': 'buyer_test',
            'email': 'Buyer.Test@Example.COM',
            'password': 'StrongPassword123!',
            'role': User.Role.BUYER,
        }
        response = self.client.post(reverse('accounts:register'), payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(username='buyer_test')
        # Email is normalized
        self.assertEqual(user.email, 'Buyer.Test@example.com')
        # Password is securely hashed, not plaintext
        self.assertNotEqual(user.password, 'StrongPassword123!')
        self.assertTrue(user.check_password('StrongPassword123!'))
        # Defaults are safe
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_email_verified)
        self.assertEqual(user.role, User.Role.BUYER)
        # Buyer does not have artist profile
        self.assertFalse(hasattr(user, 'artist_profile') and user.artist_profile is not None)

    def test_registration_cannot_elevate_privileges(self):
        """
        Verify public registration cannot grant staff, superuser or email verification status.
        """
        payload = {
            'username': 'hacker',
            'email': 'hacker@example.com',
            'password': 'HackerPassword123!',
            'role': User.Role.BUYER,
            'is_staff': True,
            'is_superuser': True,
            'is_email_verified': True,
            'is_active': True,
        }
        response = self.client.post(reverse('accounts:register'), payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(username='hacker')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_email_verified)

    def test_registration_creator_automatically_creates_artist_profile(self):
        """
        Verify that registering as CREATOR creates an ArtistProfile.
        """
        payload = {
            'username': 'creator_test',
            'email': 'creator@example.com',
            'password': 'CreatorPassword123!',
            'role': User.Role.CREATOR,
        }
        response = self.client.post(reverse('accounts:register'), payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(username='creator_test')
        self.assertEqual(user.role, User.Role.CREATOR)
        self.assertTrue(hasattr(user, 'artist_profile'))
        self.assertEqual(user.artist_profile.display_name, 'creator_test')

    def test_login_and_logout_session(self):
        """
        Verify session authentication login and logout.
        """
        User.objects.create_user(username='loginuser', email='login@example.com', password='ValidPassword123!')
        
        # Invalid password
        fail_res = self.client.post(reverse('accounts:login'), {
            'username': 'loginuser',
            'password': 'WrongPassword'
        })
        self.assertEqual(fail_res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Valid login
        login_res = self.client.post(reverse('accounts:login'), {
            'username': 'loginuser',
            'password': 'ValidPassword123!'
        })
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

        # Logout
        logout_res = self.client.post(reverse('accounts:logout'))
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)

    def test_creator_can_update_profile_buyer_is_forbidden(self):
        """
        Verify only Creator can access and edit artist profile.
        """
        creator = User.objects.create_user(
            username='art_creator',
            email='creator@art.local',
            password='Password123!',
            role=User.Role.CREATOR
        )
        buyer = User.objects.create_user(
            username='art_buyer',
            email='buyer@art.local',
            password='Password123!',
            role=User.Role.BUYER
        )

        # Buyer attempts to access artist-profile
        self.client.force_login(buyer)
        buyer_res = self.client.get(reverse('accounts:creator_artist_profile'))
        self.assertEqual(buyer_res.status_code, status.HTTP_403_FORBIDDEN)

        # Creator accesses and updates artist profile
        self.client.force_login(creator)
        creator_res = self.client.patch(reverse('accounts:creator_artist_profile'), {
            'display_name': 'Art Masterpiece',
            'bio': 'Creative painter in Hanoi.',
            'is_accepting_commissions': True
        })
        self.assertEqual(creator_res.status_code, status.HTTP_200_OK)
        self.assertEqual(creator_res.data['display_name'], 'Art Masterpiece')
        self.assertTrue(creator_res.data['is_accepting_commissions'])

    def test_public_artist_profile_does_not_leak_email_or_password(self):
        """
        Public artist profile view should not expose private details.
        """
        creator = User.objects.create_user(
            username='famous_artist',
            email='secret.email@artist.local',
            password='SuperSecretPassword123!',
            role=User.Role.CREATOR
        )
        profile = creator.artist_profile
        profile.display_name = 'Famous Master'
        profile.save()

        response = self.client.get(reverse('accounts:public_artist_profile', kwargs={'username': 'famous_artist'}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['display_name'], 'Famous Master')
        self.assertNotIn('email', response.data)
        self.assertNotIn('password', response.data)

    def test_home_page_renders_html(self):
        """
        Verify that home page '/' renders HTML template successfully.
        """
        response = self.client.get('/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'ARTFAIR')
        self.assertContains(response, 'Nghệ thuật dành cho bạn')

    def test_api_overview_endpoint(self):
        """
        Verify that '/api/' returns API root overview JSON.
        """
        response = self.client.get('/api/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['project'], 'ARTFAIR Backend API')

    def test_change_password_endpoint(self):
        """
        Verify change-password endpoint requires correct old password and updates password.
        """
        user = User.objects.create_user(
            username='test_pwd_user',
            email='test_pwd@artfair.local',
            password='OldPassword123!'
        )
        self.client.force_authenticate(user=user)

        # Wrong old password
        res = self.client.post(reverse('accounts:change_password'), {
            'old_password': 'WrongPassword!',
            'new_password': 'NewPassword123!',
            'confirm_password': 'NewPassword123!'
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Mismatched confirm password
        res = self.client.post(reverse('accounts:change_password'), {
            'old_password': 'OldPassword123!',
            'new_password': 'NewPassword123!',
            'confirm_password': 'DifferentPassword123!'
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Success
        res = self.client.post(reverse('accounts:change_password'), {
            'old_password': 'OldPassword123!',
            'new_password': 'NewPassword123!',
            'confirm_password': 'NewPassword123!'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.check_password('NewPassword123!'))

    def test_register_and_login_with_invalid_token_header_succeeds(self):
        """
        Verify that registering or logging in with a stale/invalid Authorization header
        does NOT fail with 'Invalid token.' 401 response.
        """
        self.client.credentials(HTTP_AUTHORIZATION='Token bogus_stale_token_9999')

        # Register should succeed despite invalid token header
        reg_payload = {
            'username': 'stale_token_user',
            'email': 'stale_token@example.com',
            'password': 'SecurePassword123!',
            'role': User.Role.BUYER,
        }
        res = self.client.post(reverse('accounts:register'), reg_payload)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Login should succeed despite invalid token header
        login_payload = {
            'username': 'stale_token_user',
            'password': 'SecurePassword123!',
        }
        res = self.client.post(reverse('accounts:login'), login_payload)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_registration_rejects_case_insensitive_duplicate_username(self):
        """
        Verify that registering a username differing only by case is rejected.
        """
        User.objects.create_user(
            username='OriginalArtist',
            email='original@example.com',
            password='Password123!'
        )

        res = self.client.post(reverse('accounts:register'), {
            'username': 'originalartist',
            'email': 'different@example.com',
            'password': 'Password123!',
            'role': User.Role.BUYER
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', res.data)

    def test_public_artist_profile_case_insensitive(self):
        """
        Verify that public artist profile can be queried case-insensitively.
        """
        artist = User.objects.create_user(
            username='MasterPainter',
            email='painter@example.com',
            password='Password123!',
            role=User.Role.CREATOR
        )
        artist.artist_profile.display_name = 'Master Painter'
        artist.artist_profile.save()

        # Query lowercase username
        res = self.client.get(reverse('accounts:public_artist_profile', kwargs={'username': 'masterpainter'}))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['display_name'], 'Master Painter')

    def test_notification_mark_read_endpoints(self):
        """
        Verify both /read/ and /mark-read/ aliases work to mark a notification as read.
        """
        user = User.objects.create_user(
            username='notif_user',
            email='notif@example.com',
            password='Password123!'
        )
        notif1 = user.notifications.create(
            title='Test 1',
            message='Msg 1'
        )
        notif2 = user.notifications.create(
            title='Test 2',
            message='Msg 2'
        )

        self.client.force_authenticate(user=user)

        # Test canonical /read/ endpoint
        res1 = self.client.post(reverse('accounts:notification_mark_read', kwargs={'pk': notif1.pk}))
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        notif1.refresh_from_db()
        self.assertTrue(notif1.is_read)

        # Test alias /mark-read/ endpoint
        res2 = self.client.post(reverse('accounts:notification_mark_read_alias', kwargs={'pk': notif2.pk}))
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        notif2.refresh_from_db()
        self.assertTrue(notif2.is_read)



