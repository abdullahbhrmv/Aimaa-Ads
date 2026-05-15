"""
Payments API serializer'ları (FAZ 4a).
"""

from rest_framework import serializers

from .models import Invoice, Transaction, UserBalance


class UserBalanceSerializer(serializers.ModelSerializer):
    total_assets = serializers.ReadOnlyField()

    class Meta:
        model = UserBalance
        fields = [
            "balance", "frozen_amount", "total_assets",
            "currency", "updated_at",
        ]
        read_only_fields = fields


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "id", "type", "status", "amount",
            "balance_after", "frozen_after",
            "provider", "provider_ref", "description",
            "related_campaign", "related_placement", "related_payout",
            "created_at",
        ]
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            "id", "invoice_number",
            "net_amount", "kdv_amount", "gross_amount", "currency",
            "status", "provider", "provider_ref",
            "issued_at", "created_at",
        ]
        read_only_fields = fields
