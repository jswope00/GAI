"""
Paypal Payment Fake File:
It contains Test function for paypal standard IPN payment
"""

from django.core.urlresolvers import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from edxmako.shortcuts import render_to_response

from django.contrib.sites.models import get_current_site
from django.conf import settings

from paypal.standard.forms import PayPalPaymentsForm


def paypal_test(request):
    
    """
    Paypal Standard IPN Test Function
    Referrer URL: https://github.com/spookylukey/django-paypal
    """
    
    # What you want the button to do.
    paypal_dict = {
        "business": settings.PAYPAL_RECEIVER_EMAIL,
        "amount": "1000.00",
        "item_name": "name of the item",
        "invoice": "unique-invoice-id",
        "notify_url": "http://edx-lms.opentestdrive.com/shoppingcart/payment/notify/",
        "return_url": "http://edx-lms.opentestdrive.com/shoppingcart/payment/success/",
        "cancel_return": "http://edx-lms.opentestdrive.com/shoppingcart/payment/cancel/"

    }

    # Create the instance.
    form = PayPalPaymentsForm(initial=paypal_dict)
    context = {"form": form}
    return render_to_response("shoppingcart/paypal_test.html", context)

