from django.urls import reverse

from .models import AdminNotification, UserAlertNotification
from .roles import ADMIN_ROLE, SUPERVISOR_ROLE, get_user_role


def admin_notifications(request):
    if not request.user.is_authenticated:
        return {
            'sidebar_notifications': [],
            'sidebar_unread_notifications': 0,
            'sidebar_user_alert_notifications': [],
            'sidebar_user_alert_unread': 0,
        }

    user_alert_notifications = list(
        UserAlertNotification.objects.filter(recipient=request.user).order_by('-created_at')[:10]
    )
    user_alert_unread = UserAlertNotification.objects.filter(
        recipient=request.user,
        is_read=False,
    ).count()

    notifications = []
    unread_count = 0
    if get_user_role(request.user) == ADMIN_ROLE:
        notifications = list(
            AdminNotification.objects.filter(recipient=request.user).order_by('-created_at')[:10]
        )
        unread_count = AdminNotification.objects.filter(recipient=request.user, is_read=False).count()

    return {
        'sidebar_notifications': notifications,
        'sidebar_unread_notifications': unread_count,
        'sidebar_user_alert_notifications': user_alert_notifications,
        'sidebar_user_alert_unread': user_alert_unread,
    }


URL_LABELS = {
    'home': 'Inicio',
    'login': 'Login',
    'signup': 'Registro',
    'admin_dashboard': 'Dashboard',
    'admin_stocks_panel': 'Dashboard acciones',
    'admin_users_normal': 'Usuarios normales',
    'admin_users_supervisor': 'Usuarios supervisores',
    'admin_users_admin': 'Usuarios administradores',
    'admin_user_edit': 'Editar usuario',
    'site_map': 'Mapa del sitio',
}

URL_PARENTS = {
    'admin_stocks_panel': ['admin_dashboard'],
    'admin_users_normal': ['admin_dashboard'],
    'admin_users_supervisor': ['admin_dashboard'],
    'admin_users_admin': ['admin_dashboard'],
    'admin_user_edit': ['admin_dashboard'],
}


def navigation_metadata(request):
    resolver_match = getattr(request, 'resolver_match', None)
    current_name = resolver_match.url_name if resolver_match else None

    breadcrumbs = [{'label': 'Inicio', 'url': reverse('home')}]
    if current_name and current_name != 'home':
        for parent_name in URL_PARENTS.get(current_name, []):
            breadcrumbs.append(
                {
                    'label': URL_LABELS.get(parent_name, parent_name),
                    'url': reverse(parent_name),
                }
            )
        breadcrumbs.append(
            {
                'label': URL_LABELS.get(current_name, current_name),
                'url': None,
            }
        )

    sitemap_links = [
        {'label': 'Inicio', 'url': reverse('home')},
        {'label': 'Login', 'url': reverse('login')},
        {'label': 'Registro', 'url': reverse('signup')},
        {'label': 'Dashboard', 'url': reverse('admin_dashboard')},
        {'label': 'Mapa del sitio', 'url': reverse('site_map')},
    ]

    role_name = get_user_role(request.user)
    return {
        'breadcrumbs': breadcrumbs,
        'sitemap_links': sitemap_links,
        'current_user_role': role_name,
        'can_access_dashboard': role_name in (ADMIN_ROLE, SUPERVISOR_ROLE),
        'is_application_admin': role_name == ADMIN_ROLE,
        'is_supervisor': role_name == SUPERVISOR_ROLE,
    }
