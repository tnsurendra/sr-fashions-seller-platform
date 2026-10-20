from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.database import get_db
from app.models import Seller, Store, Product, ProductVariant, Inventory
from app.schemas import (SellerWrite, SellerRead, StoreWrite, StoreRead, ProductCreate,
    ProductWrite, ProductRead, VariantWrite, VariantRead, InventoryWrite, InventoryUpdate, InventoryRead)
from app.services.catalog import require, validate_store, create_product

router = APIRouter(prefix="/api")
DB = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


def save(db, item, payload):
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def remove(db, item):
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@router.get("/sellers", response_model=list[SellerRead], tags=["Sellers"])
def sellers(db: DB, limit: Limit = 100, offset: Offset = 0):
    return db.scalars(select(Seller).order_by(Seller.id).offset(offset).limit(limit)).all()


@router.post("/sellers", response_model=SellerRead, status_code=201, tags=["Sellers"])
def add_seller(payload: SellerWrite, db: DB):
    return save(db, Seller(), payload)


@router.get("/sellers/{item_id}", response_model=SellerRead, tags=["Sellers"])
def seller(item_id: int, db: DB):
    return require(db, Seller, item_id)


@router.put("/sellers/{item_id}", response_model=SellerRead, tags=["Sellers"])
def update_seller(item_id: int, payload: SellerWrite, db: DB):
    return save(db, require(db, Seller, item_id), payload)


@router.delete("/sellers/{item_id}", status_code=204, tags=["Sellers"])
def delete_seller(item_id: int, db: DB):
    return remove(db, require(db, Seller, item_id))


@router.get("/stores", response_model=list[StoreRead], tags=["Stores"])
def stores(db: DB, seller_id: int | None = None, limit: Limit = 100, offset: Offset = 0):
    query = select(Store)
    if seller_id is not None:
        query = query.where(Store.seller_id == seller_id)
    return db.scalars(query.order_by(Store.id).offset(offset).limit(limit)).all()


@router.post("/stores", response_model=StoreRead, status_code=201, tags=["Stores"])
def add_store(payload: StoreWrite, db: DB):
    require(db, Seller, payload.seller_id)
    return save(db, Store(), payload)


@router.get("/stores/{item_id}", response_model=StoreRead, tags=["Stores"])
def store(item_id: int, db: DB):
    return require(db, Store, item_id)


@router.put("/stores/{item_id}", response_model=StoreRead, tags=["Stores"])
def update_store(item_id: int, payload: StoreWrite, db: DB):
    item = require(db, Store, item_id)
    if payload.seller_id != item.seller_id:
        raise HTTPException(422, "Store ownership cannot be changed")
    return save(db, item, payload)


@router.delete("/stores/{item_id}", status_code=204, tags=["Stores"])
def delete_store(item_id: int, db: DB):
    return remove(db, require(db, Store, item_id))


@router.get("/products", response_model=list[ProductRead], tags=["Products"])
def products(db: DB, seller_id: int | None = None, limit: Limit = 100, offset: Offset = 0):
    query = select(Product).options(selectinload(Product.variants))
    if seller_id is not None:
        query = query.where(Product.seller_id == seller_id)
    return db.scalars(query.order_by(Product.id).offset(offset).limit(limit)).all()


@router.post("/products", response_model=ProductRead, status_code=201, tags=["Products"])
def add_product(payload: ProductCreate, db: DB):
    require(db, Seller, payload.seller_id)
    return create_product(db, payload)


@router.get("/products/{item_id}", response_model=ProductRead, tags=["Products"])
def product(item_id: int, db: DB):
    return require(db, Product, item_id)


@router.put("/products/{item_id}", response_model=ProductRead, tags=["Products"])
def update_product(item_id: int, payload: ProductWrite, db: DB):
    return save(db, require(db, Product, item_id), payload)


@router.put("/products/{item_id}/variants/{variant_id}", response_model=VariantRead, tags=["Products"])
def update_variant(item_id: int, variant_id: int, payload: VariantWrite, db: DB):
    item = require(db, ProductVariant, variant_id)
    if item.product_id != item_id:
        raise HTTPException(404, "Variant not found for this product")
    return save(db, item, payload)


@router.delete("/products/{item_id}", status_code=204, tags=["Products"])
def delete_product(item_id: int, db: DB):
    return remove(db, require(db, Product, item_id))


@router.get("/inventory", response_model=list[InventoryRead], tags=["Inventory"])
def inventory(db: DB, store_id: int | None = None, limit: Limit = 100, offset: Offset = 0):
    query = select(Inventory)
    if store_id is not None:
        query = query.where(Inventory.store_id == store_id)
    return db.scalars(query.order_by(Inventory.id).offset(offset).limit(limit)).all()


@router.post("/inventory", response_model=InventoryRead, status_code=201, tags=["Inventory"])
def add_inventory(payload: InventoryWrite, db: DB):
    variant = require(db, ProductVariant, payload.variant_id)
    validate_store(db, payload.store_id, variant.product.seller_id)
    return save(db, Inventory(), payload)


@router.get("/inventory/{item_id}", response_model=InventoryRead, tags=["Inventory"])
def inventory_item(item_id: int, db: DB):
    return require(db, Inventory, item_id)


@router.put("/inventory/{item_id}", response_model=InventoryRead, tags=["Inventory"])
def update_inventory(item_id: int, payload: InventoryUpdate, db: DB):
    return save(db, require(db, Inventory, item_id), payload)


@router.delete("/inventory/{item_id}", status_code=204, tags=["Inventory"])
def delete_inventory(item_id: int, db: DB):
    return remove(db, require(db, Inventory, item_id))
