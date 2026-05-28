from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import Category, DepositAccount, Product, Sale, Supplier, SupplierCredit, User


class NegativeInputValidationTests(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(name="Test Supplier", phone="0771234567")
        self.category = Category.objects.create(name="Test Category")
        self.product = Product.objects.create(
            supplier=self.supplier,
            category=self.category,
            sku="SKU-TEST-001",
            name="Test Product",
            specifications="",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
            quantity_in_stock=10,
            low_stock_threshold=2,
        )

    def test_stock_rejects_negative_prices_and_quantity(self):
        response = self.client.post(
            reverse("stock"),
            {
                "form_action": "create",
                "supplier": self.supplier.id,
                "category": self.category.id,
                "sku": "SKU-NEG-001",
                "name": "Negative Product",
                "specifications": "",
                "cost_price": "-50",
                "selling_price": "-1",
                "quantity_in_stock": "-3",
                "low_stock_threshold": "-1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(sku="SKU-NEG-001").exists())

    def test_sales_reject_negative_delivery_distance(self):
        response = self.client.post(
            reverse("sales"),
            {
                "product": self.product.id,
                "quantity_sold": "2",
                "payment_method": "CASH",
                "customer_account": "",
                "requires_transport": "on",
                "delivery_distance_km": "-5",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Sale.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, 10)

    def test_credit_rejects_negative_amount_paid(self):
        initial_count = SupplierCredit.objects.count()

        response = self.client.post(
            reverse("credit"),
            {
                "form_action": "create_credit",
                "supplier": self.supplier.id,
                "invoice_number": "INV-NEG-001",
                "total_amount": "1000",
                "amount_paid": "-100",
                "due_date": "2026-06-30",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SupplierCredit.objects.count(), initial_count)

    def test_deposit_rejects_negative_initial_balance(self):
        response = self.client.post(
            reverse("deposit"),
            {
                "form_action": "create_account",
                "account_number": "ACC-NEG-001",
                "customer_name": "Negative Customer",
                "phone_number": "0771234567",
                "national_id_nin": "CM123456789012",
                "initial_balance": "-500",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(DepositAccount.objects.filter(account_number="ACC-NEG-001").exists())


class RoleAccessTests(TestCase):
    def setUp(self):
        self.sales_user = User.objects.create_user(
            username="sales_user",
            password="password123",
            role="SALES_ATTENDANT",
        )
        self.store_user = User.objects.create_user(
            username="store_user",
            password="password123",
            role="STORE_MANAGER",
        )
        self.admin_user = User.objects.create_user(
            username="admin_user",
            password="password123",
            role="ADMIN",
        )

    def test_sales_user_cannot_access_stock(self):
        self.client.force_login(self.sales_user)

        response = self.client.get(reverse("stock"))

        self.assertRedirects(response, reverse("sales"))

    def test_store_manager_cannot_access_sales(self):
        self.client.force_login(self.store_user)

        response = self.client.get(reverse("sales"))

        self.assertRedirects(response, reverse("stock"))

    def test_admin_can_access_all_sections(self):
        self.client.force_login(self.admin_user)

        stock_response = self.client.get(reverse("stock"))
        sales_response = self.client.get(reverse("sales"))
        reports_response = self.client.get(reverse("reports"))
        user_management_response = self.client.get(reverse("user_management"))

        self.assertEqual(stock_response.status_code, 200)
        self.assertEqual(sales_response.status_code, 200)
        self.assertEqual(reports_response.status_code, 200)
        self.assertEqual(user_management_response.status_code, 200)
