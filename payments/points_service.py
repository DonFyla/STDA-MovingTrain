from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from .models import UserPoints, PointTransaction


def get_or_create_user_points(user):
    points, created = UserPoints.objects.get_or_create(
        user=user,
        defaults={
            "balance": 0,
            "total_purchased": 0,
            "total_used": 0,
        },
    )
    return points


def get_balance(user):
    points = get_or_create_user_points(user)
    return points.balance


def has_sufficient_points(user, amount):
    return get_balance(user) >= amount


@transaction.atomic
def add_points(user, amount, description="", payment_reference="", status="completed", transaction_type="purchase"):
    if amount <= 0:
        raise ValueError("Amount must be positive")

    points = get_or_create_user_points(user)
    points = UserPoints.objects.select_for_update().get(pk=points.pk)
    points.balance += amount
    if transaction_type in ("purchase", "bonus"):
        points.total_purchased += amount
    points.expires_at = timezone.now() + timedelta(days=365)
    points.save()

    PointTransaction.objects.create(
        user=user,
        type=transaction_type,
        amount=amount,
        balance_after=points.balance,
        payment_reference=payment_reference,
        description=description,
        status=status,
        expires_at=points.expires_at,
    )
    return points


@transaction.atomic
def complete_pending_transaction(tx):
    """Complete a pending PointTransaction by crediting the user's balance.

    This updates the existing pending transaction in place instead of creating
    a duplicate completed transaction.
    """
    if tx.status != "pending":
        raise ValueError(f"Transaction must be pending, got {tx.status}")
    if tx.type not in ("purchase", "bonus"):
        raise ValueError(f"Cannot complete transaction of type {tx.type}")
    if tx.amount <= 0:
        raise ValueError("Amount must be positive")

    points = get_or_create_user_points(tx.user)
    points = UserPoints.objects.select_for_update().get(pk=points.pk)
    points.balance += tx.amount
    points.total_purchased += tx.amount
    points.expires_at = timezone.now() + timedelta(days=365)
    points.save()

    tx.status = "completed"
    tx.balance_after = points.balance
    tx.expires_at = points.expires_at
    tx.save(update_fields=["status", "balance_after", "expires_at"])

    return points


@transaction.atomic
def use_points(user, amount, flexible_booking=None, description=""):
    if amount <= 0:
        raise ValueError("Amount must be positive")

    points = get_or_create_user_points(user)
    points = UserPoints.objects.select_for_update().get(pk=points.pk)
    if points.balance < amount:
        raise ValueError(f"Insufficient points. Balance: {points.balance}, needed: {amount}")

    points.balance -= amount
    points.total_used += amount
    points.save()

    PointTransaction.objects.create(
        user=user,
        type="usage",
        amount=-amount,
        balance_after=points.balance,
        booking=flexible_booking,
        description=description,
    )
    return points


@transaction.atomic
def refund_points(user, amount, flexible_booking=None, description=""):
    if amount <= 0:
        raise ValueError("Amount must be positive")

    points = get_or_create_user_points(user)
    points = UserPoints.objects.select_for_update().get(pk=points.pk)
    points.balance += amount
    points.save()

    PointTransaction.objects.create(
        user=user,
        type="refund",
        amount=amount,
        balance_after=points.balance,
        booking=flexible_booking,
        description=description,
    )
    return points
