from django.contrib import admin

# Register your models here.
from django.contrib.auth.admin import UserAdmin
from .models import *

admin.site.register(Supplier)
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(DepositAccount)
admin.site.register(Sale)
admin.site.register(SupplierCredit)
admin.site.register(SystemSettings)
admin.site.register(User)