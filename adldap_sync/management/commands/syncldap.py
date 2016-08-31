from __future__ import unicode_literals

import logging
import uuid
import pytz
from datetime import datetime, timedelta

import ldap
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import DataError, IntegrityError
from django.utils.module_loading import import_string
from ldap.controls import SimplePagedResultsControl
from ldap.ldapobject import LDAPObject

from adldap_sync.models import ADldap_Sync

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    can_import_settings = True
    help = 'Synchronize users and groups from an authoritative LDAP server'
    ATTRIBUTE_DISABLED = 'userAccountControl'
    FLAG_UF_ACCOUNT_DISABLE = 2
    ### CONFIG VARIABLES. Default Values
    #AD/LDAP CONNECTION VARS
    conf_LDAP_SYNC_BIND_URI = []  # A string or an array for failover, i.e.  ["ldap://dc1.example.com:389","ldap://dc2.example.com:389",]
    conf_LDAP_SYNC_BIND_DN = ''  # AD User to search. DON'T USE AN ADMIN ACCOUNT!!!!!
    conf_LDAP_SYNC_BIND_PASS = ''  # The ldap user password
    conf_LDAP_SYNC_BIND_SEARCH = ''  # I.e. "OU=Department,DC=example,DC=com"
    #conf_LDAP_SYNC_BIND_PAGESIZE = 200 #Used on PagedResultsSearchObject class below

    #USERS
    conf_LDAP_SYNC_USER = True
    conf_LDAP_SYNC_USER_INCREMENTAL = True
    conf_LDAP_SYNC_USER_SEARCH = ''  # I.e. "OU=Department,DC=example,DC=com"
    conf_LDAP_SYNC_USER_FILTER = '(&(objectCategory=person)(objectClass=user))'
    conf_LDAP_SYNC_USER_FILTER_INCREMENTAL = '(&(objectCategory=person)(objectClass=user)(whenchanged>=?))'
    conf_LDAP_SYNC_USER_ATTRIBUTES = {"sAMAccountName": "username", "givenName": "first_name", "sn": "last_name", "mail": "email", }
    conf_LDAP_SYNC_USER_EXTRA_ATTRIBUTES = [ATTRIBUTE_DISABLED] 
    #['userAccountControl','company','department','distinguishedName','division','extensionName','manager','mobile','physicalDeliveryOfficename','title','thumbnailPhoto']
    conf_LDAP_SYNC_USER_EXTRA_PROFILES = []  # appname.modelname, like adldap_sync.Employee
    conf_LDAP_SYNC_USER_EXEMPT_FROM_SYNC = ['admin', 'administrator', 'administrador', 'guest']
    conf_LDAP_SYNC_USER_CALLBACKS = []
    conf_LDAP_SYNC_USER_SET_UNUSABLE_PASSWORD = True
    conf_LDAP_SYNC_USER_REMOVAL_ACTION = 'DEACTIVATE'
    conf_LDAP_SYNC_USER_SHOW_PROGRESS = True
    conf_LDAP_SYNC_USER_THUMBNAILPHOTO_NAME = "{username}_{uuid4}.jpg"
    conf_LDAP_SYNC_USER_CHANGE_FIELDCASE = "lower"  # None,"lower","upper"
    conf_LDAP_SYNC_MULTIVALUE_SEPARATOR = "|"
    conf_LDAP_SYNC_USERNAME_FIELD = None
    conf_LDAP_SYNC_REMOVED_USER_CALLBACKS = ['adldap_sync.callbacks.removed_user_deactivate']

    #GROUPS
    conf_LDAP_SYNC_GROUP = True
    conf_LDAP_SYNC_GROUP_INCREMENTAL = True
    conf_LDAP_SYNC_GROUP_SEARCH = ''  # I.e. "OU=Department,DC=example,DC=com"
    conf_LDAP_SYNC_GROUP_FILTER = '(objectClass=group)'
    conf_LDAP_SYNC_GROUP_FILTER_INCREMENTAL = '(&(objectClass=group)(whenchanged>=?))'
    conf_LDAP_SYNC_GROUP_ATTRIBUTES = {"cn": "name"}
    conf_LDAP_SYNC_GROUP_REMOVAL_ACTION = 'KEEP'

    #GROUP MEMBERSHIP
    conf_LDAP_SYNC_GROUP_MEMBERSHIP = True
    conf_LDAP_SYNC_GROUP_MEMBERSHIP_DN_FIELD = 'distinguishedName'
    conf_LDAP_SYNC_GROUP_MEMBERSHIP_FILTER = '(member:1.2.840.113556.1.4.1941:={distinguishedName})'
    conf_LDAP_SYNC_GROUP_MEMBERSHIP_CREATE_IF_NOT_EXISTS = True
    conf_LDAP_SYNC_GROUP_MEMBERSHIP_ADD_DEFAULT = []  # [('CN=Domain Users,CN=Users,DC=example,DC=com', {'cn': [b'Domain Users']}),]

    #INCREMENTAL
    conf_LDAP_SYNC_INCREMENTAL_BETWEEN_FULL = 5
    conf_LDAP_SYNC_INCREMENTAL_TIME_OFFSET = 10
    conf_LDAP_SYNC_INCREMENTAL_TIMESTAMPFORMAT = "%Y%m%d%H%M%S.0Z"

    # STAT Variables
    stats_group_total = 0
    stats_group_added = 0
    stats_group_deleted = 0
    stats_group_errors = 0
    stats_user_total = 0
    stats_user_added = 0
    stats_user_updated = 0
    stats_user_deleted = 0
    stats_user_errors = 0
    stats_membership_total = 0
    stats_membership_added = 0
    stats_membership_deleted = 0
    stats_membership_errors = 0
    #Other Sync Variables
    whenchanged = datetime.utcnow()
    working_uri = None
    working_adldap_sync = None

    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('syncType', nargs='?', type=str, default='')

    def load_stringconfig(self, attrname, defaultvalue, canbeEmpty=False):
        result = getattr(settings, attrname, defaultvalue)
        if ((not canbeEmpty) and ((result is None) or (result == ''))):
            error_msg = ("%s must be specified in your Django settings file" % attrname)
            raise ImproperlyConfigured(error_msg)
        if (not isinstance(result, str)):
            error_msg = ("%s must be a string" % attrname)
            raise ImproperlyConfigured(error_msg)
        return result

    def load_boolconfig(self, attrname, defaultvalue):
        result = getattr(settings, attrname, defaultvalue)
        if (not isinstance(result, bool)):
            error_msg = ("%s must be a Boolean" % attrname)
            raise ImproperlyConfigured(error_msg)
        return result

    def load_listconfig(self, attrname, defaultvalue, canbeEmpty=False):
        result = getattr(settings, attrname, defaultvalue)
        if (not isinstance(result, list)):
            error_msg = ("%s must be an array or list: ['a','b',....]" % attrname)
            raise ImproperlyConfigured(error_msg)
        if ((not canbeEmpty) and ((result is None) or (len(result) == 0))):
            error_msg = ("%s must be specified in your Django settings file and can't be empty" % attrname)
            raise ImproperlyConfigured(error_msg)
        return result

    def load_dictconfig(self, attrname, defaultvalue, canbeEmpty=False):
        result = getattr(settings, attrname, defaultvalue)
        if (not isinstance(result, dict)):
            error_msg = ("%s must be a dictionary: {'a':'valuea','b':'valueb',....}" % attrname)
            raise ImproperlyConfigured(error_msg)
        if ((not canbeEmpty) and ((result is None) or (len(result) == 0))):
            error_msg = ("%s must be specified in your Django settings file and can't be empty" % attrname)
            raise ImproperlyConfigured(error_msg)
        return result

    def load_config(self, *args, **options):
        forceFull = (options['syncType'].lower() == 'full')
        forceIncremental = (options['syncType'].lower() == 'incremental')

        self.conf_LDAP_SYNC_BIND_URI = []
        uri = getattr(settings, 'LDAP_SYNC_BIND_URI', '')
        #Add URIs either as string or as array of strings
        if (isinstance(uri, str)):
            self.conf_LDAP_SYNC_BIND_URI.append(uri)
        else:
            for n_uri in uri:
                self.conf_LDAP_SYNC_BIND_URI.append(n_uri)
        if (len(self.conf_LDAP_SYNC_BIND_URI) == 0):
            error_msg = "LDAP_SYNC_BIND_URI must be specified in your Django settings file"
            raise ImproperlyConfigured(error_msg)

        self.conf_LDAP_SYNC_BIND_DN = self.load_stringconfig('LDAP_SYNC_BIND_DN', self.conf_LDAP_SYNC_BIND_DN)
        self.conf_LDAP_SYNC_BIND_PASS = self.load_stringconfig('LDAP_SYNC_BIND_PASS', self.conf_LDAP_SYNC_BIND_PASS)
        self.conf_LDAP_SYNC_BIND_SEARCH = self.load_stringconfig('LDAP_SYNC_BIND_SEARCH', self.conf_LDAP_SYNC_BIND_SEARCH)
        self.conf_LDAP_SYNC_MULTIVALUE_SEPARATOR = self.load_stringconfig('LDAP_SYNC_MULTIVALUE_SEPARATOR', self.conf_LDAP_SYNC_MULTIVALUE_SEPARATOR)

        #self.conf_LDAP_SYNC_BIND_PAGESIZE = 200#Not used in this class
        self.conf_LDAP_SYNC_USER = self.load_boolconfig('LDAP_SYNC_USER', self.conf_LDAP_SYNC_USER)

        #User Sync Config
        if (self.conf_LDAP_SYNC_USER):
            self.conf_LDAP_SYNC_USER_SEARCH = self.load_stringconfig('LDAP_SYNC_USER_SEARCH', self.conf_LDAP_SYNC_BIND_SEARCH)
            self.conf_LDAP_SYNC_USER_FILTER = self.load_stringconfig('LDAP_SYNC_USER_FILTER', self.conf_LDAP_SYNC_USER_FILTER)
            self.conf_LDAP_SYNC_USER_INCREMENTAL = self.load_boolconfig('LDAP_SYNC_USER_INCREMENTAL', self.conf_LDAP_SYNC_USER_INCREMENTAL)
            if (forceFull):
                self.conf_LDAP_SYNC_USER_INCREMENTAL = False
            if (forceIncremental):
                self.conf_LDAP_SYNC_USER_INCREMENTAL = True
            self.conf_LDAP_SYNC_USER_FILTER_INCREMENTAL = self.load_stringconfig('LDAP_SYNC_USER_FILTER_INCREMENTAL', self.conf_LDAP_SYNC_USER_FILTER_INCREMENTAL, (not self.conf_LDAP_SYNC_USER_INCREMENTAL))
            self.conf_LDAP_SYNC_USER_SHOW_PROGRESS = self.load_boolconfig('LDAP_SYNC_USER_SHOW_PROGRESS', self.conf_LDAP_SYNC_USER_SHOW_PROGRESS)
            self.conf_LDAP_SYNC_USER_SET_UNUSABLE_PASSWORD = self.load_boolconfig('LDAP_SYNC_USER_SET_UNUSABLE_PASSWORD', self.conf_LDAP_SYNC_USER_SET_UNUSABLE_PASSWORD)
            self.conf_LDAP_SYNC_USER_EXTRA_ATTRIBUTES = self.load_listconfig('LDAP_SYNC_USER_EXTRA_ATTRIBUTES', self.conf_LDAP_SYNC_USER_EXTRA_ATTRIBUTES, True)
            #We need the userAccountControl attribute for Disabling check, so we added it if missing on the ldap query
            if (self.ATTRIBUTE_DISABLED not in self.conf_LDAP_SYNC_USER_EXTRA_ATTRIBUTES):
                self.conf_LDAP_SYNC_USER_EXTRA_ATTRIBUTES.append(self.ATTRIBUTE_DISABLED)
            self.conf_LDAP_SYNC_USER_EXTRA_PROFILES = self.load_listconfig('LDAP_SYNC_USER_EXTRA_PROFILES', self.conf_LDAP_SYNC_USER_EXTRA_PROFILES, True)
            self.conf_LDAP_SYNC_USER_EXEMPT_FROM_SYNC = self.load_listconfig('LDAP_SYNC_USER_EXEMPT_FROM_SYNC', self.conf_LDAP_SYNC_USER_EXEMPT_FROM_SYNC, True)
            self.conf_LDAP_SYNC_USER_CALLBACKS = self.load_listconfig('LDAP_LDAP_SYNC_USER_CALLBACKS', self.conf_LDAP_SYNC_USER_CALLBACKS, True)
            self.conf_LDAP_SYNC_USER_ATTRIBUTES = self.load_dictconfig('LDAP_SYNC_USER_ATTRIBUTES', self.conf_LDAP_SYNC_USER_ATTRIBUTES)
            username_field = getattr(get_user_model(), 'USERNAME_FIELD', 'username')
            self.conf_LDAP_SYNC_USERNAME_FIELD = self.load_stringconfig('LDAP_SYNC_USERNAME_FIELD', username_field)
            if self.conf_LDAP_SYNC_USERNAME_FIELD not in self.conf_LDAP_SYNC_USER_ATTRIBUTES.values():
                error_msg = ("LDAP_SYNC_USER_ATTRIBUTES must contain the field '%s'" % self.conf_LDAP_SYNC_USERNAME_FIELD)
                raise ImproperlyConfigured(error_msg)
            self.conf_LDAP_SYNC_USER_THUMBNAILPHOTO_NAME = self.load_stringconfig('LDAP_SYNC_USER_THUMBNAILPHOTO_NAME', self.conf_LDAP_SYNC_USER_THUMBNAILPHOTO_NAME)
            self.conf_LDAP_SYNC_USER_REMOVAL_ACTION = self.load_stringconfig('LDAP_SYNC_USER_REMOVAL_ACTION', self.conf_LDAP_SYNC_USER_REMOVAL_ACTION)
            self.conf_LDAP_SYNC_REMOVED_USER_CALLBACKS = self.load_listconfig('LDAP_SYNC_REMOVED_USER_CALLBACKS', self.conf_LDAP_SYNC_REMOVED_USER_CALLBACKS, True)
            self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE = self.load_stringconfig('LDAP_SYNC_USER_CHANGE_FIELDCASE', self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE, True)
            if (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE) and ((self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE != "lower") and (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE != "upper")):
                error_msg = ("LDAP_SYNC_USER_CHANGE_FIELDCASE invalid: %s. Valid values are None, 'lower' or 'upper'" % self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE)
                raise ImproperlyConfigured(error_msg)

        #Group Sync config
        self.conf_LDAP_SYNC_GROUP = self.load_boolconfig('LDAP_SYNC_GROUP', self.conf_LDAP_SYNC_GROUP)
        if (self.conf_LDAP_SYNC_GROUP):
            self.conf_LDAP_SYNC_GROUP_SEARCH = self.load_stringconfig('LDAP_SYNC_GROUP_SEARCH', self.conf_LDAP_SYNC_BIND_SEARCH)
            self.conf_LDAP_SYNC_GROUP_FILTER = self.load_stringconfig('LDAP_SYNC_GROUP_FILTER', self.conf_LDAP_SYNC_GROUP_FILTER)
            self.conf_LDAP_SYNC_GROUP_INCREMENTAL = self.load_boolconfig('LDAP_SYNC_GROUP_INCREMENTAL', self.conf_LDAP_SYNC_GROUP_INCREMENTAL)
            if (forceFull):
                self.conf_LDAP_SYNC_GROUP_INCREMENTAL = False
            if (forceIncremental):
                self.conf_LDAP_SYNC_GROUP_INCREMENTAL = True
            self.conf_LDAP_SYNC_GROUP_FILTER_INCREMENTAL = self.load_stringconfig('LDAP_SYNC_GROUP_FILTER_INCREMENTAL', self.conf_LDAP_SYNC_GROUP_FILTER_INCREMENTAL, (not self.conf_LDAP_SYNC_GROUP_INCREMENTAL))
            self.conf_LDAP_SYNC_GROUP_ATTRIBUTES = self.load_dictconfig('LDAP_SYNC_GROUP_ATTRIBUTES', self.conf_LDAP_SYNC_GROUP_ATTRIBUTES)
            groupname_field = 'name'
            if groupname_field not in self.conf_LDAP_SYNC_GROUP_ATTRIBUTES.values():
                error_msg = "LDAP_SYNC_GROUP_ATTRIBUTES must contain the field '%s'" % groupname_field
                raise ImproperlyConfigured(error_msg)
            self.conf_LDAP_SYNC_GROUP_REMOVAL_ACTION = self.load_stringconfig('LDAP_SYNC_GROUP_REMOVAL_ACTION', self.conf_LDAP_SYNC_GROUP_REMOVAL_ACTION)

        #Group Membership Config
        self.conf_LDAP_SYNC_GROUP_MEMBERSHIP = self.load_boolconfig('LDAP_SYNC_GROUP_MEMBERSHIP', self.conf_LDAP_SYNC_GROUP_MEMBERSHIP)
        if (self.conf_LDAP_SYNC_GROUP_MEMBERSHIP):
            self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_DN_FIELD = self.load_stringconfig('LDAP_SYNC_GROUP_MEMBERSHIP_DN_FIELD', self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_DN_FIELD)
            if ((self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_DN_FIELD is not None) and (self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_DN_FIELD not in self.conf_LDAP_SYNC_USER_EXTRA_ATTRIBUTES)):
                self.conf_LDAP_SYNC_USER_EXTRA_ATTRIBUTES.append(self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_DN_FIELD)
            self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_FILTER = self.load_stringconfig('LDAP_SYNC_GROUP_MEMBERSHIP_FILTER', self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_FILTER)
            self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_CREATE_IF_NOT_EXISTS = self.load_boolconfig('LDAP_SYNC_GROUP_MEMBERSHIP_CREATE_IF_NOT_EXISTS', self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_CREATE_IF_NOT_EXISTS)
            self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_ADD_DEFAULT = self.load_listconfig('LDAP_SYNC_GROUP_MEMBERSHIP_ADD_DEFAULT', self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_ADD_DEFAULT, True)

        self.conf_LDAP_SYNC_INCREMENTAL_BETWEEN_FULL = getattr(settings, 'LDAP_SYNC_INCREMENTAL_BETWEEN_FULL', self.conf_LDAP_SYNC_INCREMENTAL_BETWEEN_FULL)
        self.conf_LDAP_SYNC_INCREMENTAL_TIME_OFFSET = getattr(settings, 'LDAP_SYNC_INCREMENTAL_TIME_OFFSET', self.conf_LDAP_SYNC_INCREMENTAL_TIME_OFFSET)
        self.conf_LDAP_SYNC_INCREMENTAL_TIMESTAMPFORMAT = self.load_stringconfig('LDAP_SYNC_INCREMENTAL_TIMESTAMPFORMAT', self.conf_LDAP_SYNC_INCREMENTAL_TIMESTAMPFORMAT)
        #We take out N minutes to avoid any time drift or different times for sync.
        self.whenchanged = datetime.utcnow().replace(tzinfo=pytz.utc) - timedelta(minutes=self.conf_LDAP_SYNC_INCREMENTAL_TIME_OFFSET)
        msgLoaded = "Config loaded correctly"
        if (forceFull):
            msgLoaded += ": Forcing a FULL Sync"
        if (forceIncremental):
            msgLoaded += ": Forcing an Incremental Sync"
        logger.debug(msgLoaded)

    def handle(self, *args, **options):
        self.load_config(*args, **options)

        uri_groups_server, ldap_groups = self.get_ldap_groups()
        if ldap_groups:
            self.sync_ldap_groups(ldap_groups)

        uri_users_server, ldap_users = self.get_ldap_users()
        if ldap_users:
            self.sync_ldap_users(ldap_users)

        if ((uri_groups_server == uri_users_server) and (uri_groups_server is not None)):
            #OK Both servers are the same so we can safely update its info
            adldap_sync, created = ADldap_Sync.objects.get_or_create(ldap_sync_uri=uri_groups_server)
            adldap_sync.total_syncs += 1

            adldap_sync.last_sync_user_total = self.stats_user_total
            adldap_sync.last_sync_user_added = self.stats_user_added
            adldap_sync.last_sync_user_deleted = self.stats_user_deleted
            adldap_sync.last_sync_user_errors = self.stats_user_errors
            adldap_sync.last_sync_user_updated = self.stats_user_updated

            adldap_sync.last_sync_membership_total = self.stats_membership_total
            adldap_sync.last_sync_membership_added = self.stats_membership_added
            adldap_sync.last_sync_membership_deleted = self.stats_membership_deleted
            adldap_sync.last_sync_membership_errors = self.stats_membership_errors

            adldap_sync.last_sync_group_total = self.stats_group_total
            adldap_sync.last_sync_group_added = self.stats_group_added
            adldap_sync.last_sync_group_deleted = self.stats_group_deleted
            adldap_sync.last_sync_group_errors = self.stats_group_errors

            if (adldap_sync.syncs_to_full == 0):
                adldap_sync.last_sync_type = 'Full'
                adldap_sync.syncs_to_full = self.conf_LDAP_SYNC_INCREMENTAL_BETWEEN_FULL
            else:
                adldap_sync.last_sync_type = 'Incremental'
                #To allow -1 to never sync Full
                if (adldap_sync.syncs_to_full >= 0):
                    adldap_sync.syncs_to_full -= 1
            adldap_sync.whenchanged = self.whenchanged
            adldap_sync.save()
            logger.debug("Synchronization finished: Type:%s; Next Full sync in: %d syncs. Users (%d): A:%d U:%d D:%d Err:%d. Groups (%d): A:%d D:%d Err:%d. Memberships (%d): A:%d D:%d Err:%d" \
                         % (adldap_sync.last_sync_type, adldap_sync.syncs_to_full, \
                           adldap_sync.last_sync_user_total, adldap_sync.last_sync_user_added, adldap_sync.last_sync_user_updated, adldap_sync.last_sync_user_deleted, adldap_sync.last_sync_user_errors, \
                           adldap_sync.last_sync_group_total, adldap_sync.last_sync_group_added, adldap_sync.last_sync_group_deleted, adldap_sync.last_sync_group_errors, \
                           adldap_sync.last_sync_membership_total, adldap_sync.last_sync_membership_added, adldap_sync.last_sync_membership_deleted, adldap_sync.last_sync_membership_errors))

        else:
            if ((uri_groups_server is not None) or (uri_users_server is not None)):
                logger.error("Both servers are not the same, or no Sync was attempted. Something must be misconfigured! Groups URI: %s, Users URI:%s" % (uri_groups_server, uri_users_server))

    def get_ldap_users(self):
        """Retrieve user data from LDAP server."""
        if (not self.conf_LDAP_SYNC_USER):
            return (None, None)
        user_keys = set(self.conf_LDAP_SYNC_USER_ATTRIBUTES.keys())
        user_keys.update(self.conf_LDAP_SYNC_USER_EXTRA_ATTRIBUTES)
        uri_users_server, users = self.ldap_search(self.conf_LDAP_SYNC_USER_FILTER, user_keys, self.conf_LDAP_SYNC_USER_INCREMENTAL, self.conf_LDAP_SYNC_USER_FILTER_INCREMENTAL)
        logger.debug("Retrieved %d users from %s LDAP server" % (len(users), uri_users_server))
        return (uri_users_server, users)

    def sync_ldap_users(self, ldap_users):
        """Synchronize users with local user model."""
        model = get_user_model()

        #Load total User starts
        self.stats_user_total = len(ldap_users)

        list_profiles = []
        #Load extra profiles. This way we don't even need a callback. The same code is used to populate both auth_user and user_profile
        for list_profile in self.conf_LDAP_SYNC_USER_EXTRA_PROFILES:
            list_profiles.append((list_profile, apps.get_model(list_profile)))

        if not model._meta.get_field(self.conf_LDAP_SYNC_USERNAME_FIELD).unique:
            raise ImproperlyConfigured("Field '%s' must be unique" % self.conf_LDAP_SYNC_USERNAME_FIELD)

        actualProgress = 0

        for cname, attributes in ldap_users:
            defaults = {}
            actualProgress += 1
            if (self.conf_LDAP_SYNC_USER_SHOW_PROGRESS and ((100 * actualProgress // self.stats_user_total) > (100 * (actualProgress - 1) // self.stats_user_total))):
                logger.info("AD User Sync: Processed %d/%d users (%d" % (actualProgress, self.stats_user_total, (100 * actualProgress) // self.stats_user_total) + "%)")
            try:
                for name, attribute in attributes.items():
                    try:
                        if ((name.lower() == 'thumbnailphoto') or (name.lower() == 'jpegphoto')):
                            defaults[self.conf_LDAP_SYNC_USER_ATTRIBUTES[name]] = attribute[0]
                        else:
                            defaults[self.conf_LDAP_SYNC_USER_ATTRIBUTES[name]] = attribute[0].decode('utf-8')
                    except KeyError:
                        pass
                    except UnicodeDecodeError:
                        raise ImproperlyConfigured('Error in attribute ' + name + ' ' + str(attribute))
            except AttributeError:
                # In some cases attributes is a list instead of a dict; skip these invalid users
                continue

            try:
                username = defaults[self.conf_LDAP_SYNC_USERNAME_FIELD].lower()
            except KeyError:
                logger.warning("User is missing a required attribute '%s'" % self.conf_LDAP_SYNC_USERNAME_FIELD)
                continue

            #Don't import users if they are in LDAP_SYNC_USER_EXEMPT_FROM_SYNC settings
            if (username in self.conf_LDAP_SYNC_USER_EXEMPT_FROM_SYNC):
                logger.debug("Skip importing user %s, it appears in LDAP_SYNC_USER_EXEMPT_FROM_SYNC list" % username)
                continue

            kwargs = {
                self.conf_LDAP_SYNC_USERNAME_FIELD + '__iexact': username,
                'defaults': defaults,
            }

            ### Users Disable
            #Check disable bit 
            user_account_control = int(attributes[self.ATTRIBUTE_DISABLED][0].decode('utf-8'))
            user_is_disabled = (user_account_control and ((user_account_control & self.FLAG_UF_ACCOUNT_DISABLE) == self.FLAG_UF_ACCOUNT_DISABLE))
            if user_is_disabled:
                try:
                    #If disabled, we need to check if the user already exists on Django
                    user = model.objects.get(**{self.conf_LDAP_SYNC_USERNAME_FIELD + '__iexact': username,})
                    if (not user):
                        #Ignore disabled users, we won't import it, only update it
                        continue
                except Exception as e:
                    #Ignore disabled users, we won't import it, only update it
                    continue
                else:
                    #If the user already exists on Django we'll run the callbacks
                    if (self.conf_LDAP_SYNC_REMOVED_USER_CALLBACKS):
                        self.stats_user_deleted += 1
                    for path in self.conf_LDAP_SYNC_REMOVED_USER_CALLBACKS:
                        logger.debug("Calling %s for user %s" % (path, username))
                        callback = import_string(path)
                        callback(user)
            ### User creation and sinchronization
            updated = False
            try:
                if user_is_disabled:
                    created = False
                    #reload it because it may be deleted
                    user = model.objects.get(**{self.conf_LDAP_SYNC_USERNAME_FIELD + '__iexact': username,})
                else:
                    user, created = model.objects.get_or_create(**kwargs)
            except (ObjectDoesNotExist) as e:
                if (user_is_disabled):
                    continue
                else:
                    raise e
            except (IntegrityError, DataError) as e:
                logger.error("Error creating user %s: %s" % (username, e))
                self.stats_user_errors += 1
            else:
                user_updated = False
                if created:
                    logger.debug("Created user %s" % username)
                    self.stats_user_added += 1
                    user.set_unusable_password()
                else:
                    for name, attr in defaults.items():
                        current_attr = getattr(user, name, None)
                        if current_attr != attr:
                            setattr(user, name, attr)
                            if (not user_updated):
                                user_updated = True
                    if user_updated:
                        logger.debug("Updated user %s" % username)
                        updated = True

                for path in self.conf_LDAP_SYNC_USER_CALLBACKS:
                    callback = import_string(path)
                    callback(user, attributes, created, user_updated)

                try:
                    if (created or user_updated):
                        user.save()
                except Exception as e:
                    logger.error("Error saving user %s: %s" % (username, e))
                    self.stats_user_errors += 1
                ### LDAP Sync Membership
                if (self.conf_LDAP_SYNC_GROUP_MEMBERSHIP):
                    membership_uri, ldap_membership = self.get_ldap_user_membership(attributes[self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_DN_FIELD][0].decode('utf-8'))
                    if ldap_membership:
                        self.sync_ldap_user_membership(user, ldap_membership)
            #Profile creation and update.
            for name_profile, profile_model in list_profiles:
                try:
                    profile, created = profile_model.objects.get_or_create(user=user)  # ,  **kwargs )
                except (IntegrityError, DataError) as e:
                    logger.error("Error creating profile %s for user %s: %s" % (name_profile, username, e))
                    self.stats_user_errors += 1
                else:
                    profile_updated = False
                    if (created):
                        logger.debug("Created profile '%s' for user '%s'" % (name_profile, username))
                        #profile.save()
                    for unchanged_name, attr in attributes.items():
                        name = unchanged_name
                        if (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE == "lower"):
                            name = unchanged_name.lower()
                        if (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE == "upper"):
                            name = unchanged_name.upper()

                        try:
                            if ((name.lower() != 'thumbnailphoto') and (name.lower() != 'jpegphoto')):
                                current_attr = getattr(profile, name)
                                new_value = ''
                                if (isinstance(attr, list)):
                                    for val in attr:
                                        new_value += val.decode("utf8") + self.conf_LDAP_SYNC_MULTIVALUE_SEPARATOR
                                    if (new_value != ""):
                                        new_value = new_value[:-len(self.conf_LDAP_SYNC_MULTIVALUE_SEPARATOR)]
                                else:
                                    new_value = attr
                                if current_attr != new_value:
                                    setattr(profile, name, new_value)
                                    #logger.debug("Updated profile %s: Attribute %s from '%s' to '%s' - '%s'" % (username,name, current_attr, new_value, attr))
                                    profile_updated = True
                            else:
                                if (isinstance(attr, list)):
                                    newthumbPhoto = attr[0]
                                else:
                                    newthumbPhoto = attr
                                actualPhoto = None
                                try:
                                    if (name.lower() == 'thumbnailphoto'):
                                        if (not self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE):
                                            actualPhoto = profile.thumbnailPhoto.read()
                                        if (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE == "lower"):
                                            actualPhoto = profile.thumbnailphoto.read()
                                        if (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE == "upper"):
                                            actualPhoto = profile.THUMBNAILPHOTO.read()
                                    else:
                                        if (not self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE):
                                            actualPhoto = profile.jpegPhoto.read()
                                        if (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE == "lower"):
                                            actualPhoto = profile.jpegphoto.read()
                                        if (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE == "upper"):
                                            actualPhoto = profile.JPEGPHOTO.read()
                                except Exception as e:
                                    pass
                                if (actualPhoto != newthumbPhoto):
                                    #Saving thumbnailphoto
                                    #logger.debug("Photo in "+username+" are different... ")
                                    photo_name = self.conf_LDAP_SYNC_USER_THUMBNAILPHOTO_NAME
                                    #we don't format because I don't know if username it's being used at all
                                    photo_name = photo_name.replace('{username}', username)
                                    photo_name = photo_name.replace('{uuid4}', str(uuid.uuid4()))
                                    photo_name = datetime.now().strftime(photo_name)
                                    if (name.lower() == 'thumbnailphoto'):
                                        if (not self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE):
                                            if (actualPhoto):
                                                profile.thumbnailPhoto.delete()
                                            profile.thumbnailPhoto.save(name=photo_name, content=ContentFile(newthumbPhoto))
                                        if (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE == "lower"):
                                            if (actualPhoto):
                                                profile.thumbnailphoto.delete()
                                            profile.thumbnailphoto.save(name=photo_name, content=ContentFile(newthumbPhoto))
                                        if (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE == "upper"):
                                            if (actualPhoto):
                                                profile.THUMBNAILPHOTO.delete()
                                            profile.THUMBNAILPHOTO.save(name=photo_name, content=ContentFile(newthumbPhoto))
                                    else:
                                        if (not self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE):
                                            if (actualPhoto):
                                                profile.jpegPhoto.delete()
                                            profile.jpegPhoto.save(name=photo_name, content=ContentFile(newthumbPhoto))
                                        if (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE == "lower"):
                                            if (actualPhoto):
                                                profile.jpegphoto.delete()
                                            profile.jpegphoto.save(name=photo_name, content=ContentFile(newthumbPhoto))
                                        if (self.conf_LDAP_SYNC_USER_CHANGE_FIELDCASE == "upper"):
                                            if (actualPhoto):
                                                profile.JPEGPHOTO.delete()
                                            profile.JPEGPHOTO.save(name=photo_name, content=ContentFile(newthumbPhoto))
                                    profile_updated = True
                                else:
                                    pass
                                    #logger.debug("Photo "+username+" are equal")
                        except AttributeError:
                            pass
                            #logger.debug("Ignore Attribute %s on profile '%s'" % (name, name_profile))
                    if profile_updated:
                        logger.debug("Updated profile %s on user %s" % (name_profile, username))
                        updated = True
                    if (created or profile_updated):
                        try:
                            profile.save()
                        except Exception as e:
                            logger.error("Error saving profile %s for user %s: %s" % (name_profile, username, e))
                            self.stats_user_errors += 1
                    #profile.save()
                    #If either user record or any profile record is changed, we'll mark it as updated.
            if (updated):
                self.stats_user_updated += 1

        logger.info("Users are synchronized")

    def get_ldap_groups(self):
        """Retrieve groups from LDAP server."""
        if (not self.conf_LDAP_SYNC_GROUP):
            return (None, None)
        uri_groups_server, groups = self.ldap_search(self.conf_LDAP_SYNC_GROUP_FILTER, self.conf_LDAP_SYNC_GROUP_ATTRIBUTES.keys(), self.conf_LDAP_SYNC_GROUP_INCREMENTAL, self.conf_LDAP_SYNC_GROUP_FILTER_INCREMENTAL)
        logger.debug("Retrieved %d groups from %s LDAP server" % (len(groups), uri_groups_server))
        return (uri_groups_server, groups)

    def sync_ldap_groups(self, ldap_groups):
        """Synchronize LDAP groups with local group model."""
        groupname_field = 'name'
        self.stats_group_total = len(ldap_groups)

        for cname, ldap_attributes in ldap_groups:
            defaults = {}
            try:
                for name, attribute in ldap_attributes.items():
                    defaults[self.conf_LDAP_SYNC_GROUP_ATTRIBUTES[name]] = attribute[0].decode('utf-8')
            except AttributeError:
                # In some cases attrs is a list instead of a dict; skip these invalid groups
                continue

            try:
                groupname = defaults[groupname_field]
            except KeyError:
                logger.warning("Group is missing a required attribute '%s'" % groupname_field)
                self.stats_group_errors += 1
                continue

            kwargs = {
                groupname_field + '__iexact': groupname,
                'defaults': defaults,
            }
            try:
                group, created = Group.objects.get_or_create(**kwargs)
            except (IntegrityError, DataError) as e:
                logger.error("Error creating group %s: %s" % (groupname, e))
                self.stats_group_errors += 1
            else:
                if created:
                    self.stats_group_added += 1
                    logger.debug("Created group %s" % groupname)

        logger.info("Groups are synchronized")

    def get_ldap_user_membership(self, user_dn):
        """Retrieve user membership from LDAP server."""
        #Escape parenthesis in DN
        membership_filter = self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_FILTER.replace('{distinguishedName}', user_dn.replace('(', "\(").replace(')', "\)"))
        try:
            uri, groups = self.ldap_search(membership_filter, self.conf_LDAP_SYNC_GROUP_ATTRIBUTES.keys(), False, membership_filter)
        except Exception as e:
            logger.error("Error reading membership: Filter %s, Keys %s" % (membership_filter, str(self.conf_LDAP_SYNC_GROUP_ATTRIBUTES.keys())))
            return None
        #logger.debug("AD Membership: Retrieved %d groups for user '%s'" % (len(groups), user_dn))
        return (uri, groups)

    def sync_ldap_user_membership(self, user, ldap_groups):
        """Synchronize LDAP membership to Django membership"""
        groupname_field = 'name'
        actualGroups = user.groups.values_list('name', flat=True)
        user_Membership_total = len(ldap_groups)
        user_Membership_added = 0
        user_Membership_deleted = 0
        user_Membership_errors = 0

        ldap_groups += self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_ADD_DEFAULT

        ldap_name_groups = []

        for cname, ldap_attributes in ldap_groups:
            defaults = {}
            try:
                for name, attribute in ldap_attributes.items():
                    defaults[self.conf_LDAP_SYNC_GROUP_ATTRIBUTES[name]] = attribute[0].decode('utf-8')
            except AttributeError:
                # In some cases attrs is a list instead of a dict; skip these invalid groups
                continue

            try:
                groupname = defaults[groupname_field]
                ldap_name_groups.append(groupname)
            except KeyError:
                logger.warning("Group is missing a required attribute '%s'" % groupname_field)
                user_Membership_errors += 1
                continue
            if (groupname not in actualGroups):
                kwargs = {
                    groupname_field + '__iexact': groupname,
                    'defaults': defaults,
                }

                #Adding Group Membership
                try:
                    if (self.conf_LDAP_SYNC_GROUP_MEMBERSHIP_CREATE_IF_NOT_EXISTS):
                        group, created = Group.objects.get_or_create(**kwargs)
                    else:
                        group = Group.objects.get(name=groupname)
                        created = False
                except (ObjectDoesNotExist):
                    #Doesn't exist and not autocreate groups, we pass the error
                    continue
                except (IntegrityError, DataError) as e:
                    logger.error("Error creating group %s: %s" % (groupname, e))
                    user_Membership_errors += 1
                else:
                    if created:
                        logger.debug("Created group %s" % groupname)
                    #Now well assign the user
                    group.user_set.add(user)
                    user_Membership_added += 1
        #Default Primary Group: Temporary is fixed


        #removing group membership
        for check_group in actualGroups:
            if (check_group not in ldap_name_groups):
                group = Group.objects.get(name=check_group)
                group.user_set.remove(user)
                user_Membership_deleted += 1

        if ((user_Membership_deleted > 0) or (user_Membership_added > 0)):
            group.save()
            logger.info("Group membership for user %s synchronized: %d Added, %d Removed" % (user.username, user_Membership_added, user_Membership_deleted))
        #Return statistics
        self.stats_membership_total += user_Membership_total
        self.stats_membership_added += user_Membership_added
        self.stats_membership_deleted += user_Membership_deleted
        self.stats_membership_errors += user_Membership_errors

    def ldap_search(self, filter, attributes, incremental, incremental_filter):
        """
        Query the configured LDAP server with the provided search filter and
        attribute list.
        """
        for uri in self.conf_LDAP_SYNC_BIND_URI:
            #Read record of this uri
            if (self.working_uri == uri):
                adldap_sync = self.working_adldap_sync
                created = False
            else:
                adldap_sync, created = ADldap_Sync.objects.get_or_create(ldap_sync_uri=uri)

            if ((adldap_sync.syncs_to_full > 0) and incremental):
                filter_to_use = incremental_filter.replace('?', self.whenchanged.strftime(self.conf_LDAP_SYNC_INCREMENTAL_TIMESTAMPFORMAT))
                logger.debug("Using an incremental search. Filter is:'%s'" % filter_to_use)
            else:
                filter_to_use = filter

            ldap.set_option(ldap.OPT_REFERRALS, 0)
            #ldap.set_option(ldap.OPT_NETWORK_TIMEOUT, 10)
            l = PagedLDAPObject(uri)
            l.protocol_version = 3

            if (uri.startswith('ldaps:')):
                l.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_DEMAND)
                l.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
                l.set_option(ldap.OPT_X_TLS_DEMAND, True)
            else:
                l.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_NEVER)
                l.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                l.set_option(ldap.OPT_X_TLS_DEMAND, False)
            try:
                l.simple_bind_s(self.conf_LDAP_SYNC_BIND_DN, self.conf_LDAP_SYNC_BIND_PASS)
            except ldap.LDAPError as e:
                logger.error("Error connecting to LDAP server %s : %s" % (uri, e))
                continue

            results = l.paged_search_ext_s(self.conf_LDAP_SYNC_BIND_SEARCH, ldap.SCOPE_SUBTREE, filter_to_use, attrlist=attributes, serverctrls=None)
            l.unbind_s()
            if (self.working_uri is None):
                self.working_uri = uri
                self.conf_LDAP_SYNC_BIND_URI.insert(0, uri)
                self.working_adldap_sync = adldap_sync

            return (uri, results)  # Return both the LDAP server URI used and the request. This is for incremental sync purposes
        #if not connected correctly, raise error
        raise


class PagedResultsSearchObject:
    """
    Taken from the python-ldap paged_search_ext_s.py demo, showing how to use
    the paged results control: https://bitbucket.org/jaraco/python-ldap/
    """
    conf_LDAP_SYNC_BIND_PAGESIZE = max(10, getattr(settings, 'LDAP_SYNC_BIND_PAGESIZE', 200))

    def paged_search_ext_s(self, base, scope, filterstr='(objectClass=*)', attrlist=None, attrsonly=0,
                           serverctrls=None, clientctrls=None, timeout=-1, sizelimit=0):
        """
        Behaves exactly like LDAPObject.search_ext_s() but internally uses the
        simple paged results control to retrieve search results in chunks.
        """
        req_ctrl = SimplePagedResultsControl(True, size=self.conf_LDAP_SYNC_BIND_PAGESIZE, cookie='')

        # Send first search request
        msgid = self.search_ext(base, ldap.SCOPE_SUBTREE, filterstr, attrlist=attrlist,
                                serverctrls=(serverctrls or []) + [req_ctrl])
        results = []

        while True:
            rtype, rdata, rmsgid, rctrls = self.result3(msgid)
            results.extend(rdata)
            # Extract the simple paged results response control
            pctrls = [c for c in rctrls if c.controlType == SimplePagedResultsControl.controlType]

            if pctrls:
                if pctrls[0].cookie:
                    # Copy cookie from response control to request control
                    req_ctrl.cookie = pctrls[0].cookie
                    msgid = self.search_ext(base, ldap.SCOPE_SUBTREE, filterstr, attrlist=attrlist,
                                            serverctrls=(serverctrls or []) + [req_ctrl])
                else:
                    break

        return results


class PagedLDAPObject(LDAPObject, PagedResultsSearchObject):
    pass
