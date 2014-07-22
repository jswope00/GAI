"""
Allows django admin site to add PaidCourseRegistrationAnnotations
"""
from ratelimitbackend import admin
from shoppingcart.models import PaidCourseRegistrationAnnotation, PaidCourseRegistration

admin.site.register(PaidCourseRegistration)
admin.site.register(PaidCourseRegistrationAnnotation)
