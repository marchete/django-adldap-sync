#django-adldap-sync


Overhaul of [django-ldap-sync].

django-adldap-sync provides a Django management command that synchronizes LDAP
users, groups and memberships from an Active Directory server. 

This synchronization is performed each time the management command is run and
can be fired manually on demand, via an automatic cron script or as a periodic
[Celery]_ task.

### Features
  - Works on Python 3.5 and Django 1.10, tested both on Windows 10 and Centos 7.2. Untested on other Python versions or Django
  - Tested against Active Directory on Windows Server 2008R2. Must work on any other AD, and maybe another generic LDAP server.
  - One way read-only sync from Active Directory/LDAP to Django, with AD/LDAP server failover.
  - Synchronizes Users, Groups and Group Memberships. AD Primary Group is added via a manual config in settings.py.
  - Allows incremental synchronization, based on the last timestamp. This reduces the sync time to the minimum.
  - Synchronizes AD User Data to both User Model and User Profiles (without external callbacks).
  - Synchronizes thumbnailPhoto or jpegPhoto to an ImageField.

### Installation
```sh
pip install django_adldap_sync
```
You must add the app configuration on your `settings.py` file (at least the minimal config as below). 
Then update your database:
```sh
python manage.py makemigrations adldap_sync
python manage.py migrate
```
It should create a new table called `adldap_sync`. It keeps track of the last time the system was sync'ed

### Minimal config on `settings.py` 
Be sure that `USE_TZ = True` . Incremental Sync uses TimeZone

On `settings.py` add this at the end of the file, and configure the values:
```python
INSTALLED_APPS.append('adldap_sync');
LDAP_SYNC_BIND_URI = ["ldap://dc1.example.com:389","ldap://dc2.example.com:389",] 
#You need at least 1, but is open to additional failovers. Incremental syncs are bound to the server URI
#This is because the whenChanged attribute on AD is server-based, it doesn't replicate on others.
LDAP_SYNC_BIND_SEARCH = "DC=example,DC=com"
LDAP_SYNC_BIND_DN = "CN=Django,OU=Users,DC=example,DC=com"  #User's distinguishedName to sync data.
LDAP_SYNC_BIND_PASS = "MyPassword"
#Important note about the User!! Please don't use a Domain Admin here. Just create a limited AD User 
# and add delegation rights to read group/user info!!!! Using a Domain Admin to Sync data is a terrible
# bad practice, you are warned.
```      

With that you have a Synchronization from AD to Django (Users, Groups and Memberships), with a Full import each 5 incrementals.

### Minimal config with an User Profile 
Add this to the previous `settings.py`
```python
LDAP_SYNC_USER_EXTRA_ATTRIBUTES = ['userAccountControl','company','department','distinguishedName','division',\
  'extensionName','manager','mobile','physicalDeliveryOfficename','title','thumbnailPhoto']
#Or the ones you need from the AD, and create a model accordly
LDAP_SYNC_USER_EXTRA_PROFILES = [adldap_sync.Employee] # appname.modelname, like adldap_sync.Employee
LDAP_SYNC_USER_CHANGE_FIELDCASE = "lower" #None,"lower","upper"
LDAP_SYNC_USER_THUMBNAILPHOTO_NAME = "{username}_{uuid4}.jpg" 
   #It allows the parameters {username}, {uuid4} and datetime.strftime
```
Change the values to the one you need. On `models.py` and `admin.py` there are samples of a working User Profile.
You can add the AD Fields you need. By default AD fields are camelCase, it's preferred to lowercase them to fit
Django best practices.
The model MUST use the same names as the AD fields, only lowercased (if `LDAP_SYNC_USER_CHANGE_FIELDCASE = "lower"`
is used).


### Manual Sync (and `cron.d` scheduling)

```sh
python manage.py syncldap
```
To force a full search:
```sh
python manage.py syncldap full
```
To force an incremental search:
```sh
python manage.py syncldap incremental
```
The first synchronization will always be FULL

### Scheduled Sync on `settings.py`
```python
from datetime import timedelta
      #One full sync each 5 days: 1sync/hour x 24 hours x 5 days = 120 syncs
      LDAP_SYNC_INCREMENTAL_BETWEEN_FULL = 120
      CELERYBEAT_SCHEDULE = {
          'synchronize_local_users': {
              'task': 'adldap_sync.tasks.syncldap',
              'schedule': timedelta(minutes=60),
          }
      }
```      
### Full config settings
```python
    LDAP_SYNC_BIND_URI = [] 
    #A string or an array for failover, i.e.  ["ldap://dc1.example.com:389","ldap://dc2.example.com:389",]
    LDAP_SYNC_BIND_DN = ''  #AD User to search. DON'T USE AN ADMIN ACCOUNT!!!!!
    LDAP_SYNC_BIND_PASS = '' #The ldap user password
    LDAP_SYNC_BIND_SEARCH = '' #I.e. "OU=Department,DC=example,DC=com"
    LDAP_SYNC_BIND_PAGESIZE = 200 #Used on PagedResultsSearchObject, for paging LDAP queries

    #USERS
    LDAP_SYNC_USER = True    #With False it will NOT Sync either users or group memberships
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
```

      
### Dependencies
pyldap

### TODO

- Documentation::
- Create PIP Installer::
- LDAPs ::
- Unit Tests ::

FAQ
----------
- Why Full Sync is so slow?:

Because of Group Memberships, without memberships you only need 2 LDAP queries, but with memberships the system makes 2+N queries,
 where N is the number of users. I need a query per user to make a recursive group search (member of a subgroup of another group).

- Why the module needs a table on database?:

To keep track of whenChanged, the timestamp needed to do an incremental synchronization

- Weird coding style:

I'm not a Python guy, I tried to keep PEP8 and Django guidelines. 
The main exception are in User Profile. Profile fields must match the ones in AD (only lowercased), so words are not separated with _

- Horrible Documentation:

I know, but all the configurable settings are there, with their default values. 

- Can I have more than 1 User Profile?:

Yes, you can sync it either directly (adding it to the LDAP_SYNC_USER_EXTRA_PROFILES list) or via callbacks.
LDAP_SYNC_USER_CALLBACKS is more flexible as you may have any field name, and do extra checking.
But for me the EXTRA PROFILES option works ok, and is way easier.

- Can I add more than 1 Group Membership in LDAP_SYNC_GROUP_MEMBERSHIP_ADD_DEFAULT?:

Yes. The main use is to overcome the AD Primary Group limitation (it's weird to retrieve), but can be used to add more groups.

- I don't see the thumbnailPhoto on my system:

Maybe you don't have correctly configured the media or static folder, see [Django Managing static files]
Then on templates you can use `{{ request.user.employee.thumbnailphoto.url }}` to link it

[django-ldap-sync]: https://github.com/jbittel/django-ldap-sync
[Celery]: http://www.celeryproject.org
[Django Managing static files]: https://docs.djangoproject.com/es/1.10/howto/static-files/
