from django.urls import path

from .views import (
    ClickWebhookView, MyBalanceView, MyInvoicesView, MyTransactionsView,
    PaymeWebhookView,
)

urlpatterns = [
    # Authenticated user endpoints
    path("balance/", MyBalanceView.as_view(), name="payments_balance"),
    path("transactions/", MyTransactionsView.as_view(), name="payments_transactions"),
    path("invoices/", MyInvoicesView.as_view(), name="payments_invoices"),

    # Provider webhooks (public, provider-auth)
    path("click/webhook/", ClickWebhookView.as_view(), name="payments_click_webhook"),
    path("payme/webhook/", PaymeWebhookView.as_view(), name="payments_payme_webhook"),
]
