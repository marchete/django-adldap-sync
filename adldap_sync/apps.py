from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class ADldapConfig(AppConfig):
    name = 'adldap_sync'
    verbose_name = _('Synchronization: AD/LDAP Information')
