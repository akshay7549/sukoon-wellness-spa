from django.urls import path
from . import business_views as views

urlpatterns = [
    path("invoices/",views.invoice_list,name="invoice_list"),
    path("invoices/new/",views.invoice_edit,name="invoice_new"),
    path("invoices/<int:invoice_id>/edit/",views.invoice_edit,name="invoice_edit"),
    path("invoices/<int:invoice_id>/payments/",views.invoice_payment,name="invoice_payment"),
    path("calendar/",views.appointment_calendar,name="appointment_calendar"),
    path("collections/",views.collections,name="collections"),
    path("customer-history/",views.customer_history,name="customer_history"),
]
