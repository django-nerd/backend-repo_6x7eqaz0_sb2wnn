import os
from typing import List, Optional, Literal, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone
from hashlib import sha256
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User, Property, Message, Payment, get_schema_definitions

app = FastAPI(title="Real Estate Management API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Helpers ----------
class IdResponse(BaseModel):
    id: str


def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


def now_utc():
    return datetime.now(timezone.utc)


def unique_index(collection: str, field: str):
    try:
        db[collection].create_index(field, unique=True)
    except Exception:
        pass


# Create useful indexes (idempotent)
unique_index("user", "email")
unique_index("user", "mobile")
db["property"].create_index([("city", 1), ("state", 1), ("property_type", 1)])
db["property"].create_index([("price", 1)])


# ---------- Root & Health ----------
@app.get("/")
def read_root():
    return {"message": "Real Estate Management API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


# ---------- Schema exposure ----------
@app.get("/schema")
def read_schema():
    return [s.model_dump() for s in get_schema_definitions()]


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    mobile: str
    password: str
    role: Literal["ADMIN", "OWNER", "BUYER"] = "BUYER"


@app.post("/auth/register", response_model=IdResponse)
def register(req: RegisterRequest):
    # Ensure unique email/mobile
    existing = db["user"].find_one({"$or": [{"email": req.email}, {"mobile": req.mobile}]})
    if existing:
        raise HTTPException(status_code=409, detail="Email or mobile already registered")

    password_hash = sha256(req.password.encode()).hexdigest()
    user = User(
        full_name=req.full_name,
        email=req.email,
        mobile=req.mobile,
        password_hash=password_hash,
        role=req.role,
    )
    new_id = create_document("user", user)
    return {"id": new_id}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    mobile: str
    role: str


@app.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    u = db["user"].find_one({"email": req.email, "status": "ACTIVE"})
    if not u:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    hashed = sha256(req.password.encode()).hexdigest()
    if u.get("password_hash") != hashed:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {
        "id": str(u["_id"]),
        "full_name": u["full_name"],
        "email": u["email"],
        "mobile": u["mobile"],
        "role": u["role"],
    }


# ---------- Properties ----------
class PropertyCreate(Property):
    pass


class PropertyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    property_type: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    area_sqft: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    parking: Optional[bool] = None
    furnished: Optional[bool] = None
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: Optional[str] = None
    images: Optional[List[dict]] = None


@app.post("/properties", response_model=IdResponse)
def create_property(req: PropertyCreate):
    # Verify owner exists
    owner = db["user"].find_one({"_id": to_object_id(req.owner_id)})
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    new_id = create_document("property", req)
    return {"id": new_id}


@app.get("/properties")
def list_properties(
    q: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    property_type: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    bedrooms: Optional[int] = None,
    bathrooms: Optional[int] = None,
    furnished: Optional[bool] = None,
    parking: Optional[bool] = None,
    sort: Optional[Literal["newest", "price_asc", "price_desc"]] = "newest",
    skip: int = 0,
    limit: int = 20,
):
    filt: dict[str, Any] = {"status": {"$ne": "INACTIVE"}}
    if city:
        filt["city"] = city
    if state:
        filt["state"] = state
    if property_type:
        filt["property_type"] = property_type
    if bedrooms is not None:
        filt["bedrooms"] = bedrooms
    if bathrooms is not None:
        filt["bathrooms"] = bathrooms
    if furnished is not None:
        filt["furnished"] = furnished
    if parking is not None:
        filt["parking"] = parking
    if min_price is not None or max_price is not None:
        price_cond = {}
        if min_price is not None:
            price_cond["$gte"] = min_price
        if max_price is not None:
            price_cond["$lte"] = max_price
        filt["price"] = price_cond
    if q:
        filt["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"city": {"$regex": q, "$options": "i"}},
            {"state": {"$regex": q, "$options": "i"}},
        ]

    sort_spec = [("_id", -1)]
    if sort == "price_asc":
        sort_spec = [("price", 1)]
    elif sort == "price_desc":
        sort_spec = [("price", -1)]

    cursor = db["property"].find(filt).sort(sort_spec).skip(max(0, skip)).limit(min(max(1, limit), 100))
    items = []
    for d in cursor:
        d["id"] = str(d.pop("_id"))
        items.append(d)
    return {"items": items, "count": len(items)}


@app.get("/properties/{property_id}")
def get_property(property_id: str):
    d = db["property"].find_one({"_id": to_object_id(property_id)})
    if not d:
        raise HTTPException(status_code=404, detail="Property not found")
    d["id"] = str(d.pop("_id"))
    return d


@app.put("/properties/{property_id}")
def update_property(property_id: str, body: PropertyUpdate):
    update = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    update["updated_at"] = now_utc()
    res = db["property"].update_one({"_id": to_object_id(property_id)}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Property not found")
    return {"updated": True}


@app.delete("/properties/{property_id}")
def delete_property(property_id: str):
    res = db["property"].delete_one({"_id": to_object_id(property_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Property not found")
    return {"deleted": True}


class VerifyRequest(BaseModel):
    verified: bool


@app.post("/properties/{property_id}/verify")
def verify_property(property_id: str, body: VerifyRequest):
    res = db["property"].update_one({"_id": to_object_id(property_id)}, {"$set": {"verified": body.verified, "updated_at": now_utc()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Property not found")
    return {"verified": body.verified}


# ---------- Messages ----------
class MessageCreate(Message):
    pass


@app.post("/messages", response_model=IdResponse)
def create_message(req: MessageCreate):
    # Validate users
    for uid in [req.sender_id, req.receiver_id]:
        if not db["user"].find_one({"_id": to_object_id(uid)}):
            raise HTTPException(status_code=404, detail=f"User not found: {uid}")
    if req.property_id:
        if not db["property"].find_one({"_id": to_object_id(req.property_id)}):
            raise HTTPException(status_code=404, detail="Property not found")
    new_id = create_document("message", req)
    return {"id": new_id}


@app.get("/messages")
def list_messages(user_id: str):
    uid = to_object_id(user_id)
    msgs = db["message"].find({"$or": [{"sender_id": user_id}, {"receiver_id": user_id}]})\
        .sort([("_id", -1)]).limit(100)
    items = []
    for m in msgs:
        m["id"] = str(m.pop("_id"))
        items.append(m)
    return {"items": items}


# ---------- Payments ----------
class PaymentCreate(Payment):
    pass


class PaymentStatusUpdate(BaseModel):
    status: Literal["INITIATED", "SUCCESS", "FAILED", "REFUNDED"]
    provider_payment_id: Optional[str] = None


@app.post("/payments", response_model=IdResponse)
def create_payment(req: PaymentCreate):
    # Validate buyer and property
    if not db["user"].find_one({"_id": to_object_id(req.buyer_id)}):
        raise HTTPException(status_code=404, detail="Buyer not found")
    if not db["property"].find_one({"_id": to_object_id(req.property_id)}):
        raise HTTPException(status_code=404, detail="Property not found")
    new_id = create_document("payment", req)
    return {"id": new_id}


@app.get("/payments")
def list_payments(buyer_id: Optional[str] = None):
    filt = {}
    if buyer_id:
        filt["buyer_id"] = buyer_id
    docs = db["payment"].find(filt).sort([("_id", -1)]).limit(100)
    items = []
    for d in docs:
        d["id"] = str(d.pop("_id"))
        items.append(d)
    return {"items": items}


@app.post("/payments/{payment_id}/status")
def update_payment_status(payment_id: str, body: PaymentStatusUpdate):
    update = {"status": body.status, "updated_at": now_utc()}
    if body.provider_payment_id:
        update["provider_payment_id"] = body.provider_payment_id
    res = db["payment"].update_one({"_id": to_object_id(payment_id)}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"updated": True}


# ---------- Admin helpers ----------
@app.get("/admin/users")
def admin_list_users(limit: int = 50):
    users = db["user"].find({}).sort([("_id", -1)]).limit(min(limit, 200))
    items = []
    for u in users:
        u["id"] = str(u.pop("_id"))
        items.append(u)
    return {"items": items}


class UserStatusUpdate(BaseModel):
    status: Literal["ACTIVE", "SUSPENDED"]


@app.post("/admin/users/{user_id}/status")
def admin_update_user_status(user_id: str, body: UserStatusUpdate):
    res = db["user"].update_one({"_id": to_object_id(user_id)}, {"$set": {"status": body.status, "updated_at": now_utc()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"updated": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
