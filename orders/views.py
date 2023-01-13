from datetime import datetime,date
from multiprocessing.dummy import current_process
from time import strftime
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.http import HttpResponse
from carts.models import CartItem
from .forms import OrderForm
from .models import Order, Payment
import json
from orders.models import OrderProduct
from store.models import Product
from django.core.mail  import EmailMessage
from django.template.loader import render_to_string

def payments(request):
    body = json.loads(request.body)
    order = Order.objects.get(user=request.user, is_ordered=False, order_number = body['orderID'])
    # store details on payment models
    payment = Payment(
        user = request.user,
        payment_id = body['transID'],
        payment_method = body['payment_method'],
        amount_paid = order.order_total,
        status = body['status'],

    )
    payment.save()

    # update order table
    order.payment = payment
    order.is_ordered = True
    order.save()
    
    # move the cart items to Order Product Table
    cart_items = CartItem.objects.filter(user=request.user)

    for item in cart_items:
        orderproduct = OrderProduct()
        orderproduct.order_id  = order.id
        orderproduct.payment = payment
        orderproduct.user_id = request.user.id
        orderproduct.product_id = item.product_id 
        orderproduct.quantity = item.quantity
        orderproduct.product_price = item.product.price
        orderproduct.ordered = True
        orderproduct.save()

        # adding variations to table
        cart_item  = CartItem.objects.get(id=item.id)
        product_variation  = cart_item.variations.all()
        orderproduct = OrderProduct.objects.get(id=orderproduct.id)
        orderproduct.variations.set(product_variation)
        orderproduct.save()

    # reduce stock quantity
        product = Product.objects.get(id=item.product_id)
        product.stock -= item.quantity
        product.save()


# clear cart
    CartItem.objects.filter(user=request.user).delete()
    # send order received to email
    mail_subject = 'Thankyou for your Order!'
    message = render_to_string('orders/order_received_email.html',{
        'user': request.user,  
        'order': order,
    })
    to_email = request.user.email
    send_email = EmailMessage(mail_subject, message, to=[to_email])
    send_email.send()

    # send order number amd transaction id back to sendData method via JSONresponse
    data = {
        'order_number' : order.order_number,
        'transID' : payment.payment_id,
        }
    return JsonResponse(data)


def place_order(request,total=0, quantity=0, cart_items=None):
    current_user = request.user

    # if cart count is less than or equal to 0, then redirect back to shop
    cart_items = CartItem.objects.filter(user=current_user)
    cart_count = cart_items.count()
    if cart_count <= 0:
        return redirect('store')


    grand_total = 0
    tax =0 
    for cart_item in cart_items:
        total += (cart_item.product.price * cart_item.quantity)
        quantity += cart_item.quantity
    tax = (16 * total)/100
    grand_total = total + tax 

    if request.method =='POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            # store all info ->order table db
            data  = Order()
            data.user = current_user
            data.first_name = form.cleaned_data['first_name']
            data.last_name = form.cleaned_data['last_name']
            data.phone = form.cleaned_data['phone']
            data.email = form.cleaned_data['email']
            data.region = form.cleaned_data['region']
            data.city = form.cleaned_data['city']
            data.street = form.cleaned_data['street']
            data.pickup = form.cleaned_data['pickup']
            data.order_note = form.cleaned_data['order_note']
            data.order_total = grand_total
            data.tax = tax
            data.ip = request.META.get('REMOTE_ADDR')
            data.save()


            # generate order number
            yr = int(date.today().strftime('%Y'))
            dt = int(date.today().strftime('%d'))
            mt = int(date.today().strftime('%m'))
            d = date(yr,mt,dt)
            current_date = d.strftime("%Y%m%d")
            order_number = current_date + str(data.id)
            data.order_number = order_number
            data.save()

            order = Order.objects.get(user=current_user, is_ordered = False, order_number = order_number)
            context = {
                'order': order,
                'cart_items' :cart_items,
                'total':total,
                'tax': tax,
                'grand_total':grand_total,
            }
            return render(request,'orders/payments.html', context)
        
        else:
            return redirect('checkout')

# we have a problem here
def order_complete(request):
    order_number = request.GET.get('order_number')
    transID = request.GET.get('payment_id')

    try: 
        order = Order.objects.get(order_number = order_number,is_ordered = True)
        ordered_products = OrderProduct.objects.filter(order_id = order.id)

        subtotal = 0
        for i in ordered_products:
            subtotal += i.product_price * i.quantity

        payment = Payment.objects.get(payment_id=transID)

        context = {
            'order': order,
            'ordered_products': ordered_products,
            'order_number': order.order_number,
            'transID': payment.payment_id,
            'payment':payment,
            'subtotal':subtotal,

        }
        return render(request, 'orders/order_complete.html', context)
    except (Payment.DoesNotExist, Order.DoesNotExist):
        return redirect('home')

    

