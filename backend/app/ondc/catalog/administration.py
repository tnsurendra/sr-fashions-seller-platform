
"""Internal metadata API DTOs and composition; no secrets or protocol routing."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Seller, Store, Product
from app.ondc.catalog.publication import PublicationProfile, StorePublication, ProductPublication
from app.ondc.schemas.base import WireModel
from app.ondc.catalog.taxonomy import category_definition
from pydantic import field_validator, model_validator
from decimal import Decimal
from typing import Literal
from app.ondc.schemas.base import Text
from pydantic import Field
from app.ondc.models import SellerPublication, StorePublicationRow, ProductPublicationRow, CatalogPublicationState
import time

class FinderFeePolicy(WireModel):
    # Internal merchant policy using the published finder-fee term names.
    finder_fee_type: Literal["amount", "percent"]
    finder_fee_amount_min: Text = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?$")
    finder_fee_amount_max: Text = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?$")

    @model_validator(mode="after")
    def fee_range(self):
        if Decimal(self.finder_fee_amount_min) > Decimal(self.finder_fee_amount_max):
            raise ValueError("Finder fee minimum exceeds maximum")
        return self


class ProviderPublication(PublicationProfile):
    finder_fee_policy: FinderFeePolicy | None = None
    stores: dict[int, StorePublication] = {}
    products: dict[int, ProductPublication] = {}

    @field_validator("category_mapping")
    @classmethod
    def official_categories(cls, values):
        for value in values.values():
            category_definition(value)
        return values

class ProviderInput(WireModel):
    enabled: bool = False
    metadata: ProviderPublication

class PublicationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def safe_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                errors = [{"loc": e["loc"], "type": e["type"], "msg": e["msg"]} for e in exc.errors()]
                return JSONResponse(status_code=422, content={"detail": errors})
        return safe_handler


router = APIRouter(prefix="/api/ondc/publication", tags=["ONDC publication administration"], route_class=PublicationRoute)

def owner(db, model, identity):
    obj = db.get(model, identity)
    if obj is None:
        raise HTTPException(404, "Record not found")
    return obj

def put(db, row_type, key, identity, data, enabled=None):
    row = db.get(row_type, identity)
    if row is None:
        row = row_type(**{key: identity, "data": data})
        db.add(row)
    else:
        row.data = data
    if enabled is not None:
        row.enabled = enabled
    entity_type = {SellerPublication: "provider", StorePublicationRow: "store", ProductPublicationRow: "product"}[row_type]
    state = db.scalar(select(CatalogPublicationState).where(
        CatalogPublicationState.entity_type == entity_type, CatalogPublicationState.entity_id == identity))
    if state is None:
        state = CatalogPublicationState(entity_type=entity_type, entity_id=identity,
            state="pending", changed_at=time.time())
        db.add(state)
    else:
        state.state, state.changed_at = "pending", time.time()
        state.rejection_code = state.rejection_message = None
    db.commit()
    return row

def load_profile(db, seller_id):
    provider = db.get(SellerPublication, seller_id)
    if provider is None:
        raise ValueError("Provider metadata missing")
    stores = db.scalars(select(Store).where(Store.seller_id == seller_id)).all()
    products = db.scalars(select(Product).where(Product.seller_id == seller_id)).all()
    values = dict(provider.data)
    values.pop("finder_fee_policy", None)
    values["stores"] = {s.id: owner_metadata(db, StorePublicationRow, s.id) for s in stores}
    values["products"] = {p.id: owner_metadata(db, ProductPublicationRow, p.id) for p in products}
    return PublicationProfile.model_validate(values)

def owner_metadata(db, cls, identity):
    row = db.get(cls, identity)
    if row is None:
        raise ValueError("Publication metadata missing")
    return row.data

@router.put("/sellers/{identity}", response_model=ProviderInput)
def put_seller(identity: int, payload: ProviderInput, db: Session = Depends(get_db)):
    owner(db, Seller, identity)
    if payload.metadata.stores or payload.metadata.products:
        raise HTTPException(422, "Use store/product publication endpoints")
    # A single inventory seller is one provider; avoid accidental aggregation.
    if payload.enabled and db.scalar(select(SellerPublication).where(
            SellerPublication.enabled.is_(True), SellerPublication.seller_id != identity)):
        raise HTTPException(409, "An inventory seller provider is already enabled")
    put(db, SellerPublication, "seller_id", identity,
        payload.metadata.model_dump(mode="json", exclude={"stores", "products"}), payload.enabled)
    return payload

@router.get("/sellers/{identity}", response_model=ProviderInput)
def get_seller(identity: int, db: Session = Depends(get_db)):
    owner(db, Seller, identity)
    row = db.get(SellerPublication, identity)
    if row is None:
        raise HTTPException(404, "Publication metadata not configured")
    return {"enabled": row.enabled, "metadata": row.data}

@router.put("/stores/{identity}", response_model=StorePublication)
def put_store(identity: int, payload: StorePublication, db: Session = Depends(get_db)):
    owner(db, Store, identity)
    from app.ondc.schemas.catalog import Location
    Location.valid_coordinates(payload.gps)
    if any(t.value != f"store-{identity}" for g in payload.tags for t in g.list if t.code == "location"):
        raise HTTPException(422, "Store tag location must match this store")
    put(db, StorePublicationRow, "store_id", identity, payload.model_dump(mode="json"))
    return payload

@router.get("/stores/{identity}", response_model=StorePublication)
def get_store(identity: int, db: Session = Depends(get_db)):
    owner(db, Store, identity)
    row = db.get(StorePublicationRow, identity)
    if row is None:
        raise HTTPException(404, "Publication metadata not configured")
    return row.data

@router.put("/products/{identity}", response_model=ProductPublication)
def put_product(identity: int, payload: ProductPublication, db: Session = Depends(get_db)):
    owner(db, Product, identity)
    put(db, ProductPublicationRow, "product_id", identity, payload.model_dump(mode="json"))
    return payload

@router.get("/products/{identity}", response_model=ProductPublication)
def get_product(identity: int, db: Session = Depends(get_db)):
    owner(db, Product, identity)
    row = db.get(ProductPublicationRow, identity)
    if row is None:
        raise HTTPException(404, "Publication metadata not configured")
    return row.data
