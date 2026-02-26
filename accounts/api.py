from django.conf import settings
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

import stripe

from .models import ApiToken, User

router = Router(tags=["billing"])
PRO_30_UNIT_AMOUNT = 300
PRO_30_CURRENCY = "usd"


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


class ApiTokenCreateIn(Schema):
    name: str = "Agent token"
    can_write: bool = True


class ApiTokenOut(Schema):
    id: int
    name: str
    can_write: bool
    token_prefix: str
    created_at: str
    last_used_at: str | None = None


class ApiTokenCreateOut(ApiTokenOut):
    token: str


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


def _api_token_to_dict(api_token: ApiToken):
    return {
        "id": api_token.id,
        "name": api_token.name,
        "can_write": api_token.can_write,
        "token_prefix": api_token.token_prefix,
        "created_at": api_token.created_at.isoformat(),
        "last_used_at": (
            api_token.last_used_at.isoformat() if api_token.last_used_at else None
        ),
    }


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

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
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
                    "price_data": {
                        "currency": PRO_30_CURRENCY,
                        "unit_amount": PRO_30_UNIT_AMOUNT,
                        "recurring": {"interval": "month"},
                        "product_data": {
                            "name": "FeatureRequest Pro",
                            "description": "Up to 30 projects",
                        },
                    },
                    "quantity": 1,
                },
            ],
            allow_promotion_codes=True,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"plan_id": payload.plan_id},
        )
    except stripe.error.AuthenticationError:
        raise HttpError(500, "Stripe authentication failed. Check STRIPE_SECRET_KEY.")
    except stripe.error.InvalidRequestError as exc:
        message = (exc.user_message or "").strip()
        if "No such price" in message:
            raise HttpError(400, "Stripe price is invalid. Check STRIPE_PRICE_ID_30.")
        if "No such customer" in message:
            raise HttpError(400, "Stripe customer is invalid. Please retry checkout.")
        raise HttpError(400, message or "Stripe rejected the checkout request.")
    except stripe.error.StripeError as exc:
        message = (exc.user_message or "").strip()
        raise HttpError(502, message or "Stripe could not create the checkout session.")

    return BillingCheckoutOut(plan_id=payload.plan_id, checkout_url=session.url)


@router.get("/auth/tokens", response=list[ApiTokenOut])
def list_api_tokens(request):
    user = _require_auth_user(request)
    tokens = ApiToken.objects.filter(user=user, revoked_at__isnull=True).order_by(
        "-created_at"
    )
    return [_api_token_to_dict(token) for token in tokens]


@router.post("/auth/tokens", response={201: ApiTokenCreateOut})
def create_api_token(request, payload: ApiTokenCreateIn):
    user = _require_auth_user(request)
    token, raw_token = ApiToken.issue(
        user=user,
        name=payload.name,
        can_write=payload.can_write,
    )
    response = _api_token_to_dict(token)
    response["token"] = raw_token
    return 201, response


@router.delete("/auth/tokens/{token_id}", response={204: None})
def revoke_api_token(request, token_id: int):
    user = _require_auth_user(request)
    token = get_object_or_404(
        ApiToken,
        id=token_id,
        user=user,
        revoked_at__isnull=True,
    )
    token.revoke()
    return 204, None
