from django.conf import settings
from ninja import Router, Schema
from ninja.errors import HttpError

import stripe

from .models import User

router = Router(tags=["billing"])


class BillingPlanOut(Schema):
    id: str
    name: str
    subtitle: str
    price_label: str
    project_limit: int


class BillingCheckoutIn(Schema):
    plan_id: str


class BillingCheckoutOut(Schema):
    plan_id: str
    checkout_url: str | None = None


def _require_auth_user(request):
    user = request.user
    if not user.is_authenticated:
        raise HttpError(401, "Authentication required.")
    return user


def _build_checkout_urls(request):
    base = request.build_absolute_uri("/")
    if base.endswith("/"):
        return f"{base}?checkout=success", f"{base}?checkout=cancel"
    return f"{base}/?checkout=success", f"{base}/?checkout=cancel"


def _plan_definitions():
    return [
        {
            "id": "free",
            "name": "Free",
            "subtitle": "Free for 1 project",
            "price_label": "$0/mo",
            "project_limit": 1,
        },
        {
            "id": "pro_30",
            "name": "Pro",
            "subtitle": "$3/mo for up to 30 projects",
            "price_label": "$3/mo",
            "project_limit": 30,
        },
    ]


def _is_valid_plan(plan_id: str):
    return plan_id in {"free", "pro_30"}


@router.get("/billing/plans", response=list[BillingPlanOut])
def list_billing_plans(request):
    return _plan_definitions()


@router.post("/billing/checkout", response=BillingCheckoutOut)
def create_checkout_session(request, payload: BillingCheckoutIn):
    user = _require_auth_user(request)

    if not _is_valid_plan(payload.plan_id):
        raise HttpError(400, "Invalid plan selected.")

    if payload.plan_id != "pro_30":
        return BillingCheckoutOut(plan_id="free", checkout_url=None)

    if not settings.STRIPE_SECRET_KEY:
        raise HttpError(500, "Stripe is not configured.")

    if not settings.STRIPE_PRICE_ID_30:
        raise HttpError(400, "Stripe price is missing for the paid plan.")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    customer_id = user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            name=user.handle,
            metadata={"user_id": str(user.id)},
        )
        customer_id = customer.id
        user.stripe_customer_id = customer_id
        user.save(update_fields=["stripe_customer_id"])

    success_url, cancel_url = _build_checkout_urls(request)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        client_reference_id=str(user.id),
        mode="subscription",
        line_items=[
            {
                "price": settings.STRIPE_PRICE_ID_30,
                "quantity": 1,
            },
        ],
        allow_promotion_codes=True,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"plan_id": payload.plan_id},
    )

    return BillingCheckoutOut(plan_id=payload.plan_id, checkout_url=session.url)
