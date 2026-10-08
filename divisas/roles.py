from django.contrib.auth.models import Group


ADMIN_ROLE = 'ADMINISTRADOR'
SUPERVISOR_ROLE = 'SUPERVISOR'
NORMAL_ROLE = 'NORMAL'
ROLE_NAMES = (ADMIN_ROLE, SUPERVISOR_ROLE, NORMAL_ROLE)


def is_primary_admin(user):
    return user.is_authenticated and (user.username or '').strip().lower() == 'armando'


def get_user_role(user):
    if not user.is_authenticated:
        return None
    if is_primary_admin(user):
        return ADMIN_ROLE
    if user.groups.filter(name=ADMIN_ROLE).exists():
        return ADMIN_ROLE
    if user.groups.filter(name=SUPERVISOR_ROLE).exists():
        return SUPERVISOR_ROLE
    return NORMAL_ROLE


def set_user_role(user, role_name):
    if role_name not in ROLE_NAMES:
        raise ValueError('Rol no valido.')

    groups = {
        name: Group.objects.get_or_create(name=name)[0]
        for name in ROLE_NAMES
    }
    user.groups.set([groups[role_name]])

    update_fields = []
    if role_name == ADMIN_ROLE:
        if not user.is_staff:
            user.is_staff = True
            update_fields.append('is_staff')
    elif role_name == SUPERVISOR_ROLE:
        if user.is_staff:
            user.is_staff = False
            update_fields.append('is_staff')
        if user.is_superuser:
            user.is_superuser = False
            update_fields.append('is_superuser')
    elif user.is_staff:
        user.is_staff = False
        update_fields.append('is_staff')

    if update_fields:
        user.save(update_fields=update_fields)
    return role_name


def apply_role_policy(user, force_normal=False):
    if is_primary_admin(user):
        return set_user_role(user, ADMIN_ROLE)
    if force_normal:
        return set_user_role(user, NORMAL_ROLE)

    role_name = get_user_role(user)
    return set_user_role(user, role_name)


def is_admin_user(user):
    if not user.is_authenticated:
        return False
    return apply_role_policy(user) == ADMIN_ROLE


def is_supervisor_user(user):
    if not user.is_authenticated:
        return False
    return apply_role_policy(user) == SUPERVISOR_ROLE


def can_access_dashboard(user):
    if not user.is_authenticated:
        return False
    return apply_role_policy(user) in (ADMIN_ROLE, SUPERVISOR_ROLE)
