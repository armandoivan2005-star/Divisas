from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

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
