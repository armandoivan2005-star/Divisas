"""
URL configuration for practica01 project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_page, name='login'),
    path('mapa-del-sitio/', views.site_map, name='site_map'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('cuenta/eliminar/', views.delete_own_account, name='delete_own_account'),
    path('notificaciones/<int:notification_id>/leer/', views.admin_notification_mark_read, name='admin_notification_mark_read'),
    path('notificaciones/leer-todas/', views.admin_notification_mark_all_read, name='admin_notification_mark_all_read'),
    path('alertas/crear/', views.user_alert_create, name='user_alert_create'),
    path('alertas/<int:alert_id>/eliminar/', views.user_alert_delete, name='user_alert_delete'),
    path('alertas/verificar/', views.user_alert_check, name='user_alert_check'),
    path('alertas/notificaciones/<int:notification_id>/leer/', views.user_alert_notification_mark_read, name='user_alert_notification_mark_read'),
    path('alertas/notificaciones/leer-todas/', views.user_alert_notification_mark_all_read, name='user_alert_notification_mark_all_read'),
    path('favoritos/divisas/', views.currency_favorite_toggle, name='currency_favorite_toggle'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/acciones/', views.admin_stocks_panel, name='admin_stocks_panel'),
    path('dashboard/usuarios/normales/', views.admin_users_normal, name='admin_users_normal'),
    path('dashboard/usuarios/administradores/', views.admin_users_admin, name='admin_users_admin'),
    path('dashboard/usuarios/<int:user_id>/editar/', views.admin_user_edit, name='admin_user_edit'),
    path('dashboard/usuarios/<int:user_id>/restriccion/', views.admin_user_toggle_restriction, name='admin_user_toggle_restriction'),
    path('dashboard/usuarios/<int:user_id>/eliminar/', views.admin_user_delete, name='admin_user_delete'),

]

handler403 = 'divisas.views.custom_403'
handler404 = 'divisas.views.custom_404'
handler500 = 'divisas.views.custom_500'
