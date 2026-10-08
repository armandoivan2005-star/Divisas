from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .models import ExchangeAlert, FavoriteCurrency
from .roles import (
    ADMIN_ROLE,
    NORMAL_ROLE,
    SUPERVISOR_ROLE,
    get_user_role,
    set_user_role,
)
from .views import build_yahoo_symbol_candidates, sanitize_symbol_query, yahoo_market_name


class NavigationAndAuthTests(TestCase):
    def test_public_pages_are_available(self):
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        self.assertEqual(self.client.get(reverse('signup')).status_code, 200)
        self.assertEqual(self.client.get(reverse('site_map')).status_code, 200)

    def test_404_page_is_rendered(self):
        response = self.client.get('/ruta-inexistente/')
        self.assertEqual(response.status_code, 404)

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_dashboard_blocks_non_admin_users(self):
        user = User.objects.create_user(username='usuario_normal', password='123456Segura!')
        self.client.force_login(user)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_allows_primary_admin(self):
        admin_user = User.objects.create_user(username='armando', password='123456Segura!')
        self.client.force_login(admin_user)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)


class InputSanitizationTests(TestCase):
    def test_sanitize_symbol_query_removes_dangerous_chars(self):
        self.assertEqual(sanitize_symbol_query('<script>TSLA</script>'), 'SCRIPTTSLA/SCRIPT')
        self.assertEqual(sanitize_symbol_query('AAPL:BMV;DROP TABLE'), 'AAPL:BMVDROPTABLE')


class YahooFinanceSymbolTests(TestCase):
    def test_us_symbol_is_tried_before_mexican_variant(self):
        self.assertEqual(build_yahoo_symbol_candidates('AAPL'), ['AAPL', 'AAPL.MX'])

    def test_mexican_twelvedata_format_is_converted_to_yahoo(self):
        self.assertEqual(build_yahoo_symbol_candidates('WALMEX:BMV'), ['WALMEX.MX'])

    def test_mexican_market_and_currency_suffix_are_recognized(self):
        self.assertEqual(yahoo_market_name('WALMEX.MX', 'MEX'), 'Bolsa Mexicana de Valores')
        self.assertEqual(yahoo_market_name('AAPL', 'NMS'), 'Estados Unidos')


class SupervisorRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.primary_admin = User.objects.create_user(
            username='armando',
            password='123456Segura!',
        )
        set_user_role(cls.primary_admin, ADMIN_ROLE)

        cls.secondary_admin = User.objects.create_user(
            username='admin_secundario',
            password='123456Segura!',
        )
        set_user_role(cls.secondary_admin, ADMIN_ROLE)

        cls.supervisor = User.objects.create_user(
            username='supervisor_lectura',
            password='123456Segura!',
            is_staff=True,
            is_superuser=True,
        )
        set_user_role(cls.supervisor, SUPERVISOR_ROLE)

        cls.normal_user = User.objects.create_user(
            username='usuario_normal_roles',
            password='123456Segura!',
        )
        set_user_role(cls.normal_user, NORMAL_ROLE)

    def test_supervisor_group_is_created_by_migration(self):
        self.assertTrue(Group.objects.filter(name=SUPERVISOR_ROLE).exists())

    def test_supervisor_has_no_staff_or_superuser_privileges(self):
        self.supervisor.refresh_from_db()
        self.assertEqual(get_user_role(self.supervisor), SUPERVISOR_ROLE)
        self.assertFalse(self.supervisor.is_staff)
        self.assertFalse(self.supervisor.is_superuser)

        self.client.force_login(self.supervisor)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)

    @patch('divisas.views.fetch_yahoo_series')
    def test_supervisor_can_access_read_only_panels(self, fetch_yahoo_series):
        fetch_yahoo_series.return_value = (
            {
                'symbol': 'AAPL',
                'market': 'Estados Unidos',
                'instrument_name': 'Apple Inc.',
                'series': [
                    {
                        'datetime': '2026-01-02',
                        'open': 100.0,
                        'high': 103.0,
                        'low': 99.0,
                        'close': 102.0,
                        'currency': 'USD',
                        'currency_name': 'USD',
                    },
                    {
                        'datetime': '2026-01-03',
                        'open': 102.0,
                        'high': 105.0,
                        'low': 101.0,
                        'close': 104.0,
                        'currency': 'USD',
                        'currency_name': 'USD',
                    },
                ],
            },
            None,
        )
        self.client.force_login(self.supervisor)

        for route_name in (
            'admin_dashboard',
            'admin_stocks_panel',
            'admin_users_normal',
            'admin_users_supervisor',
            'admin_users_admin',
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)

    def test_supervisor_templates_hide_write_controls(self):
        self.client.force_login(self.supervisor)

        response = self.client.get(reverse('admin_users_normal'))
        self.assertContains(response, 'estrictamente de solo lectura')
        self.assertNotContains(response, 'Crear usuario')
        self.assertNotContains(response, '>Editar<', html=True)
        self.assertNotContains(response, '>Eliminar<', html=True)

        response = self.client.get(reverse('home'))
        self.assertNotContains(response, reverse('user_alert_create'))
        self.assertNotContains(response, reverse('delete_own_account'))

    def test_supervisor_write_routes_return_403_without_changes(self):
        self.client.force_login(self.supervisor)
        alert = ExchangeAlert.objects.create(
            user=self.supervisor,
            base_currency='USD',
            quote_currency='MXN',
            condition=ExchangeAlert.CONDITION_ABOVE,
            target_rate='20.000000',
        )
        user_count = User.objects.count()

        requests = (
            ('post', reverse('admin_users_normal'), {
                'username': 'creado_por_supervisor',
                'email': '',
                'password1': '123456Segura!',
                'password2': '123456Segura!',
            }),
            ('get', reverse('admin_user_edit', args=[self.normal_user.pk]), None),
            ('post', reverse('admin_user_edit', args=[self.normal_user.pk]), {
                'username': self.normal_user.username,
                'email': 'cambio@example.com',
                'role_name': SUPERVISOR_ROLE,
            }),
            ('post', reverse('admin_user_toggle_restriction', args=[self.normal_user.pk]), None),
            ('post', reverse('admin_user_delete', args=[self.normal_user.pk]), None),
            ('post', reverse('currency_favorite_toggle'), {'code': 'USD'}),
            ('post', reverse('user_alert_create'), {
                'base_currency': 'EUR',
                'quote_currency': 'USD',
                'condition': ExchangeAlert.CONDITION_ABOVE,
                'target_rate': '2.000000',
            }),
            ('post', reverse('user_alert_delete', args=[alert.pk]), None),
            ('post', reverse('user_alert_check'), None),
            ('post', reverse('user_alert_notification_mark_read', args=[999999]), None),
            ('post', reverse('user_alert_notification_mark_all_read'), None),
            ('post', reverse('admin_notification_mark_read', args=[999999]), None),
            ('post', reverse('admin_notification_mark_all_read'), None),
            ('post', reverse('delete_own_account'), None),
            ('post', reverse('signup'), {
                'username': 'registro_por_supervisor',
                'password1': 'NuevaClaveSegura123!',
                'password2': 'NuevaClaveSegura123!',
            }),
            ('post', reverse('home'), {'form_type': 'signup'}),
        )

        for method, url, data in requests:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, data=data or {})
                self.assertEqual(response.status_code, 403)

        self.assertEqual(User.objects.count(), user_count)
        self.assertFalse(FavoriteCurrency.objects.filter(user=self.supervisor).exists())
        alert.refresh_from_db()
        self.assertTrue(alert.is_active)
        self.assertTrue(User.objects.filter(pk=self.supervisor.pk).exists())

    def test_only_primary_admin_can_assign_or_remove_supervisor_role(self):
        self.client.force_login(self.secondary_admin)
        supervisor_count = User.objects.filter(groups__name=SUPERVISOR_ROLE).count()
        response = self.client.post(
            reverse('admin_users_supervisor'),
            {
                'username': 'supervisor_no_autorizado',
                'email': '',
                'password1': '123456Segura!',
                'password2': '123456Segura!',
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            User.objects.filter(groups__name=SUPERVISOR_ROLE).count(),
            supervisor_count,
        )

        response = self.client.get(reverse('admin_user_edit', args=[self.supervisor.pk]))
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse('admin_user_edit', args=[self.normal_user.pk]),
            {
                'username': self.normal_user.username,
                'email': 'normal@example.com',
                'role_name': SUPERVISOR_ROLE,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.normal_user.refresh_from_db()
        self.assertEqual(get_user_role(self.normal_user), NORMAL_ROLE)

        self.client.force_login(self.primary_admin)
        response = self.client.get(reverse('admin_user_edit', args=[self.normal_user.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<option value="SUPERVISOR">SUPERVISOR</option>', html=True)

        response = self.client.post(
            reverse('admin_user_edit', args=[self.normal_user.pk]),
            {
                'username': self.normal_user.username,
                'email': self.normal_user.email,
                'role_name': SUPERVISOR_ROLE,
            },
        )
        self.assertRedirects(response, reverse('admin_users_supervisor'))
        self.normal_user.refresh_from_db()
        self.assertEqual(get_user_role(self.normal_user), SUPERVISOR_ROLE)
        self.assertFalse(self.normal_user.is_staff)
        self.assertFalse(self.normal_user.is_superuser)

        response = self.client.post(
            reverse('admin_user_edit', args=[self.normal_user.pk]),
            {
                'username': self.normal_user.username,
                'email': self.normal_user.email,
                'role_name': NORMAL_ROLE,
            },
        )
        self.assertRedirects(response, reverse('admin_users_normal'))
        self.normal_user.refresh_from_db()
        self.assertEqual(get_user_role(self.normal_user), NORMAL_ROLE)

    def test_admin_and_normal_access_have_no_regressions(self):
        self.client.force_login(self.secondary_admin)
        self.assertEqual(self.client.get(reverse('admin_dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin_users_normal')).status_code, 200)

        self.secondary_admin.refresh_from_db()
        self.assertTrue(self.secondary_admin.is_staff)

        self.client.force_login(self.normal_user)
        self.assertEqual(self.client.get(reverse('admin_dashboard')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin_users_normal')).status_code, 403)
        self.normal_user.refresh_from_db()
        self.assertFalse(self.normal_user.is_staff)
        self.assertFalse(self.normal_user.is_superuser)
