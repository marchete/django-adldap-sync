.. _settings:

Settings
========

.. currentmodule:: django.conf.settings

Outdated documentation. This module has more configuration variables.

.. attribute:: LDAP_SYNC_BIND_URI

   :default: ``[]``

   The address of the LDAP server containing the authoritative user account
   information. This should be a string specifying the complete address::

      LDAP_SYNC_BIND_URI = ["ldap://dc1.example.com:389","ldap://dc2.example.com:389",]

.. attribute:: LDAP_SYNC_BIND_SEARCH

   :default: ``""``

   The root of the LDAP tree to search for user account information. The
   contents of this tree can be further refined using the filtering settings.
   This should be a string specifying the complete root path::

      LDAP_SYNC_BIND_SEARCH = "OU=Users,DC=example,DC=com"

.. attribute:: LDAP_SYNC_BIND_DN

   :default: ``""``

   A user with appropriate permissions to connect to the LDAP server and
   retrieve user account information. This should be a string specifying the
   LDAP user account::

      LDAP_SYNC_BIND_DN = "CN=Django,OU=Users,DC=example,DC=com"

.. attribute:: LDAP_SYNC_BIND_PASS

   :default: ``""``

   The corresponding password for the above user account. This should be a
   string specifying the password::

      LDAP_SYNC_BIND_PASS = "My super secret password"

.. attribute:: LDAP_SYNC_USER_FILTER

   :default: ``""``

   An LDAP filter to further refine the user accounts to synchronize. This
   should be a string specifying a valid LDAP filter::

      LDAP_SYNC_USER_FILTER = "(&(objectCategory=person)(objectClass=User)(memberOf=CN=Web,OU=Users,DC=example,DC=com))"

.. attribute:: LDAP_SYNC_USER_ATTRIBUTES

   :default: ``{}``

   A dictionary mapping LDAP field names to User profile attributes. New users
   will be created with this data populated, and existing users will be
   updated as necessary. The mapping must at least contain a field mapping
   the User model's username field::

      LDAP_SYNC_USER_ATTRIBUTES = {
          "sAMAccountName": "username",
          "givenName": "first_name",
          "sn": "last_name",
          "mail": "email",
      }

.. attribute:: LDAP_SYNC_USER_CALLBACKS

   :default: ``[]``

   A list of dotted paths to callback functions that will be called for each user
   added or updated. Each callback function is passed three parameters: the user
   object, a created flag and an updated flag.

.. attribute:: LDAP_SYNC_USER_EXTRA_ATTRIBUTES

   :default: ``[]``

   A list of additional LDAP field names to retrieve. These attributes are not
   updated on user accounts, but are passed to user callback functions for
   additional processing.

.. attribute:: LDAP_SYNC_REMOVED_USER_CALLBACKS

   :default: ``[]``

   A list of dotted paths to callback functions that will be called for each user
   found to be removed. Each callback function is passed a single parameter of the
   user object. Note that if changes are made to the user object, it will need to
   be explicitly saved within the callback function.

   Two callback functions are included, providing common functionality:
   ``adldap_sync.callbacks.removed_user_deactivate`` and ``adldap_sync.callbacks.removed_user_delete``
   which deactivate and delete the given user, respectively.

.. attribute:: LDAP_SYNC_USERNAME_FIELD

   :default: ``None``

   An optional field on the synchronized User model to use as the unique key for
   each user. If not specified, the User model's ``USERNAME_FIELD`` will be used.
   If specified, the field must be included in ``LDAP_SYNC_USER_ATTRIBUTES``.

.. attribute:: LDAP_SYNC_GROUP_FILTER

   :default: ``""``

   An LDAP filter string to further refine the groups to synchronize.  This
   should be a string specifying any valid filter string::

      LDAP_SYNC_GROUP_FILTER = "(&(objectclass=group))"

.. attribute:: LDAP_SYNC_GROUP_ATTRIBUTES

   :default: ``{}``

   A dictionary mapping LDAP field names to Group attributes. New groups
   will be created with this data populated, and existing groups will be
   updated as necessary. The mapping must at least contain a field with the
   value of ``name`` to specify the group's name::

      LDAP_SYNC_GROUP_ATTRIBUTES = {
          "cn": "name",
      }


TODO: Full description of config settings. All the configurable settings are below:
   LDAP_SYNC_BIND_URI = [] 
   #A string or an array for failover, i.e.  ["ldap://dc1.example.com:389","ldap://dc2.example.com:389",]
   LDAP_SYNC_BIND_DN = ''  #AD User to search. DON'T USE AN ADMIN ACCOUNT!!!!!
   LDAP_SYNC_BIND_PASS = '' #The ldap user password
   LDAP_SYNC_BIND_SEARCH = '' #I.e. "OU=Department,DC=example,DC=com"
   LDAP_SYNC_BIND_PAGESIZE = 200 #Used on PagedResultsSearchObject, for paging LDAP queries

   #USERS
   LDAP_SYNC_USER = True   #With False it will NOT Sync either users or group memberships
   LDAP_SYNC_USER_INCREMENTAL = True   #False to disable incremental sync
   LDAP_SYNC_USER_SEARCH = ''  
   #I.e. "OU=Department,DC=example,DC=com" If you don't setup any, LDAP_SYNC_BIND_SEARCH is used. 
   LDAP_SYNC_USER_FILTER = '(&(objectCategory=person)(objectClass=user))'
   LDAP_SYNC_USER_FILTER_INCREMENTAL = '(&(objectCategory=person)(objectClass=user)(whenchanged>=?))'
   #  The ? is replaced by the whenChanged datetime, in UTC format
   LDAP_SYNC_USER_ATTRIBUTES = {
      "sAMAccountName": "username",
      "givenName": "first_name",
      "sn":"last_name",
      "mail": "email",
   } 
   #  Default ones, leave it as it is
   LDAP_SYNC_USER_EXTRA_ATTRIBUTES = [] 
   #  ['userAccountControl','company','department','distinguishedName','division','extensionName',\
   #   'manager','mobile','physicalDeliveryOfficename','title','thumbnailPhoto']
   LDAP_SYNC_USER_EXTRA_PROFILES = [] 
   # appname.modelname, like adldap_sync.Employee, you have one example in models.py
   LDAP_SYNC_USER_EXEMPT_FROM_SYNC = ['admin','administrator','guest']
   #These users won't be created or synced
   LDAP_SYNC_USER_CALLBACKS = []  #You can manually populate your User Profiles via callbacks
   LDAP_SYNC_USER_SET_UNUSABLE_PASSWORD = True
   LDAP_SYNC_USER_SHOW_PROGRESS = True 
   #It will show the user sync progress, useful on large AD setups to check the % progress
   LDAP_SYNC_USER_THUMBNAILPHOTO_NAME = "{username}_{uuid4}.jpg" 
   #It allows the parameters {username}, {uuid4} and datetime.strftime
   LDAP_SYNC_USER_CHANGE_FIELDCASE = "lower" #None,"lower","upper"
   LDAP_SYNC_MULTIVALUE_SEPARATOR = "|"  
   #If an AD attribute is multivalued, it will be joined on one string as "value1|value2|value3"
   LDAP_SYNC_USERNAME_FIELD = None 
   LDAP_SYNC_REMOVED_USER_CALLBACKS = []
   #`adldap_sync.callbacks.removed_user_deactivate` and `adldap_sync.callbacks.removed_user_delete`
      
   #GROUPS
   LDAP_SYNC_GROUP = True
   LDAP_SYNC_GROUP_INCREMENTAL = True
   LDAP_SYNC_GROUP_SEARCH = '' 
   #I.e. "OU=Department,DC=example,DC=com" If you don't setup any, LDAP_SYNC_BIND_SEARCH is used. 
   LDAP_SYNC_GROUP_FILTER = '(objectClass=group)'
   LDAP_SYNC_GROUP_FILTER_INCREMENTAL = '(&(objectClass=group)(whenchanged>=?))'
   LDAP_SYNC_GROUP_ATTRIBUTES = { "cn": "name"}

   #GROUP MEMBERSHIP
   LDAP_SYNC_GROUP_MEMBERSHIP = True
   LDAP_SYNC_GROUP_MEMBERSHIP_DN_FIELD = 'distinguishedName'
   LDAP_SYNC_GROUP_MEMBERSHIP_FILTER = '(member:1.2.840.113556.1.4.1941:={distinguishedName})' 
   #Recursive group search on AD. If Group B is memberof Group A, and user is memberof Group B,
   # it will have membership on both Groups.
   LDAP_SYNC_GROUP_MEMBERSHIP_CREATE_IF_NOT_EXISTS = True
   #Create Groups if don't exist in Django. Useful if some of your group are out of search scope.
   LDAP_SYNC_GROUP_MEMBERSHIP_ADD_DEFAULT = [] 
   #  [('CN=Domain Users,CN=Users,DC=example,DC=com', {'cn': [b'Domain Users']}),]
   #IMPORTANT! AD behaves a bit weird with the Primary Group. There is no easy way to sync Primary 
   # group so you will always have 1 group less than expected. So I manually add it to all users,
   # pretty awful but enough for me, and way easier than dealing with SIDs on AD
   
   #INCREMENTAL
   LDAP_SYNC_INCREMENTAL_BETWEEN_FULL = 5
   #Each N incrementals the command will try a Full sync. This is to avoid drifting of changes, 
   # for any reason. It's a sanity check. With one each 7 days is enough, it depends on how often
   # you scheduled the incremental syncs.
   LDAP_SYNC_INCREMENTAL_TIME_OFFSET = 10
   #Incrementals are very sensitive to date and time, so to avoid clock skew problems I substract
   # 10 minutes to the datetime on query
   LDAP_SYNC_INCREMENTAL_TIMESTAMPFORMAT = "%Y%m%d%H%M%S.0Z"
   #AD time format, leave as it is.

