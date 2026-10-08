import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.core.mail import send_mail
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    AdminNotification,
    ExchangeAlert,
    FavoriteCurrency,
    UserAlertNotification,
)


ADMIN_ROLE = 'ADMINISTRADOR'
NORMAL_ROLE = 'NORMAL'
TWELVEDATA_BASE_URL = 'https://api.twelvedata.com/time_series'
TWELVEDATA_SYMBOL_SEARCH_URL = 'https://api.twelvedata.com/symbol_search'
YAHOO_FINANCE_CHART_URLS = (
    'https://query1.finance.yahoo.com/v8/finance/chart',
    'https://query2.finance.yahoo.com/v8/finance/chart',
)
YAHOO_FINANCE_SEARCH_URL = 'https://query2.finance.yahoo.com/v1/finance/search'
FRANKFURTER_BASE_URL = 'https://api.frankfurter.app'
CURRENCY_CODE_RE = re.compile(r'^[A-Z]{3}$')
SYMBOL_QUERY_RE = re.compile(r'[^A-Z0-9:._/-]')
CURRENCY_DISPLAY_NAMES = {
    'USD': 'Dólar estadounidense',
    'MXN': 'Peso mexicano',
}
security_logger = logging.getLogger('divisas.security')


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def log_security_event(request, event, outcome='ok', details=''):
    username = request.user.username if request.user.is_authenticated else 'anon'
    security_logger.info(
        'event=%s outcome=%s user=%s ip=%s path=%s details=%s',
        event,
        outcome,
        username,
        get_client_ip(request),
        request.path,
        details,
    )


def forbidden_response(request, message, event='forbidden'):
    log_security_event(request, event, outcome='denied', details=message)
    return HttpResponseForbidden(message)


def sanitize_symbol_query(raw_value):
    value = (raw_value or '').strip().upper()
    sanitized = SYMBOL_QUERY_RE.sub('', value)
    return sanitized[:24]


class DashboardUserCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('El nombre de usuario ya existe.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Las contrasenas no coinciden.')
        return cleaned_data

    def save(self):
        return User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data.get('email') or '',
            password=self.cleaned_data['password1'],
        )


class DashboardUserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email']

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        qs = User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('El nombre de usuario ya existe.')
        return username


class RestrictedAwareAuthenticationForm(AuthenticationForm):
    restricted_message = 'Esta cuenta fue restringida por uso indebido, favor de contactar a un administrador.'

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                existing_user = User.objects.filter(username__iexact=username.strip()).first()
                if existing_user and not existing_user.is_active:
                    raise forms.ValidationError(self.restricted_message, code='inactive')
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data

    def confirm_login_allowed(self, user):
        if not user.is_active:
            raise forms.ValidationError(self.restricted_message, code='inactive')
        super().confirm_login_allowed(user)


def set_user_role(user, role_name):
    admin_group, _ = Group.objects.get_or_create(name=ADMIN_ROLE)
    normal_group, _ = Group.objects.get_or_create(name=NORMAL_ROLE)

    if role_name == ADMIN_ROLE:
        user.groups.set([admin_group])
        if not user.is_staff:
            user.is_staff = True
            user.save(update_fields=['is_staff'])
        return ADMIN_ROLE

    user.groups.set([normal_group])
    if user.is_staff:
        user.is_staff = False
        user.save(update_fields=['is_staff'])
    return NORMAL_ROLE


def apply_role_policy(user, force_normal=False):
    username = (user.username or '').strip().lower()
    if username == 'armando':
        return set_user_role(user, ADMIN_ROLE)
    if force_normal:
        return set_user_role(user, NORMAL_ROLE)
    if user.groups.filter(name=ADMIN_ROLE).exists():
        return set_user_role(user, ADMIN_ROLE)
    if user.groups.filter(name=NORMAL_ROLE).exists():
        return set_user_role(user, NORMAL_ROLE)
    return set_user_role(user, NORMAL_ROLE)


def is_admin_user(user):
    if not user.is_authenticated:
        return False
    return apply_role_policy(user) == ADMIN_ROLE


def is_primary_admin(user):
    return user.is_authenticated and (user.username or '').strip().lower() == 'armando'


def home(request):
    active_modal = request.GET.get('modal', '')
    next_url = request.GET.get('next') or request.POST.get('next') or ''
    restricted_login_username = ''
    restricted_login_message = ''
    user_role = None
    favorite_currency_codes = []
    user_exchange_alerts = []
    if request.user.is_authenticated:
        user_role = apply_role_policy(request.user)
        favorite_currency_codes = list(
            FavoriteCurrency.objects.filter(user=request.user).values_list('code', flat=True)
        )
        evaluate_user_alerts(request.user)
        user_exchange_alerts = list(
            ExchangeAlert.objects.filter(user=request.user).order_by('-created_at')
        )

    login_form = RestrictedAwareAuthenticationForm(request=request, prefix='login')
    signup_form = UserCreationForm(prefix='signup')

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'login':
            login_form = RestrictedAwareAuthenticationForm(request=request, data=request.POST, prefix='login')
            if login_form.is_valid():
                user = login_form.get_user()
                apply_role_policy(user)
                login(request, user)
                log_security_event(request, 'login', outcome='success', details=f'user={user.username}')
                return redirect(next_url or 'home')
            active_modal = 'login'
            submitted_username = (request.POST.get('login-username') or '').strip()
            log_security_event(
                request,
                'login',
                outcome='failed',
                details=f'user={submitted_username or "unknown"}',
            )
            login_errors = login_form.errors.as_data().get('__all__', [])
            if any(error.code == 'inactive' for error in login_errors):
                restricted_login_username = submitted_username
                restricted_login_message = RestrictedAwareAuthenticationForm.restricted_message
                active_modal = 'restricted'
                log_security_event(
                    request,
                    'login',
                    outcome='restricted',
                    details=f'user={restricted_login_username or "unknown"}',
                )

        elif form_type == 'signup':
            signup_form = UserCreationForm(request.POST, prefix='signup')
            if signup_form.is_valid():
                user = signup_form.save()
                apply_role_policy(user, force_normal=True)
                notify_admins_new_account(user)
                login(request, user)
                log_security_event(request, 'signup', outcome='success', details=f'user={user.username}')
                return redirect(next_url or 'home')
            active_modal = 'signup'
            log_security_event(request, 'signup', outcome='failed', details='validation_error')

    context = {
        'login_form': login_form,
        'signup_form': signup_form,
        'active_modal': active_modal,
        'next': next_url,
        'user_role': user_role,
        'is_admin_user': user_role == ADMIN_ROLE,
        'favorite_currency_codes': favorite_currency_codes,
        'user_exchange_alerts': user_exchange_alerts,
        'restricted_login_username': restricted_login_username,
        'restricted_login_message': restricted_login_message,
    }
    return render(request, 'home.html', context)


@login_required
def currency_favorite_toggle(request):
    if request.method != 'POST':
        return forbidden_response(request, 'Metodo no permitido.', event='favorite_toggle_method')

    payload = {}
    if request.content_type and 'application/json' in request.content_type:
        try:
            payload = json.loads((request.body or b'{}').decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}

    code = (payload.get('code') or request.POST.get('code') or '').strip().upper()
    action = (payload.get('action') or request.POST.get('action') or 'toggle').strip().lower()

    if not CURRENCY_CODE_RE.match(code):
        return JsonResponse({'ok': False, 'error': 'Codigo de moneda invalido.'}, status=400)

    if action not in ('add', 'remove', 'toggle'):
        return JsonResponse({'ok': False, 'error': 'Accion invalida.'}, status=400)

    favorite_qs = FavoriteCurrency.objects.filter(user=request.user, code=code)

    if action == 'add':
        FavoriteCurrency.objects.get_or_create(user=request.user, code=code)
        is_favorite = True
    elif action == 'remove':
        favorite_qs.delete()
        is_favorite = False
    else:
        if favorite_qs.exists():
            favorite_qs.delete()
            is_favorite = False
        else:
            FavoriteCurrency.objects.create(user=request.user, code=code)
            is_favorite = True

    favorites = list(
        FavoriteCurrency.objects.filter(user=request.user).values_list('code', flat=True)
    )
    return JsonResponse(
        {
            'ok': True,
            'code': code,
            'is_favorite': is_favorite,
            'favorites': favorites,
        }
    )


def login_page(request):
    next_url = request.GET.get('next') or request.POST.get('next') or ''
    restricted_login_message = ''
    submitted_username = ''
    form = RestrictedAwareAuthenticationForm(request=request, data=request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            user = form.get_user()
            apply_role_policy(user)
            login(request, user)
            log_security_event(request, 'login_page', outcome='success', details=f'user={user.username}')
            return redirect(next_url or 'home')

        submitted_username = (request.POST.get('username') or '').strip()
        log_security_event(
            request,
            'login_page',
            outcome='failed',
            details=f'user={submitted_username or "unknown"}',
        )
        login_errors = form.errors.as_data().get('__all__', [])
        if any(error.code == 'inactive' for error in login_errors):
            restricted_login_message = RestrictedAwareAuthenticationForm.restricted_message
            log_security_event(
                request,
                'login_page',
                outcome='restricted',
                details=f'user={submitted_username or "unknown"}',
            )

    return render(
        request,
        'registration/login.html',
        {
            'form': form,
            'next': next_url,
            'restricted_login_message': restricted_login_message,
            'submitted_username': submitted_username,
        },
    )


def signup(request):
    next_url = request.GET.get('next') or request.POST.get('next') or ''
    form = UserCreationForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            user = form.save()
            apply_role_policy(user, force_normal=True)
            notify_admins_new_account(user)
            login(request, user)
            log_security_event(request, 'signup_page', outcome='success', details=f'user={user.username}')
            return redirect(next_url or 'home')

        log_security_event(request, 'signup_page', outcome='failed', details='validation_error')

    return render(
        request,
        'registration/signup.html',
        {
            'form': form,
            'next': next_url,
        },
    )


def site_map(request):
    return render(request, 'site_map.html')


def custom_403(request, exception=None):
    return render(request, '403.html', status=403)


def custom_404(request, exception=None):
    return render(request, '404.html', status=404)


def custom_500(request):
    return render(request, '500.html', status=500)


def notify_admins_new_account(created_user):
    admins = list(
        User.objects.filter(groups__name=ADMIN_ROLE, is_active=True)
        .exclude(pk=created_user.pk)
        .distinct()
    )
    if not admins:
        return

    username = (created_user.username or '').strip() or f'ID {created_user.pk}'
    message = f'Se creo una nueva cuenta: {username}.'
    notifications = [AdminNotification(recipient=admin_user, message=message) for admin_user in admins]
    AdminNotification.objects.bulk_create(notifications)


def notify_admins_account_deleted(deleted_user):
    admins = list(
        User.objects.filter(groups__name=ADMIN_ROLE, is_active=True)
        .exclude(pk=deleted_user.pk)
        .distinct()
    )
    if not admins:
        return

    username = (deleted_user.username or '').strip() or f'ID {deleted_user.pk}'
    message = f'El usuario {username} elimino su cuenta.'
    notifications = [AdminNotification(recipient=admin_user, message=message) for admin_user in admins]
    AdminNotification.objects.bulk_create(notifications)


def redirect_back(request):
    return redirect(request.META.get('HTTP_REFERER') or 'home')


def fetch_frankfurter_latest(base_currency, symbols):
    symbols = [code for code in symbols if CURRENCY_CODE_RE.match(code)]
    if not CURRENCY_CODE_RE.match(base_currency) or not symbols:
        return None, 'Parametros invalidos para consulta de divisas.'

    params = {
        'from': base_currency,
        'to': ','.join(sorted(set(symbols))),
    }
    url = f"{FRANKFURTER_BASE_URL}/latest?{urlencode(params)}"
    request = Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, f'No se pudo consultar Frankfurter: {exc}'

    rates = payload.get('rates')
    if not isinstance(rates, dict):
        return None, 'Respuesta invalida de Frankfurter.'
    return rates, None


def evaluate_user_alerts(user):
    alerts = list(
        ExchangeAlert.objects.filter(user=user, is_active=True)
    )
    if not alerts:
        return {'triggered_now': 0, 'errors': []}

    by_base = defaultdict(list)
    for alert in alerts:
        by_base[alert.base_currency].append(alert)

    triggered_now = 0
    errors = []
    for base_currency, base_alerts in by_base.items():
        symbols = [alert.quote_currency for alert in base_alerts]
        rates, error = fetch_frankfurter_latest(base_currency, symbols)
        if error:
            errors.append(error)
            continue

        for alert in base_alerts:
            current_rate = rates.get(alert.quote_currency)
            if current_rate is None:
                continue

            current_rate_decimal = Decimal(str(current_rate))
            is_met = (
                current_rate_decimal >= alert.target_rate
                if alert.condition == ExchangeAlert.CONDITION_ABOVE
                else current_rate_decimal <= alert.target_rate
            )

            if is_met and not alert.is_triggered:
                comparator_text = 'subio por encima de' if alert.condition == ExchangeAlert.CONDITION_ABOVE else 'cayo por debajo de'
                message = (
                    f'Alerta {alert.base_currency}/{alert.quote_currency}: '
                    f'{comparator_text} {alert.target_rate} (actual {current_rate_decimal}).'
                )
                UserAlertNotification.objects.create(
                    recipient=user,
                    alert=alert,
                    message=message,
                )
                if settings.ALERT_EMAILS_ENABLED and user.email:
                    subject = f'Alerta de divisas activada: {alert.base_currency}/{alert.quote_currency}'
                    body = (
                        f'Hola {user.username},\n\n'
                        f'Se activo tu alerta de divisas.\n'
                        f'Par: {alert.base_currency}/{alert.quote_currency}\n'
                        f'Condicion: {comparator_text} {alert.target_rate}\n'
                        f'Valor actual: {current_rate_decimal}\n\n'
                        'Este aviso se envia una vez por cruce de umbral. '
                        'Si el valor regresa y vuelve a cruzar, recibirias otro aviso.\n'
                    )
                    try:
                        send_mail(
                            subject=subject,
                            message=body,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[user.email],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
                alert.is_triggered = True
                alert.last_triggered_at = timezone.now()
                alert.save(update_fields=['is_triggered', 'last_triggered_at'])
                triggered_now += 1
            elif not is_met and alert.is_triggered:
                alert.is_triggered = False
                alert.save(update_fields=['is_triggered'])

    return {'triggered_now': triggered_now, 'errors': errors}


@login_required
def admin_notification_mark_read(request, notification_id):
    if request.method != 'POST':
        return forbidden_response(request, 'Metodo no permitido.', event='admin_notification_method')
    if not is_admin_user(request.user):
        return forbidden_response(request, 'Acceso solo para administradores.', event='admin_notification_access')

    notification = get_object_or_404(AdminNotification, pk=notification_id, recipient=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=['is_read'])
    return redirect_back(request)


@login_required
def admin_notification_mark_all_read(request):
    if request.method != 'POST':
        return forbidden_response(request, 'Metodo no permitido.', event='admin_notification_all_method')
    if not is_admin_user(request.user):
        return forbidden_response(request, 'Acceso solo para administradores.', event='admin_notification_all_access')

    AdminNotification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect_back(request)


@login_required
def user_alert_create(request):
    if request.method != 'POST':
        return forbidden_response(request, 'Metodo no permitido.', event='user_alert_create_method')

    base_currency = (request.POST.get('base_currency') or '').strip().upper()
    quote_currency = (request.POST.get('quote_currency') or '').strip().upper()
    condition = (request.POST.get('condition') or '').strip().lower()
    target_rate_raw = (request.POST.get('target_rate') or '').strip()

    if not CURRENCY_CODE_RE.match(base_currency) or not CURRENCY_CODE_RE.match(quote_currency):
        messages.error(request, 'Selecciona codigos de moneda validos (ej. USD, MXN).')
        return redirect('home')
    if base_currency == quote_currency:
        messages.error(request, 'La moneda base y la moneda objetivo deben ser diferentes.')
        return redirect('home')
    if condition not in (ExchangeAlert.CONDITION_ABOVE, ExchangeAlert.CONDITION_BELOW):
        messages.error(request, 'Selecciona una condicion valida para la alerta.')
        return redirect('home')

    try:
        target_rate = Decimal(target_rate_raw)
    except InvalidOperation:
        messages.error(request, 'La tasa objetivo debe ser un numero valido.')
        return redirect('home')

    if target_rate <= 0:
        messages.error(request, 'La tasa objetivo debe ser mayor a 0.')
        return redirect('home')

    existing = ExchangeAlert.objects.filter(
        user=request.user,
        base_currency=base_currency,
        quote_currency=quote_currency,
        condition=condition,
        target_rate=target_rate,
        is_active=True,
    ).first()
    if existing:
        messages.info(request, 'Ya tienes una alerta activa con esos mismos parametros.')
        return redirect('home')

    ExchangeAlert.objects.create(
        user=request.user,
        base_currency=base_currency,
        quote_currency=quote_currency,
        condition=condition,
        target_rate=target_rate,
        is_active=True,
    )
    log_security_event(
        request,
        'user_alert_create',
        outcome='success',
        details=f'pair={base_currency}/{quote_currency} condition={condition}',
    )
    messages.success(request, f'Alerta creada para {base_currency}/{quote_currency}.')
    return redirect('home')


@login_required
def user_alert_delete(request, alert_id):
    if request.method != 'POST':
        return forbidden_response(request, 'Metodo no permitido.', event='user_alert_delete_method')

    alert = get_object_or_404(ExchangeAlert, pk=alert_id, user=request.user)
    alert.is_active = False
    alert.save(update_fields=['is_active'])
    log_security_event(request, 'user_alert_delete', outcome='success', details=f'alert_id={alert_id}')
    messages.success(request, 'Alerta desactivada correctamente.')
    return redirect('home')


@login_required
def user_alert_check(request):
    if request.method != 'POST':
        return forbidden_response(request, 'Metodo no permitido.', event='user_alert_check_method')

    result = evaluate_user_alerts(request.user)
    unread_count = UserAlertNotification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse(
        {
            'ok': True,
            'triggered_now': result['triggered_now'],
            'unread_count': unread_count,
            'has_errors': bool(result['errors']),
        }
    )


@login_required
def user_alert_notification_mark_read(request, notification_id):
    if request.method != 'POST':
        return forbidden_response(request, 'Metodo no permitido.', event='user_alert_notification_method')

    notification = get_object_or_404(
        UserAlertNotification,
        pk=notification_id,
        recipient=request.user,
    )
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=['is_read'])
    return redirect_back(request)


@login_required
def user_alert_notification_mark_all_read(request):
    if request.method != 'POST':
        return forbidden_response(request, 'Metodo no permitido.', event='user_alert_notification_all_method')

    UserAlertNotification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect_back(request)


@login_required
def delete_own_account(request):
    if request.method != 'POST':
        return forbidden_response(request, 'Metodo no permitido.', event='delete_own_account_method')

    current_user = request.user
    if (current_user.username or '').strip().lower() == 'armando':
        messages.error(request, 'La cuenta armando no puede eliminarse desde este panel.')
        return redirect('home')

    username = current_user.username
    notify_admins_account_deleted(current_user)
    logout(request)
    current_user.delete()
    log_security_event(request, 'delete_own_account', outcome='success', details=f'user={username}')
    messages.success(request, f'La cuenta {username} fue eliminada correctamente.')
    return redirect('home')


def fetch_twelvedata_series(symbol, api_key):
    params = {
        'symbol': symbol,
        'interval': '1day',
        'outputsize': 60,
        'apikey': api_key,
    }
    url = f"{TWELVEDATA_BASE_URL}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        details = ''
        try:
            body = exc.read().decode('utf-8')
            payload = json.loads(body)
            details = payload.get('message') or payload.get('status') or body
        except (json.JSONDecodeError, UnicodeDecodeError):
            details = str(exc)
        return None, f'No se pudo consultar TwelveData ({exc.code}): {details}'
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, f'No se pudo consultar TwelveData: {exc}'

    if data.get('status') == 'error':
        return None, data.get('message', 'Error desconocido de TwelveData.')

    values = data.get('values', [])
    if not values:
        return None, 'No se encontraron datos para ese simbolo.'

    metadata = data.get('meta') if isinstance(data.get('meta'), dict) else {}
    currency = str(metadata.get('currency') or '').strip().upper()
    if not currency:
        normalized_symbol = (symbol or '').strip().upper()
        if normalized_symbol.endswith((':BMV', ':BIVA')):
            currency = 'MXN'
    currency = currency or 'N/D'
    currency_name = CURRENCY_DISPLAY_NAMES.get(currency, currency)

    parsed = []
    for row in reversed(values):
        try:
            parsed.append(
                {
                    'datetime': row.get('datetime'),
                    'open': float(row.get('open')),
                    'high': float(row.get('high')),
                    'low': float(row.get('low')),
                    'close': float(row.get('close')),
                    'currency': currency,
                    'currency_name': currency_name,
                }
            )
        except (TypeError, ValueError):
            continue

    if not parsed:
        return None, 'Los datos recibidos no tienen el formato esperado.'

    return parsed, None


def yahoo_market_name(symbol, exchange_name=''):
    normalized_symbol = (symbol or '').strip().upper()
    normalized_exchange = (exchange_name or '').strip().upper()
    if normalized_symbol.endswith('.MX') or normalized_exchange in ('MEX', 'MEXICO'):
        return 'Bolsa Mexicana de Valores'
    if normalized_exchange in ('NMS', 'NGM', 'NCM', 'NYQ', 'PCX', 'ASE', 'BTS'):
        return 'Estados Unidos'
    return exchange_name or 'Mercado no identificado'


def fetch_yahoo_series(symbol):
    params = {
        'range': '3mo',
        'interval': '1d',
        'events': 'history',
        'includeAdjustedClose': 'true',
    }
    data = None
    request_errors = []
    for base_url in YAHOO_FINANCE_CHART_URLS:
        url = f"{base_url}/{quote(symbol, safe='')}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            },
        )
        try:
            with urlopen(request, timeout=12) as response:
                data = json.loads(response.read().decode('utf-8'))
            break
        except HTTPError as exc:
            request_errors.append(f'HTTP {exc.code}')
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            request_errors.append(str(exc))

    if data is None:
        details = '; '.join(request_errors) or 'sin respuesta'
        return None, f'No se pudo consultar Yahoo Finance ({details}).'

    chart = data.get('chart') if isinstance(data, dict) else None
    if not isinstance(chart, dict):
        return None, 'Yahoo Finance devolvio una respuesta no valida.'
    if chart.get('error'):
        error = chart['error']
        description = error.get('description') if isinstance(error, dict) else str(error)
        return None, description or 'Yahoo Finance no encontro el simbolo.'

    results = chart.get('result') or []
    if not results:
        return None, 'Yahoo Finance no encontro datos para ese simbolo.'

    result = results[0]
    metadata = result.get('meta') if isinstance(result.get('meta'), dict) else {}
    timestamps = result.get('timestamp') or []
    indicators = result.get('indicators') if isinstance(result.get('indicators'), dict) else {}
    quotes = indicators.get('quote') or []
    quote_rows = quotes[0] if quotes and isinstance(quotes[0], dict) else {}
    currency = str(metadata.get('currency') or '').strip().upper()
    if not currency and (symbol or '').upper().endswith('.MX'):
        currency = 'MXN'
    currency = currency or 'N/D'
    currency_name = CURRENCY_DISPLAY_NAMES.get(currency, currency)

    parsed = []
    opens = quote_rows.get('open') or []
    highs = quote_rows.get('high') or []
    lows = quote_rows.get('low') or []
    closes = quote_rows.get('close') or []
    for index, timestamp in enumerate(timestamps):
        try:
            open_value = opens[index]
            high_value = highs[index]
            low_value = lows[index]
            close_value = closes[index]
            if None in (open_value, high_value, low_value, close_value):
                continue
            parsed.append(
                {
                    'datetime': datetime.fromtimestamp(timestamp, datetime_timezone.utc).date().isoformat(),
                    'open': round(float(open_value), 6),
                    'high': round(float(high_value), 6),
                    'low': round(float(low_value), 6),
                    'close': round(float(close_value), 6),
                    'currency': currency,
                    'currency_name': currency_name,
                }
            )
        except (IndexError, TypeError, ValueError, OSError):
            continue

    if not parsed:
        return None, 'Yahoo Finance no devolvio precios diarios utilizables.'

    resolved_symbol = str(metadata.get('symbol') or symbol).strip().upper()
    exchange_name = str(metadata.get('exchangeName') or '').strip()
    return {
        'series': parsed[-60:],
        'symbol': resolved_symbol,
        'currency': currency,
        'currency_name': currency_name,
        'market': yahoo_market_name(resolved_symbol, exchange_name),
        'instrument_name': str(metadata.get('longName') or metadata.get('shortName') or '').strip(),
    }, None


def fetch_yahoo_symbol_search(query):
    params = {
        'q': query,
        'quotesCount': 10,
        'newsCount': 0,
        'enableFuzzyQuery': 'false',
    }
    url = f"{YAHOO_FINANCE_SEARCH_URL}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []
    rows = data.get('quotes', []) if isinstance(data, dict) else []
    return rows if isinstance(rows, list) else []


def build_yahoo_symbol_candidates(raw_query, search_rows=None):
    query = (raw_query or '').strip().upper()
    candidates = []

    def add(symbol_value):
        normalized = (symbol_value or '').strip().upper()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    if query.endswith((':BMV', ':BIVA')):
        add(f'{query.rsplit(":", 1)[0]}.MX')
    else:
        add(query)

    for row in search_rows or []:
        if not isinstance(row, dict) or (row.get('quoteType') or '').upper() not in ('EQUITY', 'ETF'):
            continue
        add(row.get('symbol'))

    if query and '.' not in query and ':' not in query:
        add(f'{query}.MX')

    return candidates


def fetch_twelvedata_symbol_search(query, api_key):
    params = {
        'symbol': query,
        'outputsize': 20,
        'apikey': api_key,
    }
    url = f"{TWELVEDATA_SYMBOL_SEARCH_URL}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception:
        return []

    rows = data.get('data', [])
    if not isinstance(rows, list):
        return []
    return rows


def build_symbol_candidates(raw_query, search_rows):
    query = (raw_query or '').strip().upper()
    candidates = []

    def add(symbol_value):
        symbol_value = (symbol_value or '').strip().upper()
        if not symbol_value:
            return
        if symbol_value not in candidates:
            candidates.append(symbol_value)

    # Direct symbol attempt first only if it looks like a ticker (not a full company name with spaces).
    ticker_like = query and all(ch.isalnum() or ch in '._:/-' for ch in query)
    if ticker_like:
        add(query)

    # Add search-based candidates (useful when user writes company name, e.g. "grupo bimbo").
    for row in search_rows:
        symbol_value = row.get('symbol')
        exchange = (row.get('exchange') or '').upper()
        mic_code = (row.get('mic_code') or '').upper()
        if exchange in ('BMV', 'BIVA') or mic_code == 'XMEX' or row.get('country') == 'Mexico':
            add(symbol_value)
            if symbol_value and ':' not in symbol_value:
                add(f'{symbol_value}:BMV')
                add(f'{symbol_value}:BIVA')

    # If user typed symbol without exchange suffix, try Mexican exchange variants.
    if ticker_like and ':' not in query:
        add(f'{query}:BMV')
        add(f'{query}:BIVA')

    return candidates


@login_required
def admin_dashboard(request):
    if not is_admin_user(request.user):
        return forbidden_response(request, 'Acceso solo para administradores.', event='admin_dashboard_access')

    context = {
        'normal_count': User.objects.filter(groups__name=NORMAL_ROLE).count(),
        'admin_count': User.objects.filter(groups__name=ADMIN_ROLE).count(),
        'is_primary_admin': is_primary_admin(request.user),
    }
    return render(request, 'admin/dashboard.html', context)


@login_required
def admin_stocks_panel(request):
    if not is_admin_user(request.user):
        return forbidden_response(request, 'Acceso solo para administradores.', event='admin_stocks_access')

    api_key = settings.TWELVEDATA_API_KEY
    raw_symbol = request.GET.get('symbol') or 'AAPL'
    symbol = sanitize_symbol_query(raw_symbol) or 'AAPL'
    if raw_symbol.strip().upper() != symbol:
        log_security_event(request, 'symbol_sanitization', outcome='normalized', details=f'input={raw_symbol}')

    context = {
        'symbol': symbol.upper(),
        'api_key_configured': bool(api_key),
    }

    # Direct ticker attempts avoid an unnecessary Yahoo search request and reduce rate-limit failures.
    candidates = build_yahoo_symbol_candidates(symbol)
    if not candidates:
        context['api_error'] = (
            'No se encontro un simbolo valido para esa busqueda. '
            'Prueba con un ticker de EE. UU. (ej. AAPL) o Mexico (ej. WALMEX.MX).'
        )
        return render(request, 'admin/stocks_panel.html', context)

    yahoo_error = None
    fallback_error = None
    selected_symbol = None
    series = None
    provider = None
    instrument_market = None
    instrument_name = None

    attempted_candidates = set()
    for candidate in candidates:
        attempted_candidates.add(candidate)
        data, error = fetch_yahoo_series(candidate)
        if not error:
            selected_symbol = data['symbol']
            series = data['series']
            provider = 'Yahoo Finance'
            instrument_market = data['market']
            instrument_name = data['instrument_name']
            break
        yahoo_error = error

    # Search only after direct symbols fail; it can recover aliases without penalizing normal requests.
    if not series:
        search_rows = fetch_yahoo_symbol_search(symbol)
        context['mexican_matches'] = [
            row for row in search_rows
            if (
                str(row.get('symbol') or '').upper().endswith('.MX')
                or (row.get('exchange') or '').upper() in ('MEX', 'BMV', 'BIVA')
            )
        ][:8]
        for candidate in build_yahoo_symbol_candidates(symbol, search_rows):
            if candidate in attempted_candidates:
                continue
            attempted_candidates.add(candidate)
            data, error = fetch_yahoo_series(candidate)
            if not error:
                selected_symbol = data['symbol']
                series = data['series']
                provider = 'Yahoo Finance'
                instrument_market = data['market']
                instrument_name = data['instrument_name']
                break
            yahoo_error = error

    # TwelveData remains an optional fallback for temporary Yahoo failures.
    if not series and api_key:
        fallback_query = symbol
        if symbol.endswith('.MX'):
            fallback_query = f'{symbol[:-3]}:BMV'
        fallback_search_rows = fetch_twelvedata_symbol_search(fallback_query, api_key)
        for candidate in build_symbol_candidates(fallback_query, fallback_search_rows):
            data, error = fetch_twelvedata_series(candidate, api_key)
            if not error:
                selected_symbol = candidate
                series = data
                provider = 'TwelveData (respaldo)'
                instrument_market = (
                    'Bolsa Mexicana de Valores'
                    if candidate.endswith((':BMV', ':BIVA'))
                    else 'Estados Unidos'
                )
                break
            fallback_error = error

    if not series:
        error_parts = [f"Yahoo Finance: {yahoo_error or 'no se encontraron datos.'}"]
        if api_key and fallback_error:
            error_parts.append(f'TwelveData (respaldo): {fallback_error}')
        context['api_error'] = ' '.join(error_parts) + (
            ' Prueba con AAPL para Estados Unidos o con WALMEX.MX para la Bolsa Mexicana.'
        )
        return render(request, 'admin/stocks_panel.html', context)

    latest = series[-1]
    first = series[0]
    max_high = max(series, key=lambda row: row['high'])
    min_low = min(series, key=lambda row: row['low'])
    period_change_pct = ((latest['close'] - first['close']) / first['close']) * 100 if first['close'] else 0

    context.update(
        {
            'resolved_symbol': selected_symbol,
            'data_provider': provider,
            'instrument_market': instrument_market,
            'instrument_name': instrument_name,
            'series': list(reversed(series[-30:])),
            'latest': latest,
            'max_high': max_high,
            'min_low': min_low,
            'period_change_pct': round(period_change_pct, 2),
            'instrument_currency': latest['currency'],
            'instrument_currency_name': latest['currency_name'],
            'chart_labels': json.dumps([row['datetime'] for row in series[-30:]]),
            'chart_high': json.dumps([row['high'] for row in series[-30:]]),
            'chart_low': json.dumps([row['low'] for row in series[-30:]]),
            'chart_close': json.dumps([row['close'] for row in series[-30:]]),
        }
    )
    return render(request, 'admin/stocks_panel.html', context)


@login_required
def admin_users_by_role(request, role_name):
    if not is_admin_user(request.user):
        return forbidden_response(request, 'Acceso solo para administradores.', event='admin_users_access')

    if role_name not in (NORMAL_ROLE, ADMIN_ROLE):
        return forbidden_response(request, 'Rol no valido.', event='admin_users_role')

    primary_admin = is_primary_admin(request.user)
    can_create = primary_admin
    can_edit = role_name == NORMAL_ROLE or primary_admin
    can_delete = primary_admin

    create_form = DashboardUserCreateForm() if can_create else None
    if request.method == 'POST':
        if not can_create:
            return forbidden_response(request, 'No tienes permisos para crear usuarios en esta seccion.', event='admin_users_create')
        create_form = DashboardUserCreateForm(request.POST)
        if create_form.is_valid():
            user = create_form.save()
            set_user_role(user, role_name)
            messages.success(request, f'Usuario {user.username} creado en rol {role_name}.')
            if role_name == NORMAL_ROLE:
                return redirect('admin_users_normal')
            return redirect('admin_users_admin')

    users = User.objects.filter(groups__name=role_name).order_by('username')
    context = {
        'role_name': role_name,
        'users': users,
        'create_form': create_form,
        'can_create': can_create,
        'can_edit': can_edit,
        'can_delete': can_delete,
        'is_primary_admin': primary_admin,
    }
    return render(request, 'admin/users_list.html', context)


@login_required
def admin_users_normal(request):
    return admin_users_by_role(request, NORMAL_ROLE)


@login_required
def admin_users_admin(request):
    return admin_users_by_role(request, ADMIN_ROLE)


def redirect_to_users_list_by_role(role_name):
    if role_name == ADMIN_ROLE:
        return redirect('admin_users_admin')
    return redirect('admin_users_normal')


@login_required
def admin_user_edit(request, user_id):
    if not is_admin_user(request.user):
        return forbidden_response(request, 'Acceso solo para administradores.', event='admin_user_edit_access')

    target_user = get_object_or_404(User, pk=user_id)
    apply_role_policy(target_user)
    role_name = ADMIN_ROLE if target_user.groups.filter(name=ADMIN_ROLE).exists() else NORMAL_ROLE
    original_role = role_name
    primary_admin = is_primary_admin(request.user)
    if role_name == ADMIN_ROLE and not primary_admin:
        return forbidden_response(request, 'Solo armando puede editar administradores.', event='admin_user_edit_role')
    can_change_role = primary_admin and (target_user.username or '').strip().lower() != 'armando'

    if request.method == 'POST':
        form = DashboardUserUpdateForm(request.POST, instance=target_user)
        if form.is_valid():
            form.save()
            selected_role = original_role
            if can_change_role:
                requested_role = request.POST.get('role_name', original_role)
                if requested_role in (ADMIN_ROLE, NORMAL_ROLE):
                    selected_role = requested_role

            if selected_role == ADMIN_ROLE:
                set_user_role(target_user, ADMIN_ROLE)
                messages.success(request, 'Usuario actualizado como administrador.')
                return redirect('admin_users_admin')
            set_user_role(target_user, NORMAL_ROLE)
            messages.success(request, 'Usuario actualizado como normal.')
            return redirect('admin_users_normal')
    else:
        form = DashboardUserUpdateForm(instance=target_user)

    return render(
        request,
        'admin/user_edit.html',
        {
            'form': form,
            'target_user': target_user,
            'role_name': original_role,
            'can_change_role': can_change_role,
            'can_manage_restriction': is_primary_admin(request.user),
            'role_options': [NORMAL_ROLE, ADMIN_ROLE],
        },
    )


@login_required
def admin_user_toggle_restriction(request, user_id):
    if request.method != 'POST':
        return forbidden_response(request, 'Metodo no permitido.', event='admin_user_toggle_method')
    if not is_admin_user(request.user):
        return forbidden_response(request, 'Acceso solo para administradores.', event='admin_user_toggle_access')
    if not is_primary_admin(request.user):
        return forbidden_response(request, 'Solo armando puede restringir o reactivar cuentas.', event='admin_user_toggle_role')

    target_user = get_object_or_404(User, pk=user_id)
    apply_role_policy(target_user)
    role_name = ADMIN_ROLE if target_user.groups.filter(name=ADMIN_ROLE).exists() else NORMAL_ROLE

    if (target_user.username or '').strip().lower() == 'armando':
        messages.error(request, 'La cuenta armando no puede restringirse.')
        return redirect_to_users_list_by_role(role_name)

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])

    if target_user.is_active:
        messages.success(request, f'La cuenta {target_user.username} fue reactivada.')
        log_security_event(request, 'admin_user_reactivate', outcome='success', details=f'user={target_user.username}')
    else:
        messages.success(request, f'La cuenta {target_user.username} fue restringida.')
        log_security_event(request, 'admin_user_restrict', outcome='success', details=f'user={target_user.username}')
    return redirect_to_users_list_by_role(role_name)


@login_required
def admin_user_delete(request, user_id):
    if not is_admin_user(request.user):
        return forbidden_response(request, 'Acceso solo para administradores.', event='admin_user_delete_access')
    if request.method != 'POST':
        return forbidden_response(request, 'Metodo no permitido.', event='admin_user_delete_method')

    target_user = get_object_or_404(User, pk=user_id)
    apply_role_policy(target_user)
    role_name = ADMIN_ROLE if target_user.groups.filter(name=ADMIN_ROLE).exists() else NORMAL_ROLE
    if not is_primary_admin(request.user):
        return forbidden_response(request, 'Solo armando puede eliminar usuarios desde el dashboard.', event='admin_user_delete_role')

    if target_user == request.user:
        messages.error(request, 'No puedes eliminar tu propio usuario administrador.')
        if role_name == ADMIN_ROLE:
            return redirect('admin_users_admin')
        return redirect('admin_users_normal')

    username = target_user.username
    target_user.delete()
    log_security_event(request, 'admin_user_delete', outcome='success', details=f'user={username}')
    messages.success(request, f'Usuario {username} eliminado.')

    if role_name == ADMIN_ROLE:
        return redirect('admin_users_admin')
    return redirect('admin_users_normal')
