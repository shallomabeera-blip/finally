from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import *
from decimal import Decimal
from django.db import transaction 
from datetime import date, date, datetime
from django.db.models import Sum, F, Count
from django.contrib.auth import get_user_model


def index(request):
    return render(request, 'index.html')
@login_required(login_url='/')
def user_management(request):
    """ Renders the active personnel ledger list and handling tab frames """
    # AUTHENTICATION GUARD: Restrict access strictly to ADMIN role profiles
    if getattr(request.user, 'role', '') != 'ADMIN':
        raise PermissionDenied  # Redirects to HTTP 403 Forbidden page

    users = CustomUser.objects.all().order_by('-is_active', 'username')
    return render(request, "users.html", {
        "users": users
    })




# @login_required(login_url='login')
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

            if selling_price <= cost_price:
                messages.error(request, "Error: Selling price must exceed cost price.")
                return redirect('/stock/?show_modal=add')
            elif Product.objects.filter(sku=sku).exists():
                messages.error(request, "Error: This SKU is already registered.")
                return redirect('/stock/?show_modal=add')
            else:
                Product.objects.create(
                    supplier_id=supplier_id, category_id=category_id, sku=sku, name=name,
                    specifications=specifications, cost_price=cost_price, 
                    selling_price=selling_price, quantity_in_stock=quantity, low_stock_threshold=threshold
                )
                messages.success(request, "Product added successfully!")
                return redirect('stock')

        # ACTION: UPDATE PRODUCT
        elif form_action == 'update':
            product_id = request.POST.get('product_id')
            product = get_object_or_404(Product, id=product_id)
            
            cost_price = Decimal(request.POST.get('cost_price', '0'))
            selling_price = Decimal(request.POST.get('selling_price', '0'))

            if selling_price <= cost_price:
                messages.error(request, "Update Failed: Selling price must exceed cost price.")
                return redirect(f'/stock/?edit_id={product_id}')
            else:
                product.supplier_id = request.POST.get('supplier')
                product.category_id = request.POST.get('category')
                product.sku = request.POST.get('sku', '').strip()
                product.name = request.POST.get('name', '').strip()
                product.specifications = request.POST.get('specifications', '').strip()
                product.cost_price = cost_price
                product.selling_price = selling_price
                product.quantity_in_stock = int(request.POST.get('quantity_in_stock', '0'))
                product.low_stock_threshold = int(request.POST.get('low_stock_threshold', '5'))
                product.save()
                messages.success(request, f"{product.name} updated successfully!")
                return redirect('stock')

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
        qty_sold = int(qty_sold_raw) if qty_sold_raw else 0
        distance = Decimal(distance_raw) if distance_raw else Decimal('0')

        # Convert boolean state to clean string component parameter mappings for redirects
        t_param = 'on' if transport_toggle else ''

        if not product_id:
            messages.error(request, "Transaction Failed: Please select a valid product.")
            return redirect('/sales/?show_modal=new_sale')

        product = get_object_or_404(Product, id=product_id)

      
        if qty_sold <= 0:
            messages.error(request, "Transaction Failed: Quantity must be greater than zero.")
            return redirect(f'/sales/?show_modal=new_sale&product={product_id}&requires_transport={t_param}&delivery_distance_km={distance}')

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
            if customer_account.current_balance < grand_total:
                messages.error(request, f"Transaction Failed: Insufficient customer funds! Balance is UGX {customer_account.current_balance}.")
                return redirect(f'/sales/?show_modal=new_sale&product={product_id}&quantity_sold={qty_sold}&customer_account={account_id}&requires_transport={t_param}&delivery_distance_km={distance}')

        
        with transaction.atomic():
            product.quantity_in_stock -= qty_sold
            product.save()

            if payment_method == 'DEPOSIT_SCHEME' and customer_account:
                customer_account.current_balance -= grand_total
                customer_account.save()

            sale_invoice = Sale.objects.create(
                product=product, customer_account=customer_account, quantity_sold=qty_sold, 
                unit_price=product.selling_price, product_total=product_total, requires_transport=transport_toggle,
                delivery_distance_km=distance, transport_charge=transport_charge,
                grand_total=grand_total, payment_method=payment_method
            )

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

            SupplierCredit.objects.create(
                supplier_id=supplier_id, invoice_number=invoice_num,
                total_amount=total_amt, amount_paid=amt_paid, due_date=due_date
            )
            messages.success(request, "New supplier credit transaction logged successfully!")
            return redirect('credit')

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
            
            # Smart Redirecting based on user roles
            if user.role == 'SALES_ATTENDANT':
                return redirect('sales')
            elif user.role == 'STORE_MANAGER':
                return redirect('stock')
            else:
                return redirect('reports')
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
