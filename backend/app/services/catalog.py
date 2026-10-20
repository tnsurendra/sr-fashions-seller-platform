from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Inventory, Product, ProductVariant, Store
from app.schemas import ProductCreate


def require(db: Session, model, item_id: int):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, f"{model.__name__} not found")
    return item


def validate_store(db: Session, store_id: int, seller_id: int):
    # Lock store ownership until this transaction finishes.
    store = db.scalar(select(Store).where(Store.id == store_id).with_for_update())
    if store is None:
        raise HTTPException(404, "Store not found")
    if store.seller_id != seller_id:
        raise HTTPException(422, "Store and product must belong to the same seller")
    return store


def create_product(db: Session, payload: ProductCreate):
    product = Product(**payload.model_dump(exclude={"variants"}))
    db.add(product)
    for data in payload.variants:
        variant = ProductVariant(**data.model_dump(exclude={"initial_stock", "store_id"}), product=product)
        db.add(variant)
        if data.store_id is not None:
            validate_store(db, data.store_id, product.seller_id)
            db.add(Inventory(variant=variant, store_id=data.store_id, quantity=data.initial_stock))
    db.commit()
    db.refresh(product)
    return product
