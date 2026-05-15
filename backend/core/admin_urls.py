"""
Admin Panel API URL rotaları.
"""

from django.urls import path
from .admin_api import (
    AdminPlatformStatsView,
    AdminChannelListView, AdminChannelApproveView, AdminChannelRejectView,
    AdminCampaignListView, AdminCampaignApproveView, AdminCampaignRejectView,
    AdminUserListView,
    AdminRevenueReportView,
    AdminCategoryListCreateView, AdminCategoryDetailView,
    AdminPayoutListView, AdminPayoutApproveView, AdminPayoutRejectView,
    AdminModerationQueueView, AdminModerationApproveView, AdminModerationRejectView,
    AdminFraudDashboardView, AdminSuspiciousChannelsView, AdminSuspiciousClicksView,
    AdminChannelTrustToggleView,
)

urlpatterns = [
    # Platform stats
    path("stats/", AdminPlatformStatsView.as_view(), name="admin_stats"),

    # Channel management
    path("channels/", AdminChannelListView.as_view(), name="admin_channels"),
    path("channels/<int:pk>/approve/", AdminChannelApproveView.as_view(), name="admin_channel_approve"),
    path("channels/<int:pk>/reject/", AdminChannelRejectView.as_view(), name="admin_channel_reject"),

    # Campaign management
    path("campaigns/", AdminCampaignListView.as_view(), name="admin_campaigns"),
    path("campaigns/<int:pk>/approve/", AdminCampaignApproveView.as_view(), name="admin_campaign_approve"),
    path("campaigns/<int:pk>/reject/", AdminCampaignRejectView.as_view(), name="admin_campaign_reject"),

    # User management
    path("users/", AdminUserListView.as_view(), name="admin_users"),

    # Revenue reports
    path("revenue/", AdminRevenueReportView.as_view(), name="admin_revenue"),

    # Category management
    path("categories/", AdminCategoryListCreateView.as_view(), name="admin_categories"),
    path("categories/<int:pk>/", AdminCategoryDetailView.as_view(), name="admin_category_detail"),

    # Payout management
    path("payouts/", AdminPayoutListView.as_view(), name="admin_payouts"),
    path("payouts/<int:pk>/approve/", AdminPayoutApproveView.as_view(), name="admin_payout_approve"),
    path("payouts/<int:pk>/reject/", AdminPayoutRejectView.as_view(), name="admin_payout_reject"),

    # Moderation queue (FAZ 2)
    path("moderation/queue/", AdminModerationQueueView.as_view(), name="admin_moderation_queue"),
    path("moderation/<int:pk>/approve/", AdminModerationApproveView.as_view(), name="admin_moderation_approve"),
    path("moderation/<int:pk>/reject/", AdminModerationRejectView.as_view(), name="admin_moderation_reject"),

    # Fraud / quality dashboard (FAZ 3)
    path("fraud/dashboard/", AdminFraudDashboardView.as_view(), name="admin_fraud_dashboard"),
    path("fraud/suspicious-channels/", AdminSuspiciousChannelsView.as_view(), name="admin_fraud_suspicious_channels"),
    path("fraud/suspicious-clicks/", AdminSuspiciousClicksView.as_view(), name="admin_fraud_suspicious_clicks"),
    path("channels/<int:pk>/trust/", AdminChannelTrustToggleView.as_view(), name="admin_channel_trust"),
]
