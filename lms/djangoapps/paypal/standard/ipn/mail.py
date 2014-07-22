"""
    This file includes various mail functionality for Success and Cancel.
    
    1. Notification Mail Body Content is getting from payment_success_mail.html file.
        
    2. Cancel Mail content is getting from payment_failure_mail.html file.
    
"""

from django.contrib.sites.models import Site
from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template_from_string
from django.template.loader import get_template

from django.template import Context
from django.contrib.auth.models import User
from django.conf import settings
from datetime import datetime

from shoppingcart.models import (Order, PaidCourseRegistration,
                                OrderItem
                                )

try:
    contactus_to_mail = settings.CONTACT_EMAIL
except:
    contactus_to_mail = 'info@edx.com'


def send_payment_success_mail(request, *args, **kwargs):
    
    """
        Send Notification Mail to User after payment completed.
    """
    
    ipn_obj = kwargs.get("ipn_obj")
    
    user = User.objects.get(username=ipn_obj.custom)
    cart = Order.get_cart_for_user(user)
     
    subject = 'Your payment has been completed successfully.'
    plaintext = get_template('shoppingcart/payment_success_mail.html')
    
    total_cost = cart.total_cost
    cart_items = cart.orderitem_set.all()
    
    data = Context({
        "username": user.username,
        "transaction_id": ipn_obj.txn_id,
        "site_name": Site.objects.get_current(),
        "paid": ipn_obj.mc_gross,
        "amount": ipn_obj.amount,
        "ipn_obj": ipn_obj,
        "cart": cart,
        "cart_items":cart_items,
        "contact_mail": settings.CONTACT_EMAIL
    })

    subject, from_email, to = subject, settings.DEFAULT_FROM_EMAIL, user.email

    text_content = plaintext.render(data)

    try:
        msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
        msg.content_subtype = "html"  # Main content is now text/html
        msg.send()
    except Exception as e :
        print str(e)
        
    if ipn_obj.payment_status == "Completed":
        # Update the Purchased time and Status as Purchased
        cart.purchase(
            first=ipn_obj.first_name,
            last=ipn_obj.last_name,
            street1=ipn_obj.address_street,
            street2=ipn_obj.address_street,
            city=ipn_obj.address_city,
            state=ipn_obj.address_state,
            country=ipn_obj.address_country,
            postalcode=ipn_obj.address_zip
        )
        
        try:
            # Call the Registered Function or the Paid Course
            for cart_item in cart_items:
                PaidCourseRegistration.objects.get(id = cart_item.id).purchased_callback()
        except Exception as e:
            print str(e)
          
    
def send_payment_cancel_mail(request, *args, **kwargs):
    
    """
        Send Notification Mail to user after payment cancelled.
    """

    subject = 'Your payment has been cancelled'
    plaintext = get_template('shoppingcart/payment_cancel_mail.html')

    data = Context({
        "username": request.user.username,
        "site_name": Site.objects.get_current(),
    })

    subject, from_email, to = subject, settings.DEFAULT_FROM_EMAIL, request.user.email

    text_content = plaintext.render(data)

    msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
    msg.content_subtype = "html"  # Main content is now text/html
    msg.send()
    
    
    