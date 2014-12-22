import logging
import datetime
import pytz
from django.conf import settings
from django.contrib.auth.models import Group
from django.http import (HttpResponse, HttpResponseRedirect, HttpResponseNotFound,
    HttpResponseBadRequest, HttpResponseForbidden, Http404)
from django.utils.translation import ugettext as _
from django.views.decorators.http import require_POST
from django.core.urlresolvers import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.sites.models import Site
from edxmako.shortcuts import render_to_response
from opaque_keys.edx.locations import SlashSeparatedCourseKey
from shoppingcart.reports import RefundReport, ItemizedPurchaseReport, UniversityRevenueShareReport, CertificateStatusReport
from student.models import CourseEnrollment
from .exceptions import ItemAlreadyInCartException, AlreadyEnrolledInCourseException, CourseDoesNotExistException, ReportTypeDoesNotExistException
from .models import Order, PaidCourseRegistration, OrderItem
from .processors import process_postpay_callback, render_purchase_form_html
from django.template import RequestContext
from edxmako.shortcuts import render_to_string
from collections import OrderedDict, defaultdict

from django.contrib.sites.models import get_current_site
from django.contrib.auth.models import User

from paypal.standard.ipn.models import PayPalIPN
from paypal.standard.ipn.mail import send_payment_cancel_mail


log = logging.getLogger("shoppingcart")

EVENT_NAME_USER_UPGRADED = 'edx.course.enrollment.upgrade.succeeded'

REPORT_TYPES = [
    ("refund_report", RefundReport),
    ("itemized_purchase_report", ItemizedPurchaseReport),
    ("university_revenue_share", UniversityRevenueShareReport),
    ("certificate_status", CertificateStatusReport),
]

# Take a Current Date
now = datetime.datetime.now()


def initialize_report(report_type, start_date, end_date, start_letter=None, end_letter=None):
    """
    Creates the appropriate type of Report object based on the string report_type.
    """
    for item in REPORT_TYPES:
        if report_type in item:
            return item[1](start_date, end_date, start_letter, end_letter)
    raise ReportTypeDoesNotExistException


@require_POST
def add_course_to_cart(request, course_id):
    """
    Adds course specified by course_id to the cart.  The model function add_to_order does all the
    heavy lifting (logging, error checking, etc)
    """

    assert isinstance(course_id, basestring)
    if not request.user.is_authenticated():
        log.info("Anon user trying to add course {} to cart".format(course_id))
        return HttpResponseForbidden(_('You must be logged-in to add to a shopping cart'))
    cart = Order.get_cart_for_user(request.user)
    course_key = SlashSeparatedCourseKey.from_deprecated_string(course_id)
    # All logging from here handled by the model
    try:
        PaidCourseRegistration.add_to_order(cart, course_key)
    except CourseDoesNotExistException:
        return HttpResponseNotFound(_('The course you requested does not exist.'))
    except ItemAlreadyInCartException:
        return HttpResponseBadRequest(_('The course {0} is already in your cart.'.format(course_id)))
    except AlreadyEnrolledInCourseException:
        return HttpResponseBadRequest(_('You are already registered in course {0}.'.format(course_id)))
    return HttpResponse(_("Course added to cart."))


################ Payment Paypal IPN Standard Integration ######################
def get_signed_purchase_params(request, cart):
    
    """
        This functions will return the Parameteres for Paypal IPN Standard Payment Form    
    """
    
    total_cost = cart.total_cost
    amount = "{0:0.2f}".format(total_cost)
    cart_items = cart.orderitem_set.all()
    
    params = OrderedDict()
    
    # Newly Added Fields
    params['amount'] = amount
    params['business'] = settings.PAYPAL_RECEIVER_EMAIL
    params['currency_code'] = cart.currency.upper()
    params['quantity'] = len(cart_items)

    #params['invoice'] = "{0:d}".format(cart.id)    
    unique_val = "{0:d}-{1}".format(cart.id, now)
    unique_val = "{0:d}".format(cart.id)
    params['invoice'] = unique_val 

    # Get Current Site
    current_site = Site.objects.get_current()
    
    params['notify_url']  = "http://{0}".format(current_site.domain)+ reverse('paypal-ipn')
    #params['notify_url']  = "http://{0}/shoppingcart/payment/paypal/"
    params['return'] =  "http://{0}/shoppingcart/receipt/{1:d}/".format(current_site.domain, cart.id)
    params['cancel_return'] = "http://{0}/shoppingcart/payment/cancel/".format(current_site.domain)
        
    # URL set for Paypal Payments
    # To Do Comment
    #params['notify_url']  = "http://54.183.17.35" + reverse('paypal-ipn')
    #params['return'] =  "http://54.183.17.35/shoppingcart/receipt/{0:d}/".format(cart.id)
    #params['cancel_return'] = "http://54.183.17.35/shoppingcart/payment/cancel/"
    
    # Billing Address from cart Details
    params['address_city'] = cart.bill_to_city 
    params['last_name'] = cart.bill_to_last
    params['first_name'] = cart.bill_to_first
    params['address_country'] = cart.bill_to_country
    params['address_state'] = cart.bill_to_state
    params['address_street'] = cart.bill_to_street1 
    params['address_zip'] = cart.bill_to_postalcode
         
    # For Payment Button
    params['cmd'] = "_xclick"
    params['custom'] = request.user.username
    
    return params


def render_paypal_form_html(request, cart):
    """
    Renders the HTML of the hidden POST form that must be used to initiate a purchase with Paypal IPN Standard
    """
    if settings.FEATURES['PAYPAL_TEST']:
        action_url = settings.SANDBOX_PAYPAL_ENDPOINT
    else:
        action_url = settings.LIVE_PAYPAL_ENDPOINT
        
    return render_to_string('shoppingcart/payment.html', {
        'action': action_url,
        'params': get_signed_purchase_params(request, cart),
    })


@csrf_exempt
def payment_cancel(request):
    
    """
    Success page after payment completion.
    Clear the cart items.
    """
    # Send Notifictaion Mail to User
    send_payment_cancel_mail(request)
    
    # Update the Cart Status as "Purchased"
    cart = Order.get_cart_for_user(request.user)

    return render_to_response("shoppingcart/order_cancel.html",
                              {'cart': cart,
                              }
                             )

################ Payment Paypal Integration ######################

@login_required
def show_cart(request):
    cart = Order.get_cart_for_user(request.user)
    total_cost = cart.total_cost
    cart_items = cart.orderitem_set.all()
    
    # Commented the older one
    #form_html = render_purchase_form_html(cart)
    
    form_html = render_paypal_form_html(request, cart)
    return render_to_response("shoppingcart/list.html",
                              {'shoppingcart_items': cart_items,
                               'amount': total_cost,
                               'form_html': form_html,
                               })

@login_required
def clear_cart(request):
    cart = Order.get_cart_for_user(request.user)
    cart.clear()
    return HttpResponse('Cleared')


@login_required
def remove_item(request):
    item_id = request.REQUEST.get('id', '-1')
    try:
        item = OrderItem.objects.get(id=item_id, status='cart')
        if item.user == request.user:
            item.delete()
    except OrderItem.DoesNotExist:
        log.exception('Cannot remove cart OrderItem id={0}. DoesNotExist or item is already purchased'.format(item_id))
    return HttpResponse('OK')



@require_POST
def postpay_callback(request):
    """
    Receives the POST-back from processor.
    Mainly this calls the processor-specific code to check if the payment was accepted, and to record the order
    if it was, and to generate an error page.
    If successful this function should have the side effect of changing the "cart" into a full "order" in the DB.
    The cart can then render a success page which links to receipt pages.
    If unsuccessful the order will be left untouched and HTML messages giving more detailed error info will be
    returned.
    """
    params = request.POST.dict()
    result = process_postpay_callback(params)
    if result['success']:
        return HttpResponseRedirect(reverse('shoppingcart.views.show_receipt', args=[result['order'].id]))
    else:
        return render_to_response('shoppingcart/error.html', {'order': result['order'],
                                                              'error_html': result['error_html']})

@login_required
@csrf_exempt
def show_receipt(request, ordernum):
    """
    Displays a receipt for a particular order.
    404 if order is not yet purchased or request.user != order.user
    """

    user = User.objects.get(username=request.user.username)
    cart = Order.get_cart_for_user(user)

    try:
      ipn_obj = PayPalIPN.objects.get(invoice = ordernum)
      if ipn_obj.payment_status == "Completed":
          cart.status = 'purchased'
          cart.save()
    except PayPalIPN.DoesNotExist:      
      raise Http404('Notification not found!')

    cart_items = cart.orderitem_set.all()

    try:
        # Call the Registered Function for the Paid Course
        for cart_item in cart_items:
            PaidCourseRegistration.objects.get(id = cart_item.id).purchased_callback()
    except Exception as e:
        print str(e), 'REEEEEEEEEEEGGGGGGGGGGGGGTTTTTTTTTTTEEEEEEEEEEEDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD'

    try:
        order = Order.objects.get(id=ordernum)
    except Order.DoesNotExist:
        raise Http404('Order not found!')

    #if order.user != request.user or order.status != 'purchased':
    #    raise Http404('Order not found!')

    order_items = OrderItem.objects.filter(order=order).select_subclasses()
    any_refunds = any(i.status == "refunded" for i in order_items)
    receipt_template = 'shoppingcart/receipt.html'
    __, instructions = order.generate_receipt_instructions()
    # we want to have the ability to override the default receipt page when
    # there is only one item in the order
    context = {
        'order': order,
        'order_items': order_items,
        'any_refunds': any_refunds,
        'instructions': instructions,
    }

    if order_items.count() == 1:
        receipt_template = order_items[0].single_item_receipt_template
        context.update(order_items[0].single_item_receipt_context)

    # Only orders where order_items.count() == 1 might be attempting to upgrade
    attempting_upgrade = request.session.get('attempting_upgrade', False)
    if attempting_upgrade:
        course_enrollment = CourseEnrollment.get_or_create_enrollment(request.user, order_items[0].course_id)
        course_enrollment.emit_event(EVENT_NAME_USER_UPGRADED)
        request.session['attempting_upgrade'] = False

    return render_to_response(receipt_template, context)


def _can_download_report(user):
    """
    Tests if the user can download the payments report, based on membership in a group whose name is determined
     in settings.  If the group does not exist, denies all access
    """
    try:
        access_group = Group.objects.get(name=settings.PAYMENT_REPORT_GENERATOR_GROUP)
    except Group.DoesNotExist:
        return False
    return access_group in user.groups.all()


def _get_date_from_str(date_input):
    """
    Gets date from the date input string.  Lets the ValueError raised by invalid strings be processed by the caller
    """
    return datetime.datetime.strptime(date_input.strip(), "%Y-%m-%d").replace(tzinfo=pytz.UTC)


def _render_report_form(start_str, end_str, start_letter, end_letter, report_type, total_count_error=False, date_fmt_error=False):
    """
    Helper function that renders the purchase form.  Reduces repetition
    """
    context = {
        'total_count_error': total_count_error,
        'date_fmt_error': date_fmt_error,
        'start_date': start_str,
        'end_date': end_str,
        'start_letter': start_letter,
        'end_letter': end_letter,
        'requested_report': report_type,
    }
    return render_to_response('shoppingcart/download_report.html', context)


@login_required
def csv_report(request):
    """
    Downloads csv reporting of orderitems
    """
    if not _can_download_report(request.user):
        return HttpResponseForbidden(_('You do not have permission to view this page.'))

    if request.method == 'POST':
        start_date = request.POST.get('start_date', '')
        end_date = request.POST.get('end_date', '')
        start_letter = request.POST.get('start_letter', '')
        end_letter = request.POST.get('end_letter', '')
        report_type = request.POST.get('requested_report', '')
        try:
            start_date = _get_date_from_str(start_date) + datetime.timedelta(days=0)
            end_date = _get_date_from_str(end_date) + datetime.timedelta(days=1)
        except ValueError:
            # Error case: there was a badly formatted user-input date string
            return _render_report_form(start_date, end_date, start_letter, end_letter, report_type, date_fmt_error=True)

        report = initialize_report(report_type, start_date, end_date, start_letter, end_letter)
        items = report.rows()

        response = HttpResponse(mimetype='text/csv')
        filename = "purchases_report_{}.csv".format(datetime.datetime.now(pytz.UTC).strftime("%Y-%m-%d-%H-%M-%S"))
        response['Content-Disposition'] = 'attachment; filename="{}"'.format(filename)
        report.write_csv(response)
        return response

    elif request.method == 'GET':
        end_date = datetime.datetime.now(pytz.UTC)
        start_date = end_date - datetime.timedelta(days=30)
        start_letter = ""
        end_letter = ""
        return _render_report_form(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), start_letter, end_letter, report_type="")

    else:
        return HttpResponseBadRequest("HTTP Method Not Supported")
    

