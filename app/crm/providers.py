"""CRM integrations.

Every provider implements the same small interface so the journey never cares where data lives:

* `LocalCRM`   - the app's own database (Customer / Lead tables). Default; also what the admin API exposes.
* `HubSpotCRM` - HubSpot CRM v3 API (contacts). Customers are looked up live; leads become contacts.
* `WebhookCRM` - POSTs signed JSON events to any URL (Zapier, Make, n8n, a client's backend...).

To add Salesforce / Zoho / Pipedrive, implement `CRMProvider` and register it in `build_crm()`.
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Customer

log = logging.getLogger(__name__)


@dataclass
class CustomerRecord:
    ref: str  # provider-specific id
    email: str
    name: str
    plan: str = "-"
    status: str = "-"


@dataclass
class LeadData:
    name: str
    email: str
    phone: str | None = None
    interest: str | None = None


class CRMProvider(Protocol):
    def find_customer_by_email(self, db: Session, email: str) -> CustomerRecord | None: ...

    def get_customer(self, db: Session, ref: str) -> CustomerRecord | None: ...

    def create_lead(self, db: Session, lead: LeadData) -> str | None:
        """Push a lead. Returns the provider's reference id, or None if not synced."""
        ...

    def log_event(self, event: str, data: dict) -> None: ...


def _from_row(row: Customer) -> CustomerRecord:
    return CustomerRecord(ref=str(row.id), email=row.email, name=row.name, plan=row.plan, status=row.status)


class LocalCRM:
    def find_customer_by_email(self, db: Session, email: str) -> CustomerRecord | None:
        row = db.scalar(select(Customer).where(func.lower(Customer.email) == email.lower()))
        return _from_row(row) if row else None

    def get_customer(self, db: Session, ref: str) -> CustomerRecord | None:
        row = db.get(Customer, int(ref)) if ref.isdigit() else None
        return _from_row(row) if row else None

    def create_lead(self, db: Session, lead: LeadData) -> str | None:
        return None  # the Lead row saved by the caller *is* the local CRM record

    def log_event(self, event: str, data: dict) -> None:
        log.info("CRM event %s: %s", event, data)


class HubSpotCRM:
    BASE = "https://api.hubapi.com/crm/v3/objects/contacts"
    PROPS = ["email", "firstname", "lastname", "hs_lead_status", "lifecyclestage"]

    def __init__(self, access_token: str, http: httpx.Client | None = None):
        if not access_token:
            raise ValueError("CRM_PROVIDER=hubspot requires HUBSPOT_ACCESS_TOKEN")
        self.http = http or httpx.Client(timeout=15.0, headers={"Authorization": f"Bearer {access_token}"})

    def _record(self, obj: dict) -> CustomerRecord:
        p = obj.get("properties", {})
        name = " ".join(filter(None, [p.get("firstname"), p.get("lastname")])) or p.get("email", "")
        return CustomerRecord(
            ref=obj["id"], email=p.get("email", ""), name=name,
            plan=p.get("lifecyclestage") or "-", status=p.get("hs_lead_status") or "-",
        )

    def _search(self, email: str) -> dict | None:
        body = {
            "filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}],
            "properties": self.PROPS,
            "limit": 1,
        }
        resp = self.http.post(f"{self.BASE}/search", json=body)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None

    def find_customer_by_email(self, db: Session, email: str) -> CustomerRecord | None:
        try:
            obj = self._search(email)
        except httpx.HTTPError as exc:
            log.error("HubSpot search failed: %s", exc)
            return None
        return self._record(obj) if obj else None

    def get_customer(self, db: Session, ref: str) -> CustomerRecord | None:
        try:
            resp = self.http.get(f"{self.BASE}/{ref}", params={"properties": ",".join(self.PROPS)})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.error("HubSpot get failed: %s", exc)
            return None
        return self._record(resp.json())

    def create_lead(self, db: Session, lead: LeadData) -> str | None:
        first, _, last = lead.name.partition(" ")
        props = {"email": lead.email, "firstname": first, "lastname": last, "hs_lead_status": "NEW"}
        if lead.phone:
            props["phone"] = lead.phone
        if lead.interest:
            props["message"] = lead.interest
        try:
            existing = self._search(lead.email)
            if existing:
                resp = self.http.patch(f"{self.BASE}/{existing['id']}", json={"properties": props})
            else:
                resp = self.http.post(self.BASE, json={"properties": {**props, "lifecyclestage": "lead"}})
            resp.raise_for_status()
            return resp.json().get("id")
        except httpx.HTTPError as exc:
            log.error("HubSpot lead sync failed: %s", exc)
            return None

    def log_event(self, event: str, data: dict) -> None:
        log.info("CRM event %s: %s", event, data)


class WebhookCRM(LocalCRM):
    """Customers come from the local DB; leads and events are forwarded to a webhook."""

    def __init__(self, url: str, secret: str = "", http: httpx.Client | None = None):
        if not url:
            raise ValueError("CRM_PROVIDER=webhook requires CRM_WEBHOOK_URL")
        self.url, self.secret = url, secret
        self.http = http or httpx.Client(timeout=10.0)

    def _post(self, event: str, data: dict) -> bool:
        body = json.dumps({"event": event, "data": data}, default=str).encode()
        headers = {"Content-Type": "application/json"}
        if self.secret:
            headers["X-Signature-256"] = "sha256=" + hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        try:
            self.http.post(self.url, content=body, headers=headers).raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.error("CRM webhook %s failed: %s", event, exc)
            return False

    def create_lead(self, db: Session, lead: LeadData) -> str | None:
        return "webhook" if self._post("lead.created", lead.__dict__) else None

    def log_event(self, event: str, data: dict) -> None:
        self._post(event, data)


def build_crm(settings: Settings) -> CRMProvider:
    provider = settings.crm_provider.lower()
    if provider == "hubspot":
        return HubSpotCRM(settings.hubspot_access_token)
    if provider == "webhook":
        return WebhookCRM(settings.crm_webhook_url, settings.crm_webhook_secret)
    return LocalCRM()
