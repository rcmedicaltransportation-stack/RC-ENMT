"""Connected browser test interface adapted from the saved three-app starter."""
import json, sqlite3, uuid, base64, binascii, re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix='/api')
DB = 'connected-demo.db'
STATUSES = ['Pending', 'Scheduled', 'En Route to Pickup', '5 Minutes Away', 'Arrived at Pickup', 'Passenger Onboard', 'En Route to Destination', 'Arrived at Destination', 'Completed', 'Cancelled']
def now(): return datetime.now(timezone.utc).isoformat()
def session(value):
    try: return str(uuid.UUID(value or ''))
    except ValueError: raise HTTPException(400, 'Open the app home page to start a test session.')
def initial():
    return {'rides': [], 'drivers': [{'id':'driver-1','name':'Test Driver 1','shift':{},'phone':'','active':True,'vehicleId':'vehicle-1'}], 'claims':[], 'vehicles':[{'id':'vehicle-1','name':'Test wheelchair van','plate':'SAMPLE','type':'Wheelchair','active':True}], 'messages':[], 'documents':[], 'profile':{}, 'activity':[]}
def migrate(d):
    for key,value in initial().items(): d.setdefault(key,value)
    return d
def log(d, text):
    d['activity'].insert(0,{'at':now(),'text':text})
    d['activity']=d['activity'][:300]
def load(s):
    with sqlite3.connect(DB) as db:
        db.execute('CREATE TABLE IF NOT EXISTS demos (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        row = db.execute('SELECT data FROM demos WHERE id=?', (s,)).fetchone()
        return migrate(json.loads(row[0])) if row else initial()
def change(s, action):
    with sqlite3.connect(DB, timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS demos (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT data FROM demos WHERE id=?',(s,)).fetchone()
        data=migrate(json.loads(row[0])) if row else initial()
        result=action(data)
        db.execute('INSERT INTO demos VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(s,json.dumps(data)))
        return result
class RideIn(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    phone: str = Field(default='',max_length=30)
    date: str = Field(min_length=1,max_length=20)
    time: str = Field(min_length=1,max_length=20)
    pickup: str = Field(min_length=1,max_length=300)
    dropoff: str = Field(min_length=1,max_length=300)
    type: str
    returnTrip: str = 'No'
    notes: str = Field(default='',max_length=1000)
    source: str = 'Passenger App'
    payer: str = 'Private Pay'
    weight: float|None = Field(default=None,ge=0,le=1500)
    assistance: str = Field(default='',max_length=1000)
    appointmentTime: str = Field(default='',max_length=20)
    returnTime: str = Field(default='',max_length=20)
    clientRequestId: str = Field(default='',max_length=100)
    paymentPreference: str = Field(default='Quote requested',max_length=100)
    def validated(self):
        if self.type not in ['Ambulatory','Wheelchair','Gurney']: raise HTTPException(422,'Choose a valid transportation type.')
        if self.returnTrip not in ['No','Yes','Will Call Return']: raise HTTPException(422,'Invalid return option.')
        if self.payer not in ['Private Pay','Medi-Cal','Broker']: raise HTTPException(422,'Invalid payer.')
        try:
            datetime.strptime(self.date,'%Y-%m-%d'); datetime.strptime(self.time,'%H:%M')
        except ValueError: raise HTTPException(422,'Enter a valid date and pickup time.')
        if any(not v.strip() for v in [self.name,self.pickup,self.dropoff]): raise HTTPException(422,'Passenger and addresses are required.')
        return self.model_dump()
def find(data,collection,item):
    result=next((x for x in data[collection] if x['id']==item),None)
    if not result: raise HTTPException(404, 'Record not found in this test session.')
    return result
@router.get('/health')
def health(): return {'ok':True,'mode':'test','service':'RC Medical Transport Connected Apps'}
@router.get('/rides')
def rides(driverId: str|None=None, x_demo_session: str|None=Header(default=None)):
    rs=load(session(x_demo_session))['rides']
    return [r for r in rs if not driverId or r['driverId']==driverId]
@router.post('/rides',status_code=201)
def create_ride(body: RideIn,x_demo_session: str|None=Header(default=None)):
    fields=body.validated()
    def action(d):
        existing=next((r for r in d['rides'] if fields['clientRequestId'] and r.get('clientRequestId')==fields['clientRequestId']),None)
        if existing: return existing
        if len(d['rides'])>=100: raise HTTPException(400,'Test session limit reached.')
        r={**fields,'id':'R-'+uuid.uuid4().hex[:10],'status':'Pending','driverId':None,'createdAt':now(),'events':[],'passengerMiles':0}
        d['rides'].insert(0,r); log(d,'Ride requested: '+r['id']); return r
    return change(session(x_demo_session),action)
@router.get('/drivers')
def drivers(x_demo_session: str|None=Header(default=None)): return load(session(x_demo_session))['drivers']
class AssignIn(BaseModel):
    driverId: str = 'driver-1'
@router.post('/rides/{ride_id}/assign')
def assign(ride_id:str,body:AssignIn=AssignIn(),x_demo_session: str|None=Header(default=None)):
    def action(d):
        r=find(d,'rides',ride_id)
        if r['status'] not in ['Pending','Scheduled']: raise HTTPException(400,'Only pending or scheduled rides can be assigned.')
        driver=find(d,'drivers',body.driverId)
        if not driver.get('active',True): raise HTTPException(400,'Choose an active driver.')
        r.update(driverId=driver['id'],driver=driver['name'],status='Scheduled',updatedAt=now())
        r['events'].append({'status':'Scheduled','at':now()}); log(d,'Driver assigned: '+ride_id); return r
    return change(session(x_demo_session),action)
class EventIn(BaseModel):
    status:str
    passengerMiles: float|None=Field(default=None,ge=0,le=10000)
@router.post('/rides/{ride_id}/events')
def event(ride_id:str,body:EventIn,x_demo_session: str|None=Header(default=None)):
    if body.status not in STATUSES: raise HTTPException(422,'Invalid status.')
    def action(d):
        r=find(d,'rides',ride_id)
        if r['status'] in ['Completed','Cancelled']: raise HTTPException(400,'This ride is closed.')
        transitions={'Scheduled':['En Route to Pickup','Cancelled'],'En Route to Pickup':['5 Minutes Away','Arrived at Pickup'],'5 Minutes Away':['Arrived at Pickup'],'Arrived at Pickup':['Passenger Onboard'],'Passenger Onboard':['En Route to Destination'],'En Route to Destination':['Arrived at Destination'],'Arrived at Destination':['Completed'],'Pending':['Cancelled']}
        if body.status not in transitions.get(r['status'],[]): raise HTTPException(400,'Follow the trip steps in order.')
        if body.status=='Completed' and body.passengerMiles is None: raise HTTPException(422,'Passenger mileage is required.')
        r['status']=body.status; r['updatedAt']=now()
        if body.passengerMiles is not None: r['passengerMiles']=body.passengerMiles
        if body.status=='Passenger Onboard': r['pickupAt']=now()
        if body.status=='Arrived at Destination': r['dropoffAt']=now()
        r['events'].append({'status':body.status,'at':now()}); log(d,ride_id+': '+body.status); return r
    return change(session(x_demo_session),action)
class ShiftIn(BaseModel):
    active:bool
    odometer:float=Field(ge=0,le=2000000)
@router.post('/drivers/{driver_id}/shift')
def shift(driver_id:str,body:ShiftIn,x_demo_session: str|None=Header(default=None)):
    def action(d):
        driver=find(d,'drivers',driver_id); prev=driver['shift']
        if body.active:
            if prev.get('active'): raise HTTPException(400,'A shift is already active.')
            if prev.get('endedAt'): driver.setdefault('shifts',[]).append(prev.copy())
            driver['shift']={'active':True,'startOdometer':body.odometer,'startedAt':now(),'date':datetime.now(ZoneInfo('America/Los_Angeles')).date().isoformat()}
        else:
            if not prev.get('active'): raise HTTPException(400,'Start a shift first.')
            if body.odometer<prev['startOdometer']: raise HTTPException(422,'Ending odometer must be at least the starting odometer.')
            prev.update(active=False,endOdometer=body.odometer,totalMiles=body.odometer-prev['startOdometer'],endedAt=now())
        log(d,driver['name']+(': shift started' if body.active else ': shift ended'))
        return driver['shift']
    return change(session(x_demo_session),action)
@router.get('/claims')
def claims(x_demo_session: str|None=Header(default=None)): return load(session(x_demo_session))['claims']
@router.post('/billing/claims/from-ride/{ride_id}')
def claim(ride_id:str,x_demo_session: str|None=Header(default=None)):
    def action(d):
        r=find(d,'rides',ride_id)
        if r['status']!='Completed': raise HTTPException(400,'Complete the ride before creating its billing draft.')
        existing=next((c for c in d['claims'] if c['rideId']==ride_id),None)
        if existing: return existing
        c={'id':'C-'+uuid.uuid4().hex[:10],'rideId':ride_id,'status':'Draft','patient':r['name'],'date':r['date'],'transport':r['type'],'pickup':r['pickup'],'destination':r['dropoff'],'passengerMiles':r.get('passengerMiles',0),'payer':r['payer'],'createdAt':now(),'reviewNeeded':['Verified procedure codes and units','Verified payer rates and charges','Patient and provider identifiers','PCS/TAR and payer requirements'],'submissionEnabled':False}
        d['claims'].insert(0,c); return c
    return change(session(x_demo_session),action)
class ClaimReview(BaseModel):
    memberId: str = Field(default='',max_length=100)
    dob: str = Field(default='',max_length=20)
    diagnosis: str = Field(default='',max_length=200)
    authorization: str = Field(default='',max_length=100)
    placeOfService: str = Field(default='',max_length=10)
    procedureCode: str = Field(default='',max_length=20)
    modifiers: str = Field(default='',max_length=50)
    units: float = Field(default=0,ge=0,le=100000)
    charge: float = Field(default=0,ge=0,le=1000000)
    providerName: str = Field(default='',max_length=200)
    providerNpi: str = Field(default='',max_length=20)
    patientAddress: str = Field(default='',max_length=300)
    notes: str = Field(default='',max_length=1000)
@router.post('/claims/{claim_id}/review')
def review_claim(claim_id:str,body:ClaimReview,x_demo_session:str|None=Header(default=None)):
    def action(d):
        c=find(d,'claims',claim_id)
        c['review']=body.model_dump();c['updatedAt']=now();c['status']='Draft'
        c['missingFields']=[label for field,label in [('memberId','Member ID'),('dob','Date of birth'),('diagnosis','Diagnosis'),('placeOfService','Place of service'),('procedureCode','Procedure code'),('providerNpi','Provider NPI')] if not c['review'][field].strip()]
        if body.units<=0:c['missingFields'].append('Verified units')
        if body.charge<=0:c['missingFields'].append('Charge')
        c['validationNotice']='Starter completeness check only; payer review is still required.'
        c['boxPreview']={'1a':body.memberId,'2':c['patient'],'3':body.dob,'5':body.patientAddress,'21':body.diagnosis,'23':body.authorization,'24A':c['date'],'24B':body.placeOfService,'24D':' '.join(x for x in [body.procedureCode,body.modifiers] if x),'24F':body.charge,'24G':body.units,'28':body.charge,'33':body.providerName,'33a':body.providerNpi}
        return c
    return change(session(x_demo_session),action)

class ProfileIn(BaseModel):
    name: str = Field(default='',max_length=100)
    phone: str = Field(default='',max_length=30)
    pickup: str = Field(default='',max_length=300)
    assistance: str = Field(default='',max_length=1000)
@router.get('/workspace')
def workspace(x_demo_session:str|None=Header(default=None)):
    d=load(session(x_demo_session))
    return {k:v for k,v in d.items() if k!='documents'} | {'documents':[{k:v for k,v in f.items() if k!='data'} for f in d['documents']]}
@router.post('/profile')
def profile(body:ProfileIn,x_demo_session:str|None=Header(default=None)):
    def action(d): d['profile']=body.model_dump(); return d['profile']
    return change(session(x_demo_session),action)
class MessageIn(BaseModel):
    role: str
    text: str = Field(min_length=1,max_length=1500)
    rideId: str = Field(default='',max_length=100)
@router.post('/messages')
def post_message(body:MessageIn,x_demo_session:str|None=Header(default=None)):
    if body.role not in ['Customer','Driver','Dispatch']: raise HTTPException(422,'Invalid view.')
    if not body.text.strip(): raise HTTPException(422,'Enter a message.')
    def action(d):
        if len(d['messages'])>=300: raise HTTPException(400,'Test message limit reached.')
        if body.rideId: find(d,'rides',body.rideId)
        m={**body.model_dump(),'id':uuid.uuid4().hex,'at':now()}; d['messages'].append(m); return m
    return change(session(x_demo_session),action)
class DriverIn(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    phone: str = Field(default='',max_length=30)
    vehicleId: str = Field(default='',max_length=100)
    active: bool = True
@router.post('/drivers/{driver_id}/details')
def update_driver(driver_id:str,body:DriverIn,x_demo_session:str|None=Header(default=None)):
    def action(d):
        r=find(d,'drivers',driver_id)
        if body.vehicleId: find(d,'vehicles',body.vehicleId)
        r.update(body.model_dump());log(d,'Driver details updated: '+r['name']);return r
    return change(session(x_demo_session),action)
@router.post('/drivers')
def add_driver(body:DriverIn,x_demo_session:str|None=Header(default=None)):
    def action(d):
        if len(d['drivers'])>=20: raise HTTPException(400,'Test driver limit reached.')
        if body.vehicleId: find(d,'vehicles',body.vehicleId)
        r={**body.model_dump(),'id':'D-'+uuid.uuid4().hex[:8],'shift':{}}; d['drivers'].append(r);log(d,'Driver added: '+r['name']);return r
    return change(session(x_demo_session),action)
class VehicleIn(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    plate: str = Field(default='',max_length=30)
    type: str
    active: bool = True
@router.post('/vehicles/{vehicle_id}/details')
def update_vehicle(vehicle_id:str,body:VehicleIn,x_demo_session:str|None=Header(default=None)):
    if body.type not in ['Ambulatory','Wheelchair','Gurney']: raise HTTPException(422,'Invalid transport type.')
    def action(d):
        r=find(d,'vehicles',vehicle_id);r.update(body.model_dump());log(d,'Vehicle details updated: '+r['name']);return r
    return change(session(x_demo_session),action)
@router.post('/vehicles')
def add_vehicle(body:VehicleIn,x_demo_session:str|None=Header(default=None)):
    if body.type not in ['Ambulatory','Wheelchair','Gurney']: raise HTTPException(422,'Invalid transport type.')
    def action(d):
        if len(d['vehicles'])>=20: raise HTTPException(400,'Test vehicle limit reached.')
        r={**body.model_dump(),'id':'V-'+uuid.uuid4().hex[:8]}; d['vehicles'].append(r);log(d,'Vehicle added: '+r['name']);return r
    return change(session(x_demo_session),action)
class ChecklistIn(BaseModel):
    eligibility: str = 'Not checked'
    pcs: str = 'Not checked'
    tar: str = 'Not checked'
    notes: str = Field(default='',max_length=1000)
@router.post('/rides/{ride_id}/checklist')
def checklist(ride_id:str,body:ChecklistIn,x_demo_session:str|None=Header(default=None)):
    allowed=['Not checked','Sample review recorded','Missing sample document','Not applicable']
    if any(x not in allowed for x in [body.eligibility,body.pcs,body.tar]): raise HTTPException(422,'Invalid review selection.')
    def action(d):
        r=find(d,'rides',ride_id);r['checklist']=body.model_dump();log(d,'Test checklist saved: '+ride_id);return r
    return change(session(x_demo_session),action)
class DocumentIn(BaseModel):
    rideId: str
    name: str = Field(min_length=1,max_length=100)
    category: str
    data: str = Field(max_length=180000)
@router.post('/documents')
def upload_document(body:DocumentIn,x_demo_session:str|None=Header(default=None)):
    if body.category not in ['Sample PCS','Sample TAR','Sample ID','Odometer start','Odometer end','Other sample document']: raise HTTPException(422,'Invalid category.')
    try: raw=base64.b64decode(body.data,validate=True)
    except (ValueError,binascii.Error): raise HTTPException(422,'Invalid file encoding.')
    if len(raw)>128*1024: raise HTTPException(413,'Sample files must be 128 KB or less.')
    mime='application/pdf' if raw.startswith(b'%PDF-') else 'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None
    if not mime: raise HTTPException(422,'Use a sample PDF, PNG or JPEG file.')
    def action(d):
        find(d,'rides',body.rideId)
        if len(d['documents'])>=20: raise HTTPException(400,'Test file limit reached.')
        f={**body.model_dump(),'id':'F-'+uuid.uuid4().hex[:8],'mime':mime,'size':len(raw),'at':now()};d['documents'].append(f);log(d,'Sample document attached: '+body.rideId);return {k:v for k,v in f.items() if k!='data'}
    return change(session(x_demo_session),action)
@router.get('/documents/{file_id}')
def get_document(file_id:str,x_demo_session:str|None=Header(default=None)):
    return find(load(session(x_demo_session)),'documents',file_id)
class PaymentIn(BaseModel):
    method: str
@router.post('/rides/{ride_id}/test-payment')
def test_payment(ride_id:str,body:PaymentIn,x_demo_session:str|None=Header(default=None)):
    if body.method not in ['Request a quote','Simulate payment']: raise HTTPException(422,'Invalid test choice.')
    def action(d):
        r=find(d,'rides',ride_id)
        if r['payer']!='Private Pay': raise HTTPException(400,'Only private-pay rides use this test screen.')
        r['payment']={'status':'Simulated — no money collected' if body.method=='Simulate payment' else 'Quote requested','method':body.method,'at':now(),'amount':None};log(d,'Test payment choice saved: '+ride_id);return r
    return change(session(x_demo_session),action)

def connect(app):
    # Replace the status-only homepage; preserve the original API routes.
    app.router.routes[:]=[r for r in app.router.routes if getattr(r,'path',None) != '/']
    app.include_router(router)
    async def page(): return FileResponse(Path(__file__).with_name('connected.html'))
    for route in ['/', '/passenger','/driver','/admin']:
        app.add_api_route(route,page,methods=['GET'],include_in_schema=False)
