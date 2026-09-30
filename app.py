
from datetime import datetime
from enum import Enum
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, String, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

app = FastAPI(title="RC Medical Transport NEMT")
engine = create_engine("sqlite:///nemt.db", connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)

class Base(DeclarativeBase): pass

class TripStatus(str, Enum):
    REQUESTED="requested"; ACCEPTED="accepted"; SCHEDULED="scheduled"
    DRIVER_ASSIGNED="driver_assigned"; EN_ROUTE="en_route"; FIVE_MIN_AWAY="five_min_away"
    ARRIVED="arrived"; PASSENGER_ON_BOARD="passenger_on_board"
    AT_DESTINATION="at_destination"; COMPLETED="completed"; CANCELLED="cancelled"

class BillingStatus(str, Enum):
    NOT_READY="not_ready"; READY="ready"; SUBMITTED="submitted"
    ACCEPTED="accepted"; PAID="paid"; DENIED="denied"; NEEDS_CORRECTION="needs_correction"

class Client(Base):
    __tablename__="clients"
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String)
    phone: Mapped[str]=mapped_column(String)
    email: Mapped[Optional[str]]=mapped_column(String, nullable=True)
    member_id: Mapped[Optional[str]]=mapped_column(String, nullable=True)

class Driver(Base):
    __tablename__="drivers"
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String)
    phone: Mapped[str]=mapped_column(String)
    active: Mapped[bool]=mapped_column(Boolean, default=True)

class Payer(Base):
    __tablename__="payers"
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String)
    payer_type: Mapped[str]=mapped_column(String) # medi-cal, health-plan, private-pay, other
    electronic_payer_id: Mapped[Optional[str]]=mapped_column(String, nullable=True)

class Trip(Base):
    __tablename__="trips"
    id: Mapped[int]=mapped_column(primary_key=True)
    client_id: Mapped[int]=mapped_column(ForeignKey("clients.id"))
    driver_id: Mapped[Optional[int]]=mapped_column(ForeignKey("drivers.id"), nullable=True)
    payer_id: Mapped[Optional[int]]=mapped_column(ForeignKey("payers.id"), nullable=True)
    source: Mapped[str]=mapped_column(String, default="manual") # manual / website
    pickup: Mapped[str]=mapped_column(String)
    destination: Mapped[str]=mapped_column(String)
    appointment_time: Mapped[datetime]=mapped_column(DateTime)
    transport_type: Mapped[str]=mapped_column(String)
    round_trip: Mapped[bool]=mapped_column(Boolean, default=False)
    authorization_number: Mapped[Optional[str]]=mapped_column(String, nullable=True)
    miles: Mapped[float]=mapped_column(Float, default=0)
    wait_minutes: Mapped[int]=mapped_column(Integer, default=0)
    status: Mapped[str]=mapped_column(String, default=TripStatus.REQUESTED.value)
    billing_status: Mapped[str]=mapped_column(String, default=BillingStatus.NOT_READY.value)
    base_charge: Mapped[float]=mapped_column(Float, default=0)
    mileage_charge: Mapped[float]=mapped_column(Float, default=0)
    wait_charge: Mapped[float]=mapped_column(Float, default=0)
    amount_paid: Mapped[float]=mapped_column(Float, default=0)
    payment_method: Mapped[Optional[str]]=mapped_column(String, nullable=True)
    five_min_text_sent: Mapped[bool]=mapped_column(Boolean, default=False)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

class ClientIn(BaseModel):
    name: str; phone: str; email: Optional[str]=None; member_id: Optional[str]=None

class TripIn(BaseModel):
    client_id: int
    pickup: str
    destination: str
    appointment_time: datetime
    transport_type: str
    round_trip: bool=False
    payer_id: Optional[int]=None
    authorization_number: Optional[str]=None
    source: str="manual"

class PaymentIn(BaseModel):
    amount: float
    method: str

def send_sms(phone: str, message: str):
    # Replace with your HIPAA-appropriate SMS vendor/API.
    print(f"SMS -> {phone}: {message}")

def submit_claim_to_clearinghouse(trip: Trip):
    # Adapter point for approved clearinghouse/payer API.
    # Build the payer-required claim/encounter format here.
    return {"queued": True, "trip_id": trip.id}

@app.get("/")
def home():
    return {"system":"RC Medical Transport NEMT","status":"running"}

@app.post("/clients")
def create_client(data: ClientIn):
    with Session() as db:
        c=Client(**data.model_dump()); db.add(c); db.commit(); db.refresh(c)
        return {"id":c.id,"name":c.name}

@app.post("/website/ride-request")
def website_ride_request(data: TripIn):
    payload=data.model_dump(); payload["source"]="website"
    with Session() as db:
        t=Trip(**payload, status=TripStatus.REQUESTED.value)
        db.add(t); db.commit(); db.refresh(t)
        return {"trip_id":t.id,"status":"requested","message":"Awaiting dispatcher approval"}

@app.post("/trips")
def manual_trip(data: TripIn):
    with Session() as db:
        t=Trip(**data.model_dump(), status=TripStatus.SCHEDULED.value)
        db.add(t); db.commit(); db.refresh(t)
        return {"trip_id":t.id,"status":t.status}

@app.post("/trips/{trip_id}/accept")
def accept_trip(trip_id:int):
    with Session() as db:
        t=db.get(Trip,trip_id)
        if not t: raise HTTPException(404,"Trip not found")
        t.status=TripStatus.SCHEDULED.value; db.commit()
        return {"trip_id":t.id,"status":t.status}

@app.post("/trips/{trip_id}/assign/{driver_id}")
def assign_driver(trip_id:int, driver_id:int):
    with Session() as db:
        t=db.get(Trip,trip_id); d=db.get(Driver,driver_id)
        if not t or not d: raise HTTPException(404,"Trip or driver not found")
        t.driver_id=d.id; t.status=TripStatus.DRIVER_ASSIGNED.value
        c=db.get(Client,t.client_id)
        send_sms(c.phone, f"RC Medical Transport: {d.name} has been assigned to your ride.")
        db.commit()
        return {"trip_id":t.id,"driver":d.name,"status":t.status}

@app.post("/trips/{trip_id}/status/{status}")
def update_status(trip_id:int, status:TripStatus):
    with Session() as db:
        t=db.get(Trip,trip_id)
        if not t: raise HTTPException(404,"Trip not found")
        c=db.get(Client,t.client_id)
        t.status=status.value
        if status==TripStatus.FIVE_MIN_AWAY and not t.five_min_text_sent:
            send_sms(c.phone,"RC Medical Transport: Your driver is approximately 5 minutes away. Please be ready for pickup.")
            t.five_min_text_sent=True
        elif status==TripStatus.ARRIVED:
            send_sms(c.phone,"RC Medical Transport: Your driver has arrived.")
        elif status==TripStatus.COMPLETED:
            t.billing_status=BillingStatus.READY.value
        db.commit()
        return {"trip_id":t.id,"status":t.status,"billing_status":t.billing_status}

@app.get("/billing/ready")
def ready_to_bill():
    with Session() as db:
        trips=db.query(Trip).filter(Trip.billing_status==BillingStatus.READY.value).all()
        return [{"trip_id":t.id,"payer_id":t.payer_id,"miles":t.miles,
                 "authorization_number":t.authorization_number,
                 "total":round(t.base_charge+t.mileage_charge+t.wait_charge,2)} for t in trips]

@app.post("/billing/{trip_id}/submit")
def submit_claim(trip_id:int):
    with Session() as db:
        t=db.get(Trip,trip_id)
        if not t: raise HTTPException(404,"Trip not found")
        if t.billing_status!=BillingStatus.READY.value:
            raise HTTPException(400,"Trip is not ready to bill")
        result=submit_claim_to_clearinghouse(t)
        t.billing_status=BillingStatus.SUBMITTED.value
        db.commit()
        return {"trip_id":t.id,"billing_status":t.billing_status,"clearinghouse":result}

@app.post("/payments/{trip_id}")
def record_payment(trip_id:int, payment:PaymentIn):
    with Session() as db:
        t=db.get(Trip,trip_id)
        if not t: raise HTTPException(404,"Trip not found")
        t.amount_paid += payment.amount; t.payment_method=payment.method
        total=t.base_charge+t.mileage_charge+t.wait_charge
        if t.amount_paid >= total: t.billing_status=BillingStatus.PAID.value
        db.commit()
        return {"receipt_number":f"RC-{t.id:06d}",
                "trip_id":t.id,"paid":t.amount_paid,"method":t.payment_method,
                "balance":max(round(total-t.amount_paid,2),0)}

@app.get("/receipts/{trip_id}")
def receipt(trip_id:int):
    with Session() as db:
        t=db.get(Trip,trip_id)
        if not t: raise HTTPException(404,"Trip not found")
        c=db.get(Client,t.client_id)
        total=t.base_charge+t.mileage_charge+t.wait_charge
        return {"receipt_number":f"RC-{t.id:06d}","company":"RC Medical Transport",
                "client":c.name,"trip_date":t.appointment_time,
                "pickup":t.pickup,"destination":t.destination,
                "total":round(total,2),"paid":round(t.amount_paid,2),
                "balance":max(round(total-t.amount_paid,2),0),
                "payment_method":t.payment_method}

@app.get("/dashboard")
def dashboard():
    with Session() as db:
        return {
            "new_requests": db.query(Trip).filter(Trip.status==TripStatus.REQUESTED.value).count(),
            "scheduled": db.query(Trip).filter(Trip.status==TripStatus.SCHEDULED.value).count(),
            "ready_to_bill": db.query(Trip).filter(Trip.billing_status==BillingStatus.READY.value).count(),
            "submitted_claims": db.query(Trip).filter(Trip.billing_status==BillingStatus.SUBMITTED.value).count(),
            "paid": db.query(Trip).filter(Trip.billing_status==BillingStatus.PAID.value).count(),
        }
