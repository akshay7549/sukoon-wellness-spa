from django.urls import path
from . import business_views as views
from . import crm_views as crm
from . import reception_views as reception, loyalty_views as loyalty

urlpatterns = [
    path("day-board/", reception.day_board, name="reception_day_board"),
    path("waitlist/", reception.waitlist, name="reception_waitlist"),
    path("waitlist/new/", reception.waitlist_new, name="reception_waitlist_new"),
    path("waitlist/<int:entry_id>/", reception.waitlist_book, name="reception_waitlist_book"),
    path("rewards/", loyalty.rewards, name="loyalty_rewards"),
    path("rewards/policy/", loyalty.rewards_policy, name="loyalty_policy"),
    path("rewards/<int:contact_id>/", loyalty.wallet_detail, name="loyalty_wallet"),
    path("referrals/", loyalty.referrals, name="loyalty_referrals"),
    path("referrals/<int:referral_id>/", loyalty.referral_review, name="loyalty_referral_review"),
    path("pipeline/", crm.pipeline, name="crm_pipeline"),
    path("pipeline/new/", crm.lead_edit, name="crm_lead_new"),
    path("pipeline/booking-options/", crm.booking_options, name="crm_booking_options"),
    path("pipeline/<int:lead_id>/", crm.lead_edit, name="crm_lead_edit"),
    path("follow-ups/", crm.task_centre, name="crm_tasks"),
    path("follow-ups/new/", crm.task_edit, name="crm_task_new"),
    path("follow-ups/<int:task_id>/", crm.task_edit, name="crm_task_edit"),
    path("follow-ups/<int:task_id>/complete/", crm.task_complete, name="crm_task_complete"),
    path("customers/", crm.customers, name="crm_customers"),
    path("customers/<str:phone>/", crm.customer_detail, name="crm_customer_detail"),
    path("customers/<str:phone>/link-account/", crm.account_link, name="crm_account_link"),
    path("invoices/",views.invoice_list,name="invoice_list"),
    path("invoices/new/",views.invoice_edit,name="invoice_new"),
    path("invoices/<int:invoice_id>/edit/",views.invoice_edit,name="invoice_edit"),
    path("invoices/<int:invoice_id>/payments/",views.invoice_payment,name="invoice_payment"),
    path("calendar/",views.appointment_calendar,name="appointment_calendar"),
    path("collections/",views.collections,name="collections"),
    path("customer-history/",views.customer_history,name="customer_history"),
]
