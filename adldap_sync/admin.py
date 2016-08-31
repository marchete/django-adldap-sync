
from django.contrib import admin

from .models import ADldap_Sync  # ,Employee

admin.site.register(ADldap_Sync)


## Define an inline admin descriptor for Employee model
## which acts a bit like a singleton
#class EmployeeInline(admin.StackedInline):
#    model = Employee
#    can_delete = False
#    verbose_name_plural = 'employees'

## Define a new User admin
#class UserAdmin(BaseUserAdmin):
#    inlines = (EmployeeInline)

## Re-register UserAdmin
#admin.site.unregister(User)
#admin.site.register(User, UserAdmin)
