from django.db import models
from django.core.exceptions import ValidationError
import re
from django.contrib.auth.models import AbstractUser

class Supplier(models.Model):
    name = models.CharField(max_length=255, unique=True)
    phone = models.CharField(max_length=20)

    def __str__(self):
        return self.name

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Category Name")
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class Product(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    sku = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255, unique=True)
    specifications = models.TextField(blank=True, null=True)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_in_stock = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=5)
    date_added = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.selling_price and self.cost_price:
            if self.selling_price <= self.cost_price:
                raise ValidationError({'selling_price': 'The selling price must be strictly greater than the cost price.'})

    def __str__(self):
        return f"{self.name} ({self.quantity_in_stock} left)"


# from django.db import models
# from .models import Product, DepositAccount  # Linking our previous modules
class DepositAccount(models.Model):
    account_number = models.CharField(max_length=20, unique=True, verbose_name="Scheme Account Number")
    customer_name = models.CharField(max_length=255, verbose_name="Salary Earner Name")
    
    # Validation targets
    phone_number = models.CharField(max_length=15, unique=True)
    national_id_nin = models.CharField(max_length=14, unique=True, verbose_name="National ID (NIN)")
    
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Available Balance (UGX)")
    date_registered = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        
        # 1. STRICT UGANDAN PHONE NUMBER VALIDATION RULE
        # Matches: +2567... (13 chars) or 07... (10 chars) for standard MTN/Airtel networks
        phone_cleaned = self.phone_number.strip().replace(" ", "")
        phone_regex = r'^(?:\+256|0)7[0-9]{8}$'
        if not re.match(phone_regex, phone_cleaned):
            raise ValidationError({
                'phone_number': 'Enter a valid Ugandan mobile phone number (e.g., 077XXXXXXX or +25678XXXXXXX).'
            })
            
        # 2. STRICT UGANDAN NATIONAL ID (NIN) VALIDATION RULE
        # Must be exactly 14 characters, starting with CM (Citizens Male) or CW (Citizens Female)
        nin_cleaned = self.national_id_nin.strip().upper()
        nin_regex = r'^(CM|CF)[A-Z0-9]{12}$'
        
        if len(nin_cleaned) != 14:
            raise ValidationError({
                'national_id_nin': f'The National ID (NIN) must be exactly 14 characters long. You entered {len(nin_cleaned)} characters.'
            })
            
        if not re.match(nin_regex, nin_cleaned):
            raise ValidationError({
                'national_id_nin': 'Invalid Ugandan NIN format. It must begin with "CM" or "CW" followed by 12 alphanumeric characters.'
            })

    def __str__(self):
        return f"{self.customer_name} - Balance: UGX {self.current_balance}"

class Sale(models.Model):
    PAYMENT_METHODS = [
        ('CASH', 'Cash / Mobile Money'),
        ('DEPOSIT_SCHEME', 'Salary Deposit Scheme'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sales')
    # Can be null if paid with cold hard cash
    customer_account = models.ForeignKey(DepositAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchases')
    
    quantity_sold = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    product_total = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Transport Automation
    requires_transport = models.BooleanField(default=False)
    delivery_distance_km = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    transport_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    grand_total = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='CASH')
    date_processed = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice #{self.id} - {self.product.name}"
    
class SupplierCredit(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='credits')
    invoice_number = models.CharField(max_length=100, unique=True, verbose_name="Supplier Invoice Ref")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Total Owed (UGX)")
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Amount Paid (UGX)")
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Remaining Balance (UGX)")
    due_date = models.DateField(verbose_name="Repayment Deadline")
    date_logged = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Automatically calculate remaining balance before storing in SQLite
        self.balance_due = self.total_amount - self.amount_paid
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.supplier.name} - Owed: UGX {self.balance_due}"
    
    


class User(AbstractUser):
    ROLE_CHOICES = [
        ('SALES_ATTENDANT', 'Sales Attendant'),
        ('STORE_MANAGER', 'Store Manager'),
        ('ADMIN', 'Accounts / Admin'),
    ]
    # Now 'models' can be referenced perfectly
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='SALES_ATTENDANT')

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
