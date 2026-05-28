from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate, login, logout
from .models import *
from django.db import transaction 
from datetime import date, date, datetime
from django.db.models import Sum, F, Count
from django.contrib.auth import get_user_model


def add_validation_messages(request, validation_error):
    if hasattr(validation_error, 'message_dict'):
        for field, errors in validation_error.message_dict.items():
            for error in errors:
                messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
    else:
        for error in validation_error.messages:
            messages.error(request, error)


def role_home(role):
    if role == 'STORE_MANAGER':
        return 'stock'
    if role == 'SALES_ATTENDANT':
        return 'sales'
    return 'reports'


def require_role(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            user_role = getattr(request.user, 'role', '')
            if user_role == 'ADMIN' or user_role in allowed_roles:
                return view_func(request, *args, **kwargs)

            messages.error(request, "Access denied: you do not have permission to view this section.")
            return redirect(role_home(user_role))

        return wrapper

    return decorator


def index(request):
    return render(request, 'index.html')
@require_role('ADMIN')
def user_management(request):
    users = User.objects.all().order_by('username')
    return render(request, "user.html", {
        'employees': users,
        'role_choices': User.ROLE_CHOICES,
    })




@require_role('ADMIN')
def admin_dashboard(request):
    user = request.user

    
    context = {
        'total_products': Product.objects.count(),
        'total_sales_count': Sale.objects.count(),
        'total_suppliers_count': SupplierCredit.objects.values('supplier').distinct().count(),
        'total_customers_count': DepositAccount.objects.count(),
    }

   
    
    if user.role in ['ADMIN', 'STORE_MANAGER']:
        # Fetch up to 5 items running low on stock
        context['dashboard_low_stock'] = Product.objects.filter(
            quantity_in_stock__lte=models.F('low_stock_threshold')
        ).order_by('quantity_in_stock')[:5]

    if user.role in ['ADMIN', 'SALES_ATTENDANT']:
       
        context['dashboard_recent_sales'] = Sale.objects.all().select_related('product').order_by('-date_processed')[:5]

    return render(request, 'admin_dashboard.html', context)


@require_role('STORE_MANAGER', 'ADMIN')
def stock(request):
    if request.method == 'POST':
        form_action = request.POST.get('form_action')
        
        
        if form_action == 'create_category':
            cat_name = request.POST.get('category_name', '').strip()
            cat_desc = request.POST.get('category_description', '').strip()
            
            if Category.objects.filter(name__iexact=cat_name).exists():
                messages.error(request, "Error: This product category already exists.")
                return redirect('/stock/?show_modal=add_category')
            
            Category.objects.create(name=cat_name, description=cat_desc)
            messages.success(request, f"Category '{cat_name}' added successfully!")
            return redirect('/stock/?show_modal=add') # Send them right back to add product popup

        # ACTION: CREATE PRODUCT
        elif form_action == 'create':
            supplier_id = request.POST.get('supplier')
            category_id = request.POST.get('category')
            sku = request.POST.get('sku', '').strip()
            name = request.POST.get('name', '').strip()
            specifications = request.POST.get('specifications', '').strip()
            cost_price = Decimal(request.POST.get('cost_price', '0'))
            selling_price = Decimal(request.POST.get('selling_price', '0'))
            quantity = int(request.POST.get('quantity_in_stock', '0'))
            threshold = int(request.POST.get('low_stock_threshold', '5'))

            if Product.objects.filter(sku=sku).exists():
                messages.error(request, "Error: This SKU is already registered.")
                return redirect('/stock/?show_modal=add')

            product = Product(
                supplier_id=supplier_id,
                category_id=category_id,
                sku=sku,
                name=name,
                specifications=specifications,
                cost_price=cost_price,
                selling_price=selling_price,
                quantity_in_stock=quantity,
                low_stock_threshold=threshold,
            )

            try:
                product.full_clean()
                product.save()
                messages.success(request, "Product added successfully!")
                return redirect('stock')
            except ValidationError as e:
                add_validation_messages(request, e)
                return redirect('/stock/?show_modal=add')

        # ACTION: UPDATE PRODUCT
        elif form_action == 'update':
            product_id = request.POST.get('product_id')
            product = get_object_or_404(Product, id=product_id)

            cost_price = Decimal(request.POST.get('cost_price', '0'))
            selling_price = Decimal(request.POST.get('selling_price', '0'))

            product.supplier_id = request.POST.get('supplier')
            product.category_id = request.POST.get('category')
            product.sku = request.POST.get('sku', '').strip()
            product.name = request.POST.get('name', '').strip()
            product.specifications = request.POST.get('specifications', '').strip()
            product.cost_price = cost_price
            product.selling_price = selling_price
            product.quantity_in_stock = int(request.POST.get('quantity_in_stock', '0'))
            product.low_stock_threshold = int(request.POST.get('low_stock_threshold', '5'))

            try:
                product.full_clean()
                product.save()
                messages.success(request, f"{product.name} updated successfully!")
                return redirect('stock')
            except ValidationError as e:
                add_validation_messages(request, e)
                return redirect(f'/stock/?edit_id={product_id}')

        # ACTION: DELETE PRODUCT
        elif form_action == 'delete':
            product_id = request.POST.get('product_id')
            get_object_or_404(Product, id=product_id).delete()
            messages.success(request, "Product removed completely.")
            return redirect('stock')

    
    products = Product.objects.all().select_related('supplier', 'category').order_by('name')
    suppliers = Supplier.objects.all().order_by('name')
    categories = Category.objects.all().order_by('name')
    
    context = {'products': products, 'suppliers': suppliers, 'categories': categories}

    if request.GET.get('show_modal') == 'add':
        context['display_add_modal'] = True
    elif request.GET.get('show_modal') == 'add_category':
        context['display_add_category_modal'] = True

    edit_id = request.GET.get('edit_id')
    if edit_id:
        context['edit_product'] = get_object_or_404(Product, id=edit_id)
        context['display_edit_modal'] = True

    delete_id = request.GET.get('delete_id')
    if delete_id:
        context['delete_product'] = get_object_or_404(Product, id=delete_id)
        context['display_delete_modal'] = True

    return render(request, 'stock.html', context)




@require_role('ADMIN')
def deposit(request):
    if request.method == 'POST':
        form_action = request.POST.get('form_action')

        if form_action == 'create_account':
            acc_num = request.POST.get('account_number', '').strip()
            name = request.POST.get('customer_name', '').strip()
            phone = request.POST.get('phone_number', '').strip()
            nin = request.POST.get('national_id_nin', '').strip().upper()
            
            try:
                initial_deposit = Decimal(request.POST.get('initial_balance', '0'))
            except (ValueError, TypeError):
                initial_deposit = Decimal('0')

            try:
                new_account = DepositAccount(
                    account_number=acc_num, 
                    customer_name=name,
                    phone_number=phone, 
                    national_id_nin=nin, 
                    current_balance=initial_deposit
                )
                new_account.full_clean() 
                new_account.save()
                messages.success(request, f"Deposit profile created successfully for {name}!")
                return redirect('deposit') # Changed from deposit_dashboard to stay consistent
                
            except ValidationError as e:
                # Safe handling if validation error contains a dict or flat list
                if hasattr(e, 'message_dict'):
                    for field, errors in e.message_dict.items():
                        for error in errors:
                            messages.error(request, f"Registration Failed: {error}")
                else:
                    for error in e.messages:
                        messages.error(request, f"Registration Failed: {error}")
                
                # Dynamic redirect to prevent broken routing loops
                return redirect(f"{request.path}?show_modal=add_account")

        elif form_action == 'top_up':
            account_id = request.POST.get('account_id')
            
            try:
                amount = Decimal(request.POST.get('deposit_amount', '0'))
            except (ValueError, TypeError):
                amount = Decimal('0')
            
            if amount <= 0:
                messages.error(request, "Deposit Error: Amount must be greater than zero.")
                return redirect(f'{request.path}?top_up_id={account_id}')
                
            account = get_object_or_404(DepositAccount, id=account_id)
            account.current_balance += amount
            account.save()
            messages.success(request, f"UGX {amount:,} credited successfully to {account.customer_name}'s account.")
            return redirect('deposit')

    # GET requests processing loop
    accounts = DepositAccount.objects.all().order_by('customer_name')
    context = {'accounts': accounts}

    if request.GET.get('show_modal') == 'add_account':
        context['display_add_modal'] = True

    top_up_id = request.GET.get('top_up_id')
    if top_up_id:
        context['target_account'] = get_object_or_404(DepositAccount, id=top_up_id)
        context['display_top_up_modal'] = True

    return render(request, 'deposits.html', context)


@require_role('SALES_ATTENDANT', 'ADMIN')
def sales(request):
    TRANSPORT_RATE_PER_KM = Decimal('3000.00')

   
    if request.method == 'POST':
        product_id = request.POST.get('product')
        qty_sold_raw = request.POST.get('quantity_sold', '').strip()
        payment_method = request.POST.get('payment_method')
        account_id = request.POST.get('customer_account')
        
        # Explicit evaluation of both 'on' string value or raw template context value 
        transport_raw = request.POST.get('requires_transport', '').strip()
        transport_toggle = transport_raw in ['on', 'True']
        
        distance_raw = request.POST.get('delivery_distance_km', '').strip()

        # Safe parsing fallback for POST integers/decimals
        try:
            qty_sold = int(qty_sold_raw) if qty_sold_raw else 0
        except (TypeError, ValueError):
            qty_sold = 0

        try:
            distance = Decimal(distance_raw) if distance_raw else Decimal('0')
        except (TypeError, ValueError):
            distance = Decimal('0')

        # Convert boolean state to clean string component parameter mappings for redirects
        t_param = 'on' if transport_toggle else ''

        if not product_id:
            messages.error(request, "Transaction Failed: Please select a valid product.")
            return redirect('/sales/?show_modal=new_sale')

        product = get_object_or_404(Product, id=product_id)

        try:
            product.full_clean()
        except ValidationError as e:
            add_validation_messages(request, e)
            return redirect(f'/sales/?show_modal=new_sale&product={product_id}&quantity_sold={qty_sold}&requires_transport={t_param}&delivery_distance_km={distance}')

        if qty_sold <= 0:
            messages.error(request, "Transaction Failed: Quantity must be greater than zero.")
            return redirect(f'/sales/?show_modal=new_sale&product={product_id}&requires_transport={t_param}&delivery_distance_km={distance}')

        if distance < 0:
            messages.error(request, "Transaction Failed: Delivery distance cannot be negative.")
            return redirect(f'/sales/?show_modal=new_sale&product={product_id}&quantity_sold={qty_sold}&requires_transport={t_param}&delivery_distance_km={distance}')

        if product.quantity_in_stock < qty_sold:
            messages.error(request, f"Transaction Failed: Insufficient stock! Only {product.quantity_in_stock} left.")
            return redirect(f'/sales/?show_modal=new_sale&product={product_id}&quantity_sold={qty_sold}&requires_transport={t_param}&delivery_distance_km={distance}')

        # Final Financial Multipliers
        product_total = product.selling_price * qty_sold
        transport_charge = (distance * TRANSPORT_RATE_PER_KM) if transport_toggle else Decimal('0.00')
        grand_total = product_total + transport_charge

        customer_account = None
        if payment_method == 'DEPOSIT_SCHEME':
            if not account_id:
                messages.error(request, "Transaction Failed: Select a deposit scheme profile.")
                return redirect(f'/sales/?show_modal=new_sale&product={product_id}&quantity_sold={qty_sold}&requires_transport={t_param}&delivery_distance_km={distance}')

            customer_account = get_object_or_404(DepositAccount, id=account_id)
            try:
                customer_account.full_clean()
            except ValidationError as e:
                add_validation_messages(request, e)
                return redirect(f'/sales/?show_modal=new_sale&product={product_id}&quantity_sold={qty_sold}&customer_account={account_id}&requires_transport={t_param}&delivery_distance_km={distance}')

            if customer_account.current_balance < grand_total:
                messages.error(request, f"Transaction Failed: Insufficient customer funds! Balance is UGX {customer_account.current_balance}.")
                return redirect(f'/sales/?show_modal=new_sale&product={product_id}&quantity_sold={qty_sold}&customer_account={account_id}&requires_transport={t_param}&delivery_distance_km={distance}')

        with transaction.atomic():
            product.quantity_in_stock -= qty_sold
            product.save()

            if payment_method == 'DEPOSIT_SCHEME' and customer_account:
                customer_account.current_balance -= grand_total
                customer_account.save()

            sale_invoice = Sale(
                product=product,
                customer_account=customer_account,
                quantity_sold=qty_sold,
                unit_price=product.selling_price,
                product_total=product_total,
                requires_transport=transport_toggle,
                delivery_distance_km=distance,
                transport_charge=transport_charge,
                grand_total=grand_total,
                payment_method=payment_method,
            )

            try:
                sale_invoice.full_clean()
                sale_invoice.save()
            except ValidationError as e:
                add_validation_messages(request, e)
                return redirect(f'/sales/?show_modal=new_sale&product={product_id}&quantity_sold={qty_sold}&customer_account={account_id or ""}&requires_transport={t_param}&delivery_distance_km={distance}')

            messages.success(request, "Sale finalized successfully!")
            return redirect(f'/sales/?view_receipt_id={sale_invoice.id}')

    
    sales_history = Sale.objects.all().select_related('product', 'customer_account').order_by('-date_processed')
    available_products = Product.objects.filter(quantity_in_stock__gt=0).order_by('name')
    active_deposit_accounts = DepositAccount.objects.all().order_by('customer_name')

    context = {
        'sales': sales_history,
        'products': available_products,
        'deposit_accounts': active_deposit_accounts,
        'rate_per_km': TRANSPORT_RATE_PER_KM
    }

    
    if request.GET.get('show_modal') == 'new_sale':
        context['display_sale_modal'] = True
        
        # Read parameters from URL to build a real-time calculation preview
        preview_prod_id = request.GET.get('product')
        preview_qty_raw = request.GET.get('quantity_sold', '').strip()  
        preview_trans = request.GET.get('requires_transport') == 'on'
        preview_dist_raw = request.GET.get('delivery_distance_km', '').strip()

        if preview_prod_id and preview_qty_raw:
            try:
                p_prod = get_object_or_404(Product, id=preview_prod_id)
                p_qty = int(preview_qty_raw)
                p_dist = Decimal(preview_dist_raw) if preview_dist_raw else Decimal('0')
                
                p_subtotal = p_prod.selling_price * p_qty
                p_trans_fee = (p_dist * TRANSPORT_RATE_PER_KM) if preview_trans else Decimal('0.00')
                p_grand = p_subtotal + p_trans_fee
                
                context['preview_data'] = {
                    'product_name': p_prod.name,
                    'unit_price': p_prod.selling_price,
                    'quantity': p_qty,
                    'subtotal': p_subtotal,
                    'requires_transport': preview_trans,
                    'distance': p_dist,
                    'transport_fee': p_trans_fee,
                    'grand_total': p_grand
                }
            except (ValueError, TypeError):
                pass  

   
    receipt_id = request.GET.get('view_receipt_id')
    if receipt_id:
        context['receipt'] = get_object_or_404(Sale, id=receipt_id)
        context['display_receipt_modal'] = True

    return render(request, 'sales.html', context)


@require_role('ADMIN')
def credit(request):

    if request.method == 'POST':
        form_action = request.POST.get('form_action')

        
        if form_action == 'create_credit':
            supplier_id = request.POST.get('supplier')
            invoice_num = request.POST.get('invoice_number', '').strip()
            total_amt = Decimal(request.POST.get('total_amount', '0'))
            amt_paid = Decimal(request.POST.get('amount_paid', '0'))
            due_date_str = request.POST.get('due_date')

            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, "Error: Invalid due date format.")
                return redirect('/credit/?show_modal=add_credit')

            if total_amt <= 0:
                messages.error(request, "Error: Total invoice amount must be greater than zero.")
                return redirect('/stock/?show_modal=add_credit')

            if SupplierCredit.objects.filter(invoice_number=invoice_num).exists():
                messages.error(request, "Error: This supplier invoice reference number is already logged.")
                return redirect('/credit/?show_modal=add_credit')

            credit_record = SupplierCredit(
                supplier_id=supplier_id,
                invoice_number=invoice_num,
                total_amount=total_amt,
                amount_paid=amt_paid,
                due_date=due_date,
            )

            try:
                credit_record.full_clean()
                credit_record.save()
                messages.success(request, "New supplier credit transaction logged successfully!")
                return redirect('credit')
            except ValidationError as e:
                add_validation_messages(request, e)
                return redirect('/credit/?show_modal=add_credit')

        # ACTION B: RECORD REPAYMENT/CLEAR BALANCES
        elif form_action == 'pay_credit':
            credit_id = request.POST.get('credit_id')
            payment_amount = Decimal(request.POST.get('payment_amount', '0'))

            credit_record = get_object_or_404(SupplierCredit, id=credit_id)

            if payment_amount <= 0 or payment_amount > credit_record.balance_due:
                messages.error(request, f"Payment Failed: Amount must be between UGX 1 and UGX {credit_record.balance_due}.")
                return redirect(f'/credit/?pay_id={credit_id}')

            credit_record.amount_paid += payment_amount
            credit_record.save()  # Triggers our custom auto-balance calculations

            messages.success(request, f"Repayment of UGX {payment_amount} logged for {credit_record.supplier.name}.")
            return redirect('credit')

    # 2. RUN REGULAR VIEW DATA PREPARATION (GET)
    credits = SupplierCredit.objects.all().select_related('supplier').order_by('due_date')
    suppliers = Supplier.objects.all().order_by('name')
    
    # Simple alert threshold: Find accounts overdue or due within 7 days
    today = datetime.now().date()

    context = {
        'credits': credits,
        'suppliers': suppliers,
        'today': today,
    }

    if request.GET.get('show_modal') == 'add_credit':
        context['display_add_modal'] = True

    pay_id = request.GET.get('pay_id')
    if pay_id:
        context['target_credit'] = get_object_or_404(SupplierCredit, id=pay_id)
        context['display_payment_modal'] = True

    return render(request, 'credit.html', context)


@require_role('ADMIN')
def reports(request):
   
    today = date.today()

    
    daily_sales_records = Sale.objects.filter(date_processed__date=today)
    
   
    total_revenue = daily_sales_records.aggregate(total=Sum('grand_total'))['total'] or 0.00
    
    
    
    daily_profit = daily_sales_records.aggregate(
        profit=Sum((F('product__selling_price') - F('product__cost_price')) * F('quantity_sold'))
    )['profit'] or 0.00

    # 2. LIABILITIES & SAVINGS LEDGER METRICS (Extra Modules Cross-Check)
    total_customer_deposits = DepositAccount.objects.aggregate(total=Sum('current_balance'))['total'] or 0.00
    total_supplier_debts = SupplierCredit.objects.filter(balance_due__gt=0).aggregate(total=Sum('balance_due'))['total'] or 0.00

    # 3. LOW STOCK WARNING ALERTS PIPELINE
    # Finds items where current physical volume drops below their localized alert configuration numbers
    low_stock_items = Product.objects.filter(quantity_in_stock__lte=F('low_stock_threshold')).order_by('quantity_in_stock')
    low_stock_count = low_stock_items.count()

    # Pack metrics context into display variables
    context = {
        'total_revenue': total_revenue,
        'daily_profit': daily_profit,
        'total_customer_deposits': total_customer_deposits,
        'total_supplier_debts': total_supplier_debts,
        'low_stock_items': low_stock_items,
        'low_stock_count': low_stock_count,
        'today': today
    }

    return render(request, 'reports.html', context)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('reports') # Send directly if already logged in

    if request.method == 'POST':
        username_input = request.POST.get('username', '').strip()
        password_input = request.POST.get('password', '').strip()

        user = authenticate(request, username=username_input, password=password_input)
        
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect(role_home(user.role))
        else:
            messages.error(request, "Access Denied: Invalid username or security password.")
            return redirect('login')

    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    return redirect('login')




User = get_user_model()

def is_admin(user):
    return user.is_authenticated and user.role == 'ADMIN'

# @login_required(login_url='login')
# @user_passes_test(is_admin, login_url='login')
def user_management(request):
    # 1. PROCESS CORE ACTIONS FOR USER STORAGE (POST)
    if request.method == 'POST':
        form_action = request.POST.get('form_action')

        if form_action == 'create_user':
            username = request.POST.get('username', '').strip().lower()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            role = request.POST.get('role')
            password = request.POST.get('password', '')

            # Validation  checks
            if User.objects.filter(username=username).exists():
                messages.error(request, f"Registration Failed: Username '{username}' is already taken.")
                return redirect('/users/?show_modal=add_user')

            
            
            User.objects.create_user(
                username=username, first_name=first_name, last_name=last_name,
                email=email, role=role, password=password
            )
            messages.success(request, f"Success: Corporate staff account created for @{username}!")
            return redirect('user_management')

        elif form_action == 'delete_user':
            user_id = request.POST.get('user_id')

           
            if int(user_id) == request.user.id:
                messages.error(request, "Operation Aborted: You are currently signed into this profile account.")
                return redirect('user_management')

            employee_record = get_object_or_404(User, id=user_id)
            deleted_name = employee_record.username
            employee_record.delete()

            messages.success(request, f"Success: Access tokens revoked for employee account @{deleted_name}.")
            return redirect('user_management')

    
    
    employees_list = User.objects.all().order_by('username')
    role_options = User.ROLE_CHOICES # Dynamic models.py array fetch loop configuration
    
    context = {
        'employees': employees_list,
        'role_choices': role_options,
    }

    if request.GET.get('show_modal') == 'add_user':
        context['display_add_modal'] = True

    target_delete_id = request.GET.get('delete_id')
    if target_delete_id:
        context['delete_employee'] = get_object_or_404(User, id=target_delete_id)
        context['display_delete_modal'] = True

    return render(request, 'user.html', context)


# ===================== PAGE 1: SUPPLIER MANAGEMENT =====================
@require_role('STORE_MANAGER', 'ADMIN')
def supplier_management(request):
    if request.method == 'POST':
        form_action = request.POST.get('form_action')

        if form_action == 'create':
            name = request.POST.get('name', '').strip()
            phone = request.POST.get('phone', '').strip()

            if Supplier.objects.filter(name__iexact=name).exists():
                messages.error(request, "Error: This supplier name already exists.")
                return redirect('/suppliers/?show_modal=add')

            Supplier.objects.create(name=name, phone=phone)
            messages.success(request, f"Supplier '{name}' added successfully!")
            return redirect('supplier_management')

        elif form_action == 'update':
            supplier_id = request.POST.get('supplier_id')
            supplier = get_object_or_404(Supplier, id=supplier_id)
            
            name = request.POST.get('name', '').strip()
            phone = request.POST.get('phone', '').strip()

            if Supplier.objects.filter(name__iexact=name).exclude(id=supplier_id).exists():
                messages.error(request, "Error: This supplier name already exists.")
                return redirect(f'/suppliers/?edit_id={supplier_id}')

            supplier.name = name
            supplier.phone = phone
            supplier.save()
            messages.success(request, f"Supplier '{name}' updated successfully!")
            return redirect('supplier_management')

        elif form_action == 'delete':
            supplier_id = request.POST.get('supplier_id')
            supplier = get_object_or_404(Supplier, id=supplier_id)
            name = supplier.name
            supplier.delete()
            messages.success(request, f"Supplier '{name}' removed completely.")
            return redirect('supplier_management')

    suppliers = Supplier.objects.all().order_by('name')
    context = {'suppliers': suppliers}

    if request.GET.get('show_modal') == 'add':
        context['display_add_modal'] = True

    edit_id = request.GET.get('edit_id')
    if edit_id:
        context['edit_supplier'] = get_object_or_404(Supplier, id=edit_id)
        context['display_edit_modal'] = True

    delete_id = request.GET.get('delete_id')
    if delete_id:
        context['delete_supplier'] = get_object_or_404(Supplier, id=delete_id)
        context['display_delete_modal'] = True

    return render(request, 'supplier_management.html', context)


# ===================== PAGE 2: DETAILED INVENTORY REPORTS =====================
@require_role('STORE_MANAGER', 'ADMIN')
def inventory_reports(request):
    products = Product.objects.all().select_related('supplier', 'category').order_by('name')
    
    total_inventory_value = sum(
        p.quantity_in_stock * p.cost_price for p in products
    )
    
    total_potential_value = sum(
        p.quantity_in_stock * p.selling_price for p in products
    )
    
    total_profit_potential = total_potential_value - total_inventory_value
    
    low_stock_products = products.filter(
        quantity_in_stock__lte=models.F('low_stock_threshold')
    ).order_by('quantity_in_stock')
    
    high_value_products = products.order_by('-quantity_in_stock')[:10]
    
    product_profitability = [
        {
            'product': p,
            'profit_per_unit': p.selling_price - p.cost_price,
            'total_profit_potential': (p.selling_price - p.cost_price) * p.quantity_in_stock
        }
        for p in products
    ]
    product_profitability.sort(key=lambda x: x['total_profit_potential'], reverse=True)
    
    categories = Category.objects.all()
    category_stats = []
    for cat in categories:
        cat_products = products.filter(category=cat)
        cat_value = sum(p.quantity_in_stock * p.cost_price for p in cat_products)
        category_stats.append({
            'category': cat,
            'product_count': cat_products.count(),
            'total_value': cat_value,
            'items_in_stock': sum(p.quantity_in_stock for p in cat_products)
        })
    
    context = {
        'products': products,
        'total_inventory_value': total_inventory_value,
        'total_potential_value': total_potential_value,
        'total_profit_potential': total_profit_potential,
        'low_stock_products': low_stock_products,
        'product_profitability': product_profitability[:15],
        'category_stats': category_stats,
        'today': date.today(),
    }

    return render(request, 'inventory_reports.html', context)


# ===================== PAGE 3: CREDIT AGING REPORT =====================
@require_role('ADMIN')
def credit_aging(request):
    today = datetime.now().date()
    credits = SupplierCredit.objects.all().select_related('supplier').order_by('due_date')
    
    # Categorize by aging buckets
    overdue = []
    due_soon = []  # 1-30 days
    upcoming = []  # 31-60 days
    future = []    # 60+ days
    paid = []      # balance_due = 0
    
    for credit in credits:
        if credit.balance_due == 0:
            paid.append(credit)
        else:
            days_overdue = (today - credit.due_date).days
            if days_overdue > 0:
                overdue.append({'credit': credit, 'days': days_overdue})
            elif days_overdue > -30:
                due_soon.append({'credit': credit, 'days': abs(days_overdue)})
            elif days_overdue > -60:
                upcoming.append({'credit': credit, 'days': abs(days_overdue)})
            else:
                future.append({'credit': credit, 'days': abs(days_overdue)})
    
    # Summary statistics
    total_outstanding = SupplierCredit.objects.filter(balance_due__gt=0).aggregate(
        total=Sum('balance_due')
    )['total'] or 0
    
    supplier_summary = []
    for supplier in Supplier.objects.all():
        supplier_credits = SupplierCredit.objects.filter(supplier=supplier)
        total_owed = supplier_credits.filter(balance_due__gt=0).aggregate(
            total=Sum('balance_due')
        )['total'] or 0
        if total_owed > 0:
            supplier_summary.append({
                'supplier': supplier,
                'total_owed': total_owed,
                'credit_count': supplier_credits.count()
            })
    
    context = {
        'overdue': sorted(overdue, key=lambda x: x['days'], reverse=True),
        'due_soon': sorted(due_soon, key=lambda x: x['days']),
        'upcoming': sorted(upcoming, key=lambda x: x['days']),
        'future': sorted(future, key=lambda x: x['days']),
        'paid': paid,
        'total_outstanding': total_outstanding,
        'supplier_summary': supplier_summary,
        'today': today,
    }

    return render(request, 'credit_aging.html', context)


# ===================== PAGE 5: SETTINGS/CONFIGURATION =====================
@require_role('ADMIN')
def settings(request):
    # Get or create system settings
    settings_obj = SystemSettings.get_settings()
    
    if request.method == 'POST':
        # Update business info
        settings_obj.business_name = request.POST.get('business_name', settings_obj.business_name)
        settings_obj.business_phone = request.POST.get('business_phone', settings_obj.business_phone)
        settings_obj.business_email = request.POST.get('business_email', settings_obj.business_email)
        
        # Update transport settings
        try:
            transport_rate = Decimal(request.POST.get('transport_rate', settings_obj.transport_rate_per_km))
            settings_obj.transport_rate_per_km = transport_rate
        except (ValueError, TypeError):
            pass
        
        # Update free delivery threshold
        free_delivery = request.POST.get('free_delivery_threshold', '')
        if free_delivery:
            try:
                settings_obj.free_delivery_threshold = Decimal(free_delivery)
            except (ValueError, TypeError):
                pass
        
        # Update system preferences
        try:
            settings_obj.default_low_stock_threshold = int(request.POST.get('low_stock_default', settings_obj.default_low_stock_threshold))
        except (ValueError, TypeError):
            pass
        
        settings_obj.save()
        messages.success(request, "Settings updated successfully!")
        return redirect('settings')
    
    context = {
        'transport_rate': settings_obj.transport_rate_per_km,
        'business_name': settings_obj.business_name,
        'business_phone': settings_obj.business_phone,
        'business_email': settings_obj.business_email,
        'free_delivery_threshold': settings_obj.free_delivery_threshold,
        'low_stock_default': settings_obj.default_low_stock_threshold,
        'currency': settings_obj.currency,
        'timezone': settings_obj.timezone,
    }

    return render(request, 'settings.html', context)


# ===================== PAGE 6: USER PROFILE =====================
@require_role('SALES_ATTENDANT', 'STORE_MANAGER', 'ADMIN')
def user_profile(request):
    user = request.user
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_profile':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.save()
            
            messages.success(request, "Profile updated successfully!")
            return redirect('user_profile')
        
        elif action == 'change_password':
            old_password = request.POST.get('old_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            if not user.check_password(old_password):
                messages.error(request, "Current password is incorrect.")
                return redirect('user_profile')
            
            if new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
                return redirect('user_profile')
            
            if len(new_password) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
                return redirect('user_profile')
            
            user.set_password(new_password)
            user.save()
            
            messages.success(request, "Password changed successfully!")
            return redirect('login')
    
    # Get user activity
    user_sales = Sale.objects.filter(id__gte=1).count() if user.role == 'SALES_ATTENDANT' else None
    
    context = {
        'user': user,
        'role_display': user.get_role_display(),
        'user_sales': user_sales,
    }

    return render(request, 'user_profile.html', context)


# ===================== PAGE 7: SALES HISTORY & RECEIPTS =====================
@require_role('SALES_ATTENDANT', 'ADMIN')
def sales_history(request):
    # Get all sales with related data
    sales = Sale.objects.all().select_related('product', 'customer_account').order_by('-date_processed')
    
    # Summary statistics
    total_sales_count = sales.count()
    total_revenue = sales.aggregate(total=Sum('grand_total'))['total'] or Decimal('0')
    total_transport_revenue = sales.aggregate(total=Sum('transport_charge'))['total'] or Decimal('0')
    
    # Payment method breakdown
    cash_sales = sales.filter(payment_method='CASH').count()
    deposit_sales = sales.filter(payment_method='DEPOSIT_SCHEME').count()
    
    # Filter options
    payment_filter = request.GET.get('payment_method', '')
    date_filter = request.GET.get('date_from', '')
    
    if payment_filter:
        sales = sales.filter(payment_method=payment_filter)
    
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            sales = sales.filter(date_processed__date=filter_date)
        except ValueError:
            pass
    
    # Pagination simulation - show latest 100
    sales_display = sales[:100]
    
    # Get system settings for transport rate
    system_settings = SystemSettings.get_settings()
    
    context = {
        'sales': sales_display,
        'total_sales_count': total_sales_count,
        'total_revenue': total_revenue,
        'total_transport_revenue': total_transport_revenue,
        'cash_sales': cash_sales,
        'deposit_sales': deposit_sales,
        'today': date.today(),
        'transport_rate': system_settings.transport_rate_per_km,
    }
    
    # Handle receipt view modal
    receipt_id = request.GET.get('receipt_id')
    if receipt_id:
        context['receipt'] = get_object_or_404(Sale, id=receipt_id)
        context['display_receipt_modal'] = True
    
    return render(request, 'sales_history.html', context)
