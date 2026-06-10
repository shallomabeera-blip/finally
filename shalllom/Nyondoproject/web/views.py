from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import *
from django.db import transaction 
from datetime import date, date, datetime
from django.db.models import Sum, F, Count
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import User 


def add_validation_messages(request, validation_error):
    if hasattr(validation_error, 'message_dict'):
        for field, errors in validation_error.message_dict.items():
            for error in errors:
                messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
    else:
        for error in validation_error.messages:
            messages.error(request, error)


def role_home(role):
    """Maps role names to their default dashboard URL names safely."""
    clean_role = str(role).upper().strip()
    
    # Map exact role values from User.ROLE_CHOICES to URL names
    if clean_role == 'STOCK':
        return 'stock'
    if clean_role == 'SALES':
        return 'sales'
    if clean_role == 'ADMIN':
        return 'admin_dashboard'
    
    # Fuzzy matching fallback for compatibility
    if 'STOCK' in clean_role or 'MANAGER' in clean_role:
        return 'stock'
    if 'SALES' in clean_role or 'ATTENDANT' in clean_role:
        return 'sales'
    return 'admin_dashboard'


def require_role(*allowed_roles):
    """Enforces role boundaries safely with fuzzy matching logic."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            # Fetch the user's role and standardize it to uppercase
            user_role = str(getattr(request.user, 'role', '')).upper()
            
            # Universal administrative override clearance
            if 'ADMIN' in user_role:
                return view_func(request, *args, **kwargs)

            # Check if any allowed roles are part of the user's role string
            for allowed in allowed_roles:
                if allowed.upper() in user_role:
                    return view_func(request, *args, **kwargs)

            # Access denied safety route
            messages.error(request, "Access denied: Redirected to your authorized department.")
            return redirect(role_home(user_role))

        return wrapper
    return decorator


#  CORE SYSTEM VIEWS (Login, Logout, Landing)

def index(request):
    """Public landing page shown before login."""
    if request.user.is_authenticated:
        return redirect(role_home(request.user.role))
    return render(request, 'index.html')


def login_view(request):
    """Handles secure workspace employee authentication processing."""
    if request.user.is_authenticated:
        return redirect(role_home(request.user.role))

    error_fields = []
    username_input = ''

    if request.method == 'POST':
        username_input = request.POST.get('username', '').strip()
        password_input = request.POST.get('password', '')

        if not username_input:
            error_fields.append('username')
        if not password_input:
            error_fields.append('password')

        if not error_fields:
            # Authenticate checks the password hash securely against the SQLite backend
            user = authenticate(request, username=username_input, password=password_input)

            if user is not None:
                if user.is_active:
                    login(request, user)
                    messages.success(request, f"Welcome back, {user.username}!")
                    return redirect(role_home(user.role))
                else:
                    messages.error(request, "Your account profile has been disabled by management.")
            else:
                messages.error(request, "Invalid credentials. Please verify your username and password.")
        else:
            messages.error(request, "Please fill in all required login fields.")

    return render(request, 'login.html', {
        'error_fields': error_fields,
        'username_input': username_input,
    })


def logout_view(request):
    """Logs the user out cleanly and clears the active session."""
    logout(request)
    messages.info(request, "You have logged out of the Nyondo Hardware terminal.")
    return redirect('login')



#  ACCOUNT CONTROL & BUSINESS VIEWS

@login_required
@require_role('ADMIN')
def user_management(request):
    """Allows administrators to track, view, and create user accounts."""
    if request.method == 'POST':
        form_action = request.POST.get('form_action')
        
        if form_action == 'create_user':
            username_input = request.POST.get('username', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email_input = request.POST.get('email', '').strip()
            password_input = request.POST.get('password', '')
            role_input = request.POST.get('role', '')

            error_fields = []
            if not username_input:
                error_fields.append('username')
            if not first_name:
                error_fields.append('first_name')
            if not last_name:
                error_fields.append('last_name')
            if not role_input:
                error_fields.append('role')
            if not password_input:
                error_fields.append('password')

            if error_fields:
                messages.error(request, "User creation failed: Please fill in all required fields.")
                return redirect(f"/users/?show_modal=add&error_fields={','.join(error_fields)}&username={username_input}&first_name={first_name}&last_name={last_name}&email={email_input}&role={role_input}")

            try:
                if User.objects.filter(username=username_input).exists():
                    raise ValidationError("An account with this username already exists.")

                # create_user securely hashes passwords so credentials validate on login
                new_user = User.objects.create_user(
                    username=username_input,
                    first_name=first_name,
                    last_name=last_name,
                    email=email_input,
                    password=password_input,
                    role=role_input
                )
                messages.success(request, f"Account for employee '{new_user.username}' created successfully!")
                return redirect('user_management')

            except ValidationError as e:
                add_validation_messages(request, e)
            except Exception as e:
                messages.error(request, f"An unexpected system exception occurred: {str(e)}")

    users = User.objects.all().order_by('username')
    
    context = {
        'employees': users,
        'role_choices': User.ROLE_CHOICES,
        'today': timezone.now(),
        'error_fields': request.GET.get('error_fields', '').split(',') if request.GET.get('error_fields') else [],
        'form_data': {
            'username': request.GET.get('username', ''),
            'first_name': request.GET.get('first_name', ''),
            'last_name': request.GET.get('last_name', ''),
            'email': request.GET.get('email', ''),
            'role': request.GET.get('role', ''),
        },
    }
    
    # Handle show_modal GET parameter for displaying modals
    show_modal = request.GET.get('show_modal')
    if show_modal == 'add':
        context['display_add_modal'] = True
    
    # Handle delete confirmation modal
    delete_id = request.GET.get('delete_id')
    if delete_id:
        context['delete_employee'] = get_object_or_404(User, id=delete_id)
        context['display_delete_modal'] = True
    
    return render(request, "user.html", context)




@require_role('ADMIN')
def admin_dashboard(request):
    user = request.user

    context = {
        'total_products': Product.objects.count(),
        'total_sales_count': Sale.objects.count(),
        'total_suppliers_count': SupplierCredit.objects.values('supplier').distinct().count(),
        'total_customers_count': DepositAccount.objects.count(),
        'today': timezone.now(),
    }

   
    
    if user.role in ['ADMIN', 'STORE_MANAGER']:
        # Fetch up to 5 items running low on stock
        context['dashboard_low_stock'] = Product.objects.filter(
            quantity_in_stock__lte=models.F('low_stock_threshold')
        ).order_by('quantity_in_stock')[:5]

    if user.role in ['ADMIN', 'SALES_ATTENDANT']:
       
        context['dashboard_recent_sales'] = Sale.objects.all().select_related('product').order_by('-date_processed')[:5]

    return render(request, 'admin_dashboard.html', context)


@require_role('STOCK', 'ADMIN')
def stock(request):
    if request.method == 'POST':
        form_action = request.POST.get('form_action')
        
        
        if form_action == 'create_category':
            cat_name = request.POST.get('category_name', '').strip()
            cat_desc = request.POST.get('category_description', '').strip()
            
            if not cat_name:
                messages.error(request, "Error: Category name is required.")
                return redirect(f'/stock/?show_modal=add_category&error_fields=category_name&category_name={cat_name}&category_description={cat_desc}')

            if Category.objects.filter(name__iexact=cat_name).exists():
                messages.error(request, "Error: This product category already exists.")
                return redirect(f'/stock/?show_modal=add_category&error_fields=category_name&category_name={cat_name}&category_description={cat_desc}')
            
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
            cost_raw = request.POST.get('cost_price', '').strip()
            sell_raw = request.POST.get('selling_price', '').strip()
            qty_raw = request.POST.get('quantity_in_stock', '').strip()
            thresh_raw = request.POST.get('low_stock_threshold', '').strip()

            # Track missing fields for UI feedback
            error_fields = []
            if not supplier_id: error_fields.append('supplier')
            if not category_id: error_fields.append('category')
            if not sku: error_fields.append('sku')
            if not name: error_fields.append('name')
            if not cost_raw: error_fields.append('cost_price')
            if not sell_raw: error_fields.append('selling_price')
            if not qty_raw: error_fields.append('quantity_in_stock')

            if error_fields:
                messages.error(request, "Product creation failed: Please fill in all required fields.")
                err_query = ",".join(error_fields)
                return redirect(f'/stock/?show_modal=add&error_fields={err_query}&sku={sku}&name={name}&spec={specifications}&cost={cost_raw}&sell={sell_raw}&qty={qty_raw}&thresh={thresh_raw}&supplier={supplier_id or ""}&category={category_id or ""}')

            if Product.objects.filter(sku=sku).exists():
                messages.error(request, "Error: This SKU is already registered.")
                return redirect(f'/stock/?show_modal=add&error_fields=sku&sku={sku}&name={name}&spec={specifications}&cost={cost_raw}&sell={sell_raw}&qty={qty_raw}&thresh={thresh_raw}&supplier={supplier_id or ""}&category={category_id or ""}')

            try:
                product = Product(
                    supplier_id=supplier_id,
                    category_id=category_id,
                    sku=sku,
                    name=name,
                    specifications=specifications,
                    cost_price=Decimal(cost_raw or '0'),
                    selling_price=Decimal(sell_raw or '0'),
                    quantity_in_stock=int(qty_raw or '0'),
                    low_stock_threshold=int(thresh_raw or '5'),
                )
                product.full_clean()
                product.save()
                messages.success(request, "Product added successfully!")
                return redirect('stock')
            except ValidationError as e:
                failed_fields = list(e.message_dict.keys()) if hasattr(e, 'message_dict') else []
                err_query = ",".join(failed_fields)
                add_validation_messages(request, e)
                return redirect(f'/stock/?show_modal=add&error_fields={err_query}&sku={sku}&name={name}&spec={specifications}&cost={cost_raw}&sell={sell_raw}&qty={qty_raw}&thresh={thresh_raw}&supplier={supplier_id or ""}&category={category_id or ""}')

        # ACTION: UPDATE PRODUCT
        elif form_action == 'update':
            product_id = request.POST.get('product_id')
            product = get_object_or_404(Product, id=product_id)

            # Capture raw values for validation
            cost_raw = request.POST.get('cost_price', '').strip()
            sell_raw = request.POST.get('selling_price', '').strip()
            qty_raw = request.POST.get('quantity_in_stock', '').strip()
            sku = request.POST.get('sku', '').strip()
            name = request.POST.get('name', '').strip()

            # Check for empty fields manually for immediate feedback
            error_fields = []
            if not sku: error_fields.append('sku')
            if not name: error_fields.append('name')
            if not cost_raw: error_fields.append('cost_price')
            if not sell_raw: error_fields.append('selling_price')
            if not qty_raw: error_fields.append('quantity_in_stock')

            if error_fields:
                messages.error(request, "Update Failed: Please fill in all required fields.")
                err_query = ",".join(error_fields)
                return redirect(f'/stock/?edit_id={product_id}&error_fields={err_query}')

            product.supplier_id = request.POST.get('supplier')
            product.category_id = request.POST.get('category')
            product.sku = sku
            product.name = name
            product.specifications = request.POST.get('specifications', '').strip()
            product.cost_price = Decimal(cost_raw or '0')
            product.selling_price = Decimal(sell_raw or '0')
            product.quantity_in_stock = int(qty_raw or '0')
            product.low_stock_threshold = int(request.POST.get('low_stock_threshold', '5'))

            try:
                product.full_clean()
                product.save()
                messages.success(request, f"{product.name} updated successfully!")
                return redirect('stock')
            except ValidationError as e:
                failed_fields = list(e.message_dict.keys()) if hasattr(e, 'message_dict') else []
                err_query = ",".join(failed_fields)
                add_validation_messages(request, e)
                return redirect(f'/stock/?edit_id={product_id}&error_fields={err_query}')

        # ACTION: DELETE PRODUCT
        elif form_action == 'delete':
            product_id = request.POST.get('product_id')
            get_object_or_404(Product, id=product_id).delete()
            messages.success(request, "Product removed completely.")
            return redirect('stock')

    
    products = Product.objects.all().select_related('supplier', 'category').order_by('name')
    suppliers = Supplier.objects.all().order_by('name')
    categories = Category.objects.all().order_by('name')
    
    context = {
        'products': products,
        'suppliers': suppliers,
        'categories': categories,
        'today': timezone.now(),
    }

    # General error field extraction for all modals
    context['error_fields'] = request.GET.get('error_fields', '').split(',') if request.GET.get('error_fields') else []

    if request.GET.get('show_modal') == 'add':
        context['display_add_modal'] = True
        context['form_data'] = {
            'sku': request.GET.get('sku', ''),
            'name': request.GET.get('name', ''),
            'specifications': request.GET.get('spec', ''),
            'cost_price': request.GET.get('cost', ''),
            'selling_price': request.GET.get('sell', ''),
            'quantity_in_stock': request.GET.get('qty', ''),
            'low_stock_threshold': request.GET.get('thresh', ''),
            'supplier_id': request.GET.get('supplier', ''),
            'category_id': request.GET.get('category', ''),
        }
    elif request.GET.get('show_modal') == 'add_category':
        context['display_add_category_modal'] = True
        context['form_data'] = {
            'category_name': request.GET.get('category_name', ''),
            'category_description': request.GET.get('category_description', ''),
        }

    edit_id = request.GET.get('edit_id')
    if edit_id:
        context['edit_product'] = get_object_or_404(Product, id=edit_id)
        context['display_edit_modal'] = True

    delete_id = request.GET.get('delete_id')
    if delete_id:
        context['delete_product'] = get_object_or_404(Product, id=delete_id)
        context['display_delete_modal'] = True

    return render(request, 'stock.html', context)




@require_role('SALES', 'ADMIN')
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

            # Track missing fields for UI feedback
            error_fields = []
            if not acc_num: error_fields.append('account_number')
            if not name: error_fields.append('customer_name')
            if not phone: error_fields.append('phone_number')
            if not nin: error_fields.append('national_id_nin')

            # Validate required fields
            if error_fields:
                messages.error(request, "Registration Failed: Please fill in all required fields.")
                err_query = ",".join(error_fields)
                return redirect(f"{request.path}?show_modal=add_account&acc_num={acc_num}&name={name}&phone={phone}&nin={nin}&balance={initial_deposit}&error_fields={err_query}")

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
                return redirect('deposit')
                
            except ValidationError as e:
                # Extract field names from ValidationError to highlight borders
                failed_fields = list(e.message_dict.keys()) if hasattr(e, 'message_dict') else []
                err_query = ",".join(failed_fields)
                # Safe handling if validation error contains a dict or flat list
                if hasattr(e, 'message_dict'):
                    for field, errors in e.message_dict.items():
                        for error in errors:
                            messages.error(request, f"Registration Failed: {error}")
                else:
                    for error in e.messages:
                        messages.error(request, f"Registration Failed: {error}")
                
                # Dynamic redirect with form data preserved
                return redirect(f"{request.path}?show_modal=add_account&acc_num={acc_num}&name={name}&phone={phone}&nin={nin}&balance={initial_deposit}&error_fields={err_query}")

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
    context = {
        'accounts': accounts,
        'today': timezone.now(),
    }

    if request.GET.get('show_modal') == 'add_account':
        context['display_add_modal'] = True
        context['error_fields'] = request.GET.get('error_fields', '').split(',') if request.GET.get('error_fields') else []
        # Preserve form values on validation error
        context['form_data'] = {
            'account_number': request.GET.get('acc_num', ''),
            'customer_name': request.GET.get('name', ''),
            'phone_number': request.GET.get('phone', ''),
            'national_id_nin': request.GET.get('nin', ''),
            'initial_balance': request.GET.get('balance', '0'),
        }

    top_up_id = request.GET.get('top_up_id')
    if top_up_id:
        context['target_account'] = get_object_or_404(DepositAccount, id=top_up_id)
        context['display_top_up_modal'] = True

    return render(request, 'deposits.html', context)


@require_role('SALES', 'ADMIN')
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

        # Track missing fields
        error_fields = []
        if not product_id: error_fields.append('product')
        if not qty_sold_raw: error_fields.append('quantity_sold')

        if error_fields:
            messages.error(request, "Transaction Failed: Please fill in all required fields.")
            err_query = ",".join(error_fields)
            return redirect(f'/sales/?show_modal=new_sale&error_fields={err_query}&product={product_id or ""}&quantity_sold={qty_sold_raw or ""}&requires_transport={t_param}&delivery_distance_km={distance}')

        product = get_object_or_404(Product, id=product_id)

        try:
            product.full_clean()
        except ValidationError as e:
            add_validation_messages(request, e)
            return redirect(f'/sales/?show_modal=new_sale&product={product_id}&quantity_sold={qty_sold}&requires_transport={t_param}&delivery_distance_km={distance}')

        if qty_sold <= 0:
            messages.error(request, "Transaction Failed: Quantity must be greater than zero.")
            return redirect(f'/sales/?show_modal=new_sale&product={product_id}&requires_transport={t_param}&delivery_distance_km={distance}&error_fields=quantity_sold')

        if distance < 0:
            messages.error(request, "Transaction Failed: Delivery distance cannot be negative.")
            return redirect(f'/sales/?show_modal=new_sale&product={product_id}&quantity_sold={qty_sold}&requires_transport={t_param}&delivery_distance_km={distance}&error_fields=delivery_distance_km')

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
        'rate_per_km': TRANSPORT_RATE_PER_KM,
        'today': timezone.now(),
    }

    
    if request.GET.get('show_modal') == 'new_sale':
        context['display_sale_modal'] = True  
        context['error_fields'] = request.GET.get('error_fields', '').split(',') if request.GET.get('error_fields') else []

   
    receipt_id = request.GET.get('view_receipt_id')
    if receipt_id:
        context['receipt'] = get_object_or_404(Sale, id=receipt_id)
        context['display_receipt_modal'] = True

    return render(request, 'sales.html', context)


@require_role('SALES', 'ADMIN')
def credit(request):

    if request.method == 'POST':
        form_action = request.POST.get('form_action')

        
        if form_action == 'create_credit':
            supplier_id = request.POST.get('supplier')
            invoice_num = request.POST.get('invoice_number', '').strip()
            total_amt_raw = request.POST.get('total_amount', '').strip()
            amt_paid_raw = request.POST.get('amount_paid', '').strip()
            due_date_str = request.POST.get('due_date')

            error_fields = []
            if not supplier_id:
                error_fields.append('supplier')
            if not invoice_num:
                error_fields.append('invoice_number')
            if not total_amt_raw:
                error_fields.append('total_amount')
            if not amt_paid_raw:
                error_fields.append('amount_paid')
            if not due_date_str:
                error_fields.append('due_date')

            if error_fields:
                messages.error(request, "Credit entry failed: Please fill in all required fields.")
                return redirect(f"/credit/?show_modal=add_credit&error_fields={','.join(error_fields)}&supplier={supplier_id or ''}&invoice_number={invoice_num}&total_amount={total_amt_raw}&amount_paid={amt_paid_raw}&due_date={due_date_str or ''}")

            total_amt = Decimal(total_amt_raw)
            amt_paid = Decimal(amt_paid_raw)

            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, "Error: Invalid due date format.")
                return redirect('/credit/?show_modal=add_credit')

            if total_amt <= 0:
                messages.error(request, "Error: Total invoice amount must be greater than zero.")
                return redirect('/credit/?show_modal=add_credit')

            if SupplierCredit.objects.filter(invoice_number=invoice_num).exists():
                messages.error(request, "Error: This supplier invoice reference number is already logged.")
                return redirect('/credit/?show_modal=add_credit')

            # Calculate balance_due before creating the object
            balance_due = total_amt - amt_paid
            
            credit_record = SupplierCredit(
                supplier_id=supplier_id,
                invoice_number=invoice_num,
                total_amount=total_amt,
                amount_paid=amt_paid,
                balance_due=balance_due,
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
                return redirect(f'/credit/?pay_id={credit_id}&error_fields=payment_amount')

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
        'today': timezone.now(),
        'error_fields': request.GET.get('error_fields', '').split(',') if request.GET.get('error_fields') else [],
        'form_data': {
            'supplier': request.GET.get('supplier', ''),
            'invoice_number': request.GET.get('invoice_number', ''),
            'total_amount': request.GET.get('total_amount', ''),
            'amount_paid': request.GET.get('amount_paid', ''),
            'due_date': request.GET.get('due_date', ''),
        },
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




# PAGE 1: SUPPLIER MANAGEMENT 
@require_role('STOCK', 'ADMIN')
def supplier_management(request):
    if request.method == 'POST':
        form_action = request.POST.get('form_action')

        if form_action == 'create':
            name = request.POST.get('name', '').strip()
            phone = request.POST.get('phone', '').strip()
            error_fields = []

            if not name:
                error_fields.append('name')
            if not phone:
                error_fields.append('phone')

            if error_fields:
                messages.error(request, "Supplier creation failed: Please fill in all required fields.")
                return redirect(f"/suppliers/?show_modal=add&error_fields={','.join(error_fields)}&name={name}&phone={phone}")

            if Supplier.objects.filter(name__iexact=name).exists():
                messages.error(request, "Error: This supplier name already exists.")
                return redirect(f"/suppliers/?show_modal=add&error_fields=name&name={name}&phone={phone}")

            Supplier.objects.create(name=name, phone=phone)
            messages.success(request, f"Supplier '{name}' added successfully!")
            return redirect('supplier_management')

        elif form_action == 'update':
            supplier_id = request.POST.get('supplier_id')
            supplier = get_object_or_404(Supplier, id=supplier_id)
            
            name = request.POST.get('name', '').strip()
            phone = request.POST.get('phone', '').strip()
            error_fields = []

            if not name:
                error_fields.append('name')
            if not phone:
                error_fields.append('phone')

            if error_fields:
                messages.error(request, "Supplier update failed: Please fill in all required fields.")
                return redirect(f"/suppliers/?edit_id={supplier_id}&error_fields={','.join(error_fields)}&name={name}&phone={phone}")

            if Supplier.objects.filter(name__iexact=name).exclude(id=supplier_id).exists():
                messages.error(request, "Error: This supplier name already exists.")
                return redirect(f"/suppliers/?edit_id={supplier_id}&error_fields=name&name={name}&phone={phone}")

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
    context = {
        'suppliers': suppliers,
        'today': timezone.now(),
        'error_fields': request.GET.get('error_fields', '').split(',') if request.GET.get('error_fields') else [],
        'form_data': {
            'name': request.GET.get('name', ''),
            'phone': request.GET.get('phone', ''),
        },
    }

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


#  INVENTORY REPORTS
@require_role('STOCK', 'ADMIN')
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


#  CREDIT AGING REPORT 
@require_role('SALES', 'ADMIN')
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


# PAGE 5: SETTINGS/CONFIGURATION 
@require_role('ADMIN')
def settings(request):
    # Get or create system settings
    settings_obj = SystemSettings.get_settings()
    
    if request.method == 'POST':
        business_name = request.POST.get('business_name', '').strip()
        if not business_name:
            messages.error(request, "Business name is required.")
            return redirect('/settings/?error_fields=business_name')

        # Update business info
        settings_obj.business_name = business_name
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
        'error_fields': request.GET.get('error_fields', '').split(',') if request.GET.get('error_fields') else [],
        'transport_rate': settings_obj.transport_rate_per_km,
        'business_name': settings_obj.business_name,
        'business_phone': settings_obj.business_phone,
        'business_email': settings_obj.business_email,
        'free_delivery_threshold': settings_obj.free_delivery_threshold,
        'low_stock_default': settings_obj.default_low_stock_threshold,
        'currency': settings_obj.currency,
        'timezone': settings_obj.timezone,
        'today': timezone.now(),
    }

    return render(request, 'settings.html', context)


# USER PROFILE
@require_role('SALES', 'STOCK', 'ADMIN')
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
        'today': timezone.now(),
    }

    return render(request, 'user_profile.html', context)


#  SALES HISTORY & RECEIPTS
@require_role('SALES', 'ADMIN')
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
