#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.http import HttpResponse, QueryDict
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from paypal.standard.ipn.forms import PayPalIPNForm
from paypal.standard.ipn.models import PayPalIPN

from paypal.standard.ipn.mail import (send_payment_success_mail,
                                     )
from shoppingcart.models import (Order, PaidCourseRegistration,
                                OrderItem
                                )

@require_POST
@csrf_exempt
def ipn(request, item_check_callable=None):
    
    """
    The response from Paypal Payment
    
    {u'protection_eligibility': [u'Eligible'],
    u'last_name': [u'R'], 
    u'txn_id': [u'1B883441C5191701K'], 
    u'receiver_email': [u'username@example.com'],
    u'payment_status': [u'Completed'],
    u'payment_gross': [u'100.00'],
    u'tax': [u'0.00'], 
    u'residence_country': [u'US'], 
    u'invoice': [u'1461'],
    u'address_state': [u'CA'],
    u'payer_status': [u'verified'],
    u'txn_type': [u'web_accept'],
    u'address_country': [u'United States'],
    u'handling_amount': [u'0.00'], 
    u'payment_date': [u'01:23:03 Jul 04, 2014 PDT'], 
    u'first_name': [u'XXXXXXXXX'], u'item_name': [u''],
    u'address_street': [u'1 Main St'], 
    u'charset': [u'windows-1252'], 
    u'custom': [u''],
    u'notify_version': [u'3.8'],
    u'address_name': [u'XXXXXXXXX'], 
    u'test_ipn': [u'1'],
    u'item_number': [u''], 
    u'receiver_id': [u'7EEGW6KXU7H3G'],
    u'transaction_subject': [u''], 
    u'business': [u'username@example.com'], 
    u'payer_id': [u'YQG53MRMSMVT8'],
    u'verify_sign': [u'AMIsJErLWFh1ByQ-Pn.oseCWp0SBAOA1.0fCwFL.qfIIq6GQoS36n5i8'],
    u'address_zip': [u'95131'], 
    u'payment_fee': [u'3.20'], 
    u'address_country_code': [u'US'],
    u'address_city': [u'San Jose'],
    u'address_status': [u'confirmed'], 
    u'mc_fee': [u'3.20'],
    u'mc_currency': [u'USD'],
    u'shipping': [u'0.00'], 
    u'payer_email': [u'user1@example.com'],
    u'payment_type': [u'instant'],
    u'mc_gross': [u'100.00'], 
    u'ipn_track_id': [u'59b0e84327236'],
    u'quantity': [u'1']
    }

    """
    
    """
    PayPal IPN endpoint (notify_url).
    Used by both PayPal Payments Pro and Payments Standard to confirm transactions.
    http://tinyurl.com/d9vu9d
    
    PayPal IPN Simulator:
    https://developer.paypal.com/cgi-bin/devscr?cmd=_ipn-link-session
    """
    #TODO: Clean up code so that we don't need to set None here and have a lot
    #      of if checks just to determine if flag is set.
    flag = None
    ipn_obj = None

    # Clean up the data as PayPal sends some weird values such as "N/A"
    # Also, need to cope with custom encoding, which is stored in the body (!).
    # Assuming the tolerate parsing of QueryDict and an ASCII-like encoding,
    # such as windows-1252, latin1 or UTF8, the following will work:

    encoding = request.POST.get('charset', None)

    if encoding is None:
        flag = "Invalid form - no charset passed, can't decode"
        data = None
    else:
        try:
            data = QueryDict(request.body, encoding=encoding).copy()
        except LookupError:
            data = None
            flag = "Invalid form - invalid charset"

    if data is not None:
        date_fields = ('time_created', 'payment_date', 'next_payment_date',
                       'subscr_date', 'subscr_effective')
        for date_field in date_fields:
            if data.get(date_field) == 'N/A':
                del data[date_field]

        form = PayPalIPNForm(data)
        if form.is_valid():
            try:
                #When commit = False, object is returned without saving to DB.
                ipn_obj = form.save(commit=False)
            except Exception as e:
                flag = "Exception while processing. (%s)" % e
        else:
            flag = "Invalid form. (%s)" % form.errors

    if ipn_obj is None:
        ipn_obj = PayPalIPN()

    #Set query params and sender's IP address
    ipn_obj.initialize(request)

    if flag is not None:
        #We save errors in the flag field
        ipn_obj.set_flag(flag)
    else:
        # Secrets should only be used over SSL.
        if request.is_secure() and 'secret' in request.GET:
            ipn_obj.verify_secret(form, request.GET['secret'])
        else:
            ipn_obj.verify(item_check_callable)

    ipn_obj.save()
    
          
    # Send Notification mail to logged in user
    try:
        send_payment_success_mail(request, ipn_obj=ipn_obj)
    except Exception as e:
        print str(e)
        
    return HttpResponse("OKAY")
