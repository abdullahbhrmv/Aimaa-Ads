"""
Atomik bakiye servis fonksiyonları (FAZ 4a).

Her fonksiyon:
- `transaction.atomic()` içinde çalışır
- `UserBalance` satırını `select_for_update()` ile kilitler
- Bir `Transaction` kaydı oluşturur (audit trail)
- `User.balance` denormalize mirror'ını senkronize eder

Idempotency:
- Provider-kaynaklı mutasyonlar (deposit, withdraw callback'leri)
  `(provider, provider_ref)` benzersizliğine dayanır; aynı ref ikinci kez
  gelirse mevcut Transaction döndürülür.
- İç mutasyonlar (freeze/spend/refund) iş mantığında zaten idempotent
  olmalı (ör. `_settle_placement`'ın `billed_at IS NULL` guard'ı).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from .models import Transaction, UserBalance

logger = logging.getLogger(__name__)
User = get_user_model()


class InsufficientBalanceError(Exception):
    """Yetersiz bakiye — kampanya approve veya payout'ta fırlatılır."""


class InsufficientFrozenError(Exception):
    """Frozen havuzu beklenenden az — veri tutarsızlığı işareti."""


def _sync_user_balance_mirror(user, balance: UserBalance) -> None:
    """`User.balance` legacy alanını güncel tut. Deprecated mirror."""
    # `update()` ile yazarak auto_now gibi alanları tetiklemeyiz.
    User.objects.filter(pk=user.pk).update(balance=balance.balance)


def _lock_balance(user) -> UserBalance:
    """Bakiye satırını lock'la (transaction içinde çağrılmalı).

    Yoksa oluşturur. `select_for_update` ile aynı anda iki worker'ın
    aynı kullanıcıya çift mutasyon yapmasını engeller.
    """
    UserBalance.objects.get_or_create(user=user)
    return UserBalance.objects.select_for_update().get(user=user)


# --- Dış para girişi / çıkışı ---------------------------------------------


def deposit(
    user,
    amount: Decimal,
    provider: str,
    provider_ref: str,
    description: str = "",
) -> Transaction:
    """Provider webhook'undan gelen bakiye yükleme — idempotent.

    Aynı `(provider, provider_ref)` ikinci kez çağrılırsa mevcut Transaction
    döner, bakiye tekrar artırılmaz.
    """
    if amount <= 0:
        raise ValueError(f"deposit amount must be positive (got {amount})")

    # Idempotency — kilit almadan önce mevcut tx'i ara. Race durumunda
    # aşağıdaki IntegrityError yakalanır.
    existing = Transaction.objects.filter(
        provider=provider, provider_ref=provider_ref
    ).first()
    if existing:
        logger.info(
            "Idempotent deposit — tx=%s provider=%s ref=%s",
            existing.id, provider, provider_ref,
        )
        return existing

    try:
        with transaction.atomic():
            balance = _lock_balance(user)
            balance.balance += amount
            balance.save(update_fields=["balance", "updated_at"])

            tx = Transaction.objects.create(
                user=user,
                type=Transaction.Type.DEPOSIT,
                status=Transaction.Status.COMPLETED,
                amount=amount,
                provider=provider,
                provider_ref=provider_ref,
                description=description,
                balance_after=balance.balance,
                frozen_after=balance.frozen_amount,
            )
            _sync_user_balance_mirror(user, balance)
            return tx
    except IntegrityError:
        # Race ile concurrent deposit — mevcut tx'i döndür.
        return Transaction.objects.get(provider=provider, provider_ref=provider_ref)


def withdraw_for_payout(payout) -> Transaction:
    """PayoutRequest onaylandığında publisher'dan para düş.

    Transaction status `PENDING` başlar — provider ödemeyi tamamlayınca
    (FAZ 4b) `COMPLETED`'a geçer. İptal halinde `CANCELLED` + refund.
    """
    user = payout.user
    with transaction.atomic():
        balance = _lock_balance(user)
        if balance.balance < payout.amount:
            raise InsufficientBalanceError(
                f"User {user.id} balance {balance.balance} < payout {payout.amount}"
            )

        balance.balance -= payout.amount
        balance.save(update_fields=["balance", "updated_at"])

        tx = Transaction.objects.create(
            user=user,
            type=Transaction.Type.WITHDRAW,
            status=Transaction.Status.PENDING,
            amount=payout.amount,
            provider=getattr(payout, "provider", "") or Transaction.Provider.MANUAL,
            provider_ref=getattr(payout, "provider_ref", "") or "",
            description=f"Payout #{payout.id}",
            related_payout=payout,
            balance_after=balance.balance,
            frozen_after=balance.frozen_amount,
        )
        _sync_user_balance_mirror(user, balance)
        return tx


# --- Kampanya bütçesi (freeze / spend / refund) --------------------------


def freeze_for_campaign(campaign) -> Transaction:
    """Kampanya onay anında budget'ı frozen havuzuna taşı."""
    if campaign.budget <= 0:
        raise ValueError("Campaign budget must be positive")

    advertiser = campaign.advertiser
    with transaction.atomic():
        balance = _lock_balance(advertiser)
        if balance.balance < campaign.budget:
            raise InsufficientBalanceError(
                f"Balance {balance.balance} < budget {campaign.budget}"
            )

        balance.balance -= campaign.budget
        balance.frozen_amount += campaign.budget
        balance.save(update_fields=["balance", "frozen_amount", "updated_at"])

        tx = Transaction.objects.create(
            user=advertiser,
            type=Transaction.Type.FREEZE,
            status=Transaction.Status.COMPLETED,
            amount=campaign.budget,
            provider=Transaction.Provider.INTERNAL,
            description=f"Kampanya #{campaign.id} için dondurulan bütçe",
            related_campaign=campaign,
            balance_after=balance.balance,
            frozen_after=balance.frozen_amount,
        )
        _sync_user_balance_mirror(advertiser, balance)
        return tx


def spend_from_frozen(placement, cost: Decimal) -> Transaction | None:
    """`_settle_placement`'tan çağrılır — frozen havuzundan ücret düş.

    Frozen yetersizse (veri tutarsızlığı — örn. kampanya approve olmadan
    placement sent oldu) `balance`'tan düşer ve log'lar. Negative balance
    mümkün değildir — yine yetersizse `InsufficientBalanceError`.
    """
    if cost <= 0:
        return None

    advertiser = placement.ad.campaign.advertiser
    with transaction.atomic():
        balance = _lock_balance(advertiser)

        if balance.frozen_amount >= cost:
            balance.frozen_amount -= cost
        else:
            # Edge: frozen yetersiz. balance'a düş, ikisi de yetmezse fırlat.
            leftover = cost - balance.frozen_amount
            balance.frozen_amount = Decimal("0")
            if balance.balance < leftover:
                raise InsufficientBalanceError(
                    f"Placement {placement.id} cost {cost} exceeds frozen+balance"
                )
            balance.balance -= leftover
            logger.warning(
                "Frozen underrun for placement %s — drew %s from balance",
                placement.id, leftover,
            )

        balance.save(update_fields=["balance", "frozen_amount", "updated_at"])

        tx = Transaction.objects.create(
            user=advertiser,
            type=Transaction.Type.AD_SPEND,
            status=Transaction.Status.COMPLETED,
            amount=cost,
            provider=Transaction.Provider.INTERNAL,
            description=f"Placement #{placement.id} harcaması",
            related_campaign=placement.ad.campaign,
            related_placement=placement,
            balance_after=balance.balance,
            frozen_after=balance.frozen_amount,
        )
        _sync_user_balance_mirror(advertiser, balance)
        return tx


def credit_publisher(placement, revenue: Decimal) -> Transaction | None:
    """Publisher'a reklam gelirini ekle — `_settle_placement`'tan çağrılır."""
    if revenue <= 0:
        return None

    publisher = placement.channel.owner
    with transaction.atomic():
        balance = _lock_balance(publisher)
        balance.balance += revenue
        balance.save(update_fields=["balance", "updated_at"])

        tx = Transaction.objects.create(
            user=publisher,
            type=Transaction.Type.AD_EARNING,
            status=Transaction.Status.COMPLETED,
            amount=revenue,
            provider=Transaction.Provider.INTERNAL,
            description=f"Placement #{placement.id} kazancı",
            related_placement=placement,
            balance_after=balance.balance,
            frozen_after=balance.frozen_amount,
        )
        _sync_user_balance_mirror(publisher, balance)
        return tx


def refund_unspent_campaign(campaign) -> Transaction | None:
    """Kampanya complete/pause/reject olduğunda kalan frozen'ı iade et.

    `budget - spent` kadar geri yazılır. Frozen havuzunda o kadar yoksa
    (edge case), sahip olunan miktar iade edilir.
    """
    remaining = (campaign.budget or Decimal("0")) - (campaign.spent or Decimal("0"))
    if remaining <= 0:
        return None

    advertiser = campaign.advertiser
    with transaction.atomic():
        balance = _lock_balance(advertiser)
        refundable = min(remaining, balance.frozen_amount)
        if refundable <= 0:
            return None

        balance.frozen_amount -= refundable
        balance.balance += refundable
        balance.save(update_fields=["balance", "frozen_amount", "updated_at"])

        tx = Transaction.objects.create(
            user=advertiser,
            type=Transaction.Type.REFUND,
            status=Transaction.Status.COMPLETED,
            amount=refundable,
            provider=Transaction.Provider.INTERNAL,
            description=f"Kampanya #{campaign.id} iadesi",
            related_campaign=campaign,
            balance_after=balance.balance,
            frozen_after=balance.frozen_amount,
        )
        _sync_user_balance_mirror(advertiser, balance)
        return tx


def adjust(
    user,
    amount: Decimal,
    description: str,
    direction: str = "credit",
) -> Transaction:
    """Admin manuel düzeltme — balance'a direkt ekler veya çıkarır."""
    if amount <= 0:
        raise ValueError("adjust amount must be positive")
    if direction not in {"credit", "debit"}:
        raise ValueError("direction must be 'credit' or 'debit'")

    with transaction.atomic():
        balance = _lock_balance(user)
        if direction == "credit":
            balance.balance += amount
        else:
            if balance.balance < amount:
                raise InsufficientBalanceError(
                    f"Cannot debit {amount} from balance {balance.balance}"
                )
            balance.balance -= amount
        balance.save(update_fields=["balance", "updated_at"])

        tx = Transaction.objects.create(
            user=user,
            type=Transaction.Type.ADJUSTMENT,
            status=Transaction.Status.COMPLETED,
            amount=amount,
            provider=Transaction.Provider.INTERNAL,
            description=description,
            balance_after=balance.balance,
            frozen_after=balance.frozen_amount,
        )
        _sync_user_balance_mirror(user, balance)
        return tx
