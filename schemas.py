"""
Database Schemas for Online Real Estate Management System

Each Pydantic model represents a collection in MongoDB. The collection name
is the lowercase of the class name (e.g., User -> "user").
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime

# -----------------------------
# Core domain models
# -----------------------------

class User(BaseModel):
    full_name: str
    email: EmailStr
    mobile: str
    password_hash: Optional[str] = None
    role: Literal["ADMIN", "OWNER", "BUYER"] = "BUYER"
    status: Literal["ACTIVE", "SUSPENDED"] = "ACTIVE"

class PropertyImage(BaseModel):
    file_path: str
    is_primary: bool = False

class Property(BaseModel):
    owner_id: str = Field(..., description="User _id of owner as string")
    title: str
    description: Optional[str] = None
    property_type: Literal[
        "APARTMENT", "HOUSE", "PLOT", "COMMERCIAL", "INDUSTRIAL"
    ]
    price: float
    currency: str = "INR"
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
    verified: bool = False
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"
    images: List[PropertyImage] = []

class Message(BaseModel):
    sender_id: str
    receiver_id: str
    property_id: Optional[str] = None
    subject: str
    body: str
    is_read: bool = False

class Payment(BaseModel):
    buyer_id: str
    property_id: str
    amount: float
    currency: str = "INR"
    purpose: Literal["BOOKING", "DEPOSIT", "OTHER"] = "BOOKING"
    provider: Optional[Literal["RAZORPAY", "STRIPE", "MANUAL"]] = "MANUAL"
    provider_payment_id: Optional[str] = None
    status: Literal["INITIATED", "SUCCESS", "FAILED", "REFUNDED"] = "INITIATED"

# Simple schema exposure for tooling
class SchemaInfo(BaseModel):
    name: str
    fields: dict


def get_schema_definitions():
    return [
        SchemaInfo(name="user", fields=User.model_json_schema()),
        SchemaInfo(name="property", fields=Property.model_json_schema()),
        SchemaInfo(name="message", fields=Message.model_json_schema()),
        SchemaInfo(name="payment", fields=Payment.model_json_schema()),
    ]
