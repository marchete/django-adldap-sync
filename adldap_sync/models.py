import logging
from datetime import datetime

import pytz
from django.db import models
from django.utils.translation import ugettext as _

logger = logging.getLogger(__name__)

SYNC_TYPES = (
    ('Full', _('Full')),
    ('Incremental', _('Incremental')),
    )


class ADldap_Sync(models.Model):
    #Minimal fields to be able to use incremental Synchronization
    ldap_sync_uri = models.CharField(verbose_name=_('AD/LDAP Sync URI'), max_length=500, unique=True)
    whenchanged = models.DateTimeField(verbose_name=_('Last Update (UTC)'), default=datetime(1990, 1, 1, 1, 1, 1, 657692, tzinfo=pytz.UTC))
    #Make always the first synchronization a full one
    syncs_to_full = models.IntegerField(verbose_name=_('Incremental Syncs until Full Sync'), default=0)

    #Statistics
    total_syncs = models.IntegerField(verbose_name=_('Total Syncs'), default=0)
    last_sync_type = models.CharField(verbose_name=_('Last Sync Type'), max_length=100, choices=SYNC_TYPES, default=SYNC_TYPES[1])

    last_sync_user_total = models.IntegerField(verbose_name=_('Last Sync: Users Found in LDAP'), default=0)
    last_sync_user_added = models.IntegerField(verbose_name=_('Last Sync: Users Added'), default=0)
    last_sync_user_updated = models.IntegerField(verbose_name=_('Last Sync: Users Updated'), default=0)
    last_sync_user_deleted = models.IntegerField(verbose_name=_('Last Sync: Users Deleted'), default=0)
    last_sync_user_errors = models.IntegerField(verbose_name=_('Last Sync: User Errors'), default=0)

    last_sync_group_total = models.IntegerField(verbose_name=_('Last Sync: Groups Found in LDAP'), default=0)
    last_sync_group_added = models.IntegerField(verbose_name=_('Last Sync: Groups Added'), default=0)
    last_sync_group_deleted = models.IntegerField(verbose_name=_('Last Sync: Groups Deleted'), default=0)
    last_sync_group_errors = models.IntegerField(verbose_name=_('Last Sync: Group Errors'), default=0)

    last_sync_membership_total = models.IntegerField(verbose_name=_('Last Sync: Memberships Found in LDAP'), default=0)
    last_sync_membership_added = models.IntegerField(verbose_name=_('Last Sync: Memberships Added'), default=0)
    last_sync_membership_deleted = models.IntegerField(verbose_name=_('Last Sync: Memberships Deleted'), default=0)
    last_sync_membership_errors = models.IntegerField(verbose_name=_('Last Sync: Membership Errors'), default=0)

    def __str__(self):
        return _('"%(uri)s": Synced %(total)d times. Last Sync: %(date)s ') % {'uri': self.ldap_sync_uri, 'total': self.total_syncs, 'date': self.whenchanged}

    class Meta:
        verbose_name = _("Active Directory/LDAP Sync Record")
        verbose_name_plural = _("Active Directory/LDAP Sync Records")
        db_table = "adldap_sync"


## Class Sample for User Profile
#class Employee(models.Model):
#    user = models.OneToOneField(User,verbose_name=_('User'), on_delete=models.CASCADE)
#    company = models.CharField(verbose_name=_('Company'),max_length=200)
#    department = models.CharField(verbose_name=_('Department'),max_length=200,blank=True, null=True)
#    distinguishedname = models.CharField(verbose_name=_('DN'),max_length=250,blank=True, null=True) #To search managers
#    division = models.CharField(verbose_name=_('Division'),max_length=100,blank=True, null=True)
#    extensionname = models.CharField(verbose_name=_('Extension'),max_length=100,blank=True, null=True)
#    manager = models.CharField(verbose_name=_('Manager'),max_length=250,blank=True, null=True) #A manager in distinguishedName format
#    mobile = models.CharField(verbose_name=_('Mobile Phone'),max_length=100,blank=True, null=True)
#    physicaldeliveryofficename = models.CharField(verbose_name=_('Address'),max_length=500,blank=True, null=True)
#    thumbnailphoto = models.ImageField(upload_to='avatar',blank=True, null=True)
#    title = models.CharField(max_length=100,blank=True, null=True)
#    def __str__(self):
#        return self.user.username
#    def __unicode__(self):
#        return self.user.username
#    class Meta:
#        verbose_name = _("employee")
#        verbose_name_plural = _("employees")
#        db_table = "user_employee"
