"""Connected browser test interface adapted from the saved three-app starter."""
import json, sqlite3, uuid
from datetime import datetime, timezone
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
def load(s):
    with sqlite3.connect(DB) as db:
        db.execute('CREATE TABLE IF NOT EXISTS demos (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        row = db.execute('SELECT data FROM demos WHERE id=?', (s,)).fetchone()
        return json.loads(row[0]) if row else {'rides': [], 'drivers': [{'id':'driver-1','name':'Test Driver 1','shift':{}}], 'claims':[]}
def change(s, action):
    with sqlite3.connect(DB, timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS demos (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT data FROM demos WHERE id=?',(s,)).fetchone()
        data=json.loads(row[0]) if row else {'rides': [], 'drivers':[{'id':'driver-1','name':'Test Driver 1','shift':{}}], 'claims':[]}
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
    def validated(self):
        if self.type not in ['Ambulatory','Wheelchair','Gurney']: raise HTTPException(422,'Choose a valid transportation type.')
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
        if len(d['rides'])>=100: raise HTTPException(400,'Test session limit reached.')
        r={**fields,'id':'R-'+uuid.uuid4().hex[:10],'status':'Pending','driverId':None,'createdAt':now(),'events':[],'passengerMiles':0}
        d['rides'].insert(0,r); return r
    return change(session(x_demo_session),action)
@router.get('/drivers')
def drivers(x_demo_session: str|None=Header(default=None)): return load(session(x_demo_session))['drivers']
@router.post('/rides/{ride_id}/assign')
def assign(ride_id:str,x_demo_session: str|None=Header(default=None)):
    def action(d):
        r=find(d,'rides',ride_id)
        if r['status'] in ['Completed','Cancelled']: raise HTTPException(400,'This ride is closed.')
        r.update(driverId='driver-1',driver='Test Driver 1',status='Scheduled',updatedAt=now())
        r['events'].append({'status':'Scheduled','at':now()}); return r
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
        if body.status=='Completed' and r['status']!='Arrived at Destination': raise HTTPException(400,'Mark arrival at destination before completing this ride.')
        r['status']=body.status; r['updatedAt']=now()
        if body.passengerMiles is not None: r['passengerMiles']=body.passengerMiles
        if body.status=='Passenger Onboard': r['pickupAt']=now()
        if body.status=='Arrived at Destination': r['dropoffAt']=now()
        r['events'].append({'status':body.status,'at':now()}); return r
    return change(session(x_demo_session),action)
class ShiftIn(BaseModel):
    active:bool
    odometer:float=Field(ge=0,le=2000000)
@router.post('/drivers/driver-1/shift')
def shift(body:ShiftIn,x_demo_session: str|None=Header(default=None)):
    def action(d):
        driver=d['drivers'][0]; prev=driver['shift']
        if body.active:
            if prev.get('active'): raise HTTPException(400,'A shift is already active.')
            driver['shift']={'active':True,'startOdometer':body.odometer,'startedAt':now()}
        else:
            if not prev.get('active'): raise HTTPException(400,'Start a shift first.')
            if body.odometer<prev['startOdometer']: raise HTTPException(422,'Ending odometer must be at least the starting odometer.')
            prev.update(active=False,endOdometer=body.odometer,totalMiles=body.odometer-prev['startOdometer'],endedAt=now())
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

def connect(app):
    # Replace the status-only homepage; preserve the original API routes.
    app.router.routes[:]=[r for r in app.router.routes if getattr(r,'path',None) != '/']
    app.include_router(router)
    async def page(): return FileResponse(Path(__file__).with_name('connected.html'))
    for route in ['/', '/passenger','/driver','/admin']:
        app.add_api_route(route,page,methods=['GET'],include_in_schema=False)
