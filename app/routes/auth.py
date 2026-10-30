import json
import asyncio
import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.models.user import User, Role, UserRole, Practitioner, Patient, UserSession, Pharmacist
from app.models.pharmacy import PharmacyStore
from app.models.verification import AuditEvent
from app.schemas.auth import (
    LoginRequest,
    OtpLoginRequest,
    RegisterRequest,
    RefreshTokenRequest,
    AuthResponse,
    SessionStatusResponse,
    UserProfileSchema,
    ActiveSessionSchema
)
from app.services.auth_service import (
    AuthService,
    extract_token_from_request,
    get_current_user_optional,
    get_current_user,
    event_bus
)
from app.services.otp_service import OtpService

router = APIRouter(prefix="/api/auth", tags=["Production Authentication & Real-Time Sessions"])

@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Authenticate user via Email/Phone + Password.
    Returns session token and sets secure HTTP-only session cookie.
    Broadcasts real-time login event across connected clients.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("User-Agent", "Unknown Client")

    success, msg, access_token, refresh_token, profile = AuthService.authenticate_by_credentials(
        db=db,
        email_or_phone=payload.email_or_phone,
        password=payload.password,
        ip_address=client_ip,
        user_agent=user_agent,
        remember_me=payload.remember_me
    )

    if not success or not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=msg
        )

    # Set secure session cookie (30 days if remember_me, else 24 hours)
    max_age = 30 * 86400 if payload.remember_me else 86400
    response.set_cookie(
        key="healthslip_session",
        value=access_token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=False # Set to True when HTTPS is enabled
    )

    # Broadcast real-time login event
    await event_bus.broadcast("USER_LOGIN", {
        "user_id": profile.id,
        "email": profile.email,
        "full_name": profile.full_name,
        "role": profile.primary_role,
        "ip": client_ip
    })

    return AuthResponse(
        success=True,
        message="Login successful. Secure session established.",
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in_seconds=max_age,
        user=profile
    )

@router.post("/refresh", response_model=AuthResponse)
def refresh_token_endpoint(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    """
    Exchange valid refresh token for a newly issued short-lived access JWT token.
    """
    success, msg, new_access_token, profile = AuthService.refresh_access_token(db, payload.refresh_token)
    if not success or not new_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=msg
        )

    return AuthResponse(
        success=True,
        message="Access token refreshed successfully.",
        access_token=new_access_token,
        refresh_token=payload.refresh_token,
        token_type="bearer",
        expires_in_seconds=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=profile
    )

@router.post("/login-otp", response_model=AuthResponse)
async def login_with_otp(payload: OtpLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Two-Factor / Passwordless mobile authentication via verified 6-digit OTP.
    Auto-links or initializes Patient account in healthslip_prod.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("User-Agent", "Unknown Client")

    # Verify OTP against salt-hashed DB record
    success, msg, _ = OtpService.verify_otp(
        db=db,
        phone_number=payload.phone_number,
        otp_code=payload.otp_code,
        ip_address=client_ip
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    clean_phone = payload.phone_number.strip().replace(" ", "").replace("-", "")
    user = db.query(User).filter(User.phone_number == clean_phone).first()

    if not user:
        # Create Patient user if new
        user = User(
            email=f"patient_{clean_phone[-4:]}@healthslip.local",
            phone_number=clean_phone,
            password_hash=AuthService.hash_password("Patient@2026"),
            status="ACTIVE",
            is_phone_verified=True
        )
        db.add(user)
        db.flush()

        # Link Patient role
        patient_role = db.query(Role).filter(Role.code == "PATIENT").first()
        if patient_role:
            db.add(UserRole(user_id=user.id, role_id=patient_role.id))

        # Create Patient profile
        patient = Patient(
            user_id=user.id,
            first_name="Patient",
            last_name=f"({clean_phone[-4:]})",
            gender="UNDISCLOSED"
        )
        db.add(patient)
        db.commit()

    # Create session
    session_rec, token = AuthService.create_session(
        db=db,
        user=user,
        ip_address=client_ip,
        user_agent=user_agent,
        remember_me=True
    )

    profile = AuthService.build_user_profile(user)

    response.set_cookie(
        key="healthslip_session",
        value=token,
        max_age=86400,
        httponly=True,
        samesite="lax",
        secure=False
    )

    await event_bus.broadcast("USER_LOGIN", {
        "user_id": profile.id,
        "email": profile.email,
        "full_name": profile.full_name,
        "role": profile.primary_role,
        "method": "OTP",
        "ip": client_ip
    })

    return AuthResponse(
        success=True,
        message="OTP verified. Authenticated successfully.",
        access_token=token,
        token_type="bearer",
        expires_in_seconds=86400,
        user=profile
    )

@router.post("/register", response_model=AuthResponse)
async def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Register a new user (Doctor, Patient, or Admin) with cryptographic PBKDF2 password hashing.
    Establishes real-time session immediately.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("User-Agent", "Unknown Client")
    clean_phone = payload.phone_number.strip().replace(" ", "").replace("-", "")
    clean_email = payload.email.strip().lower()

    # Check for existing email or phone
    existing = db.query(User).filter((User.email == clean_email) | (User.phone_number == clean_phone)).first()
    if existing:
        if existing.email.lower() == clean_email:
            raise HTTPException(status_code=400, detail="An account with this email already exists.")
        raise HTTPException(status_code=400, detail="An account with this mobile number already exists.")

    # Hash password with PBKDF2
    password_hash = AuthService.hash_password(payload.password)

    new_user = User(
        email=clean_email,
        phone_number=clean_phone,
        password_hash=password_hash,
        status="ACTIVE",
        is_phone_verified=False,
        is_email_verified=False
    )
    db.add(new_user)
    db.flush()

    # Assign role
    role_code = payload.role_code.upper()
    role = db.query(Role).filter(Role.code == role_code).first()
    if not role:
        role = db.query(Role).filter(Role.code == "PATIENT").first()

    if role:
        db.add(UserRole(user_id=new_user.id, role_id=role.id))

    # Parse full name
    name_parts = payload.full_name.strip().split(" ", 1)
    f_name = name_parts[0]
    l_name = name_parts[1] if len(name_parts) > 1 else ""

    # Role specific entities
    if role_code == "DOCTOR":
        license_num = payload.doctor_license or f"DOC-2026-{new_user.id:04d}"
        spec = payload.doctor_specialization or "General & Internal Medicine"
        practitioner = Practitioner(
            user_id=new_user.id,
            license_number=license_num,
            specialization=spec,
            department="Clinical Medicine"
        )
        db.add(practitioner)
    elif role_code == "PHARMACIST":
        reg_num = payload.pharmacist_registration or f"PHAR-2026-{new_user.id:04d}"
        if payload.store_id:
            new_user.store_id = payload.store_id
        pharmacist = Pharmacist(
            user_id=new_user.id,
            store_id=payload.store_id,
            registration_number=reg_num,
            qualification="B.Pharm / Registered Pharmacist"
        )
        db.add(pharmacist)
    elif role_code == "ADMIN":
        pass
    else:
        # Patient
        gender_val = payload.gender.upper() if payload.gender and payload.gender.upper() in ('MALE', 'FEMALE', 'OTHER') else 'UNDISCLOSED'
        dob = datetime.date(1996, 5, 12)
        if payload.date_of_birth:
            try:
                dob = datetime.datetime.strptime(payload.date_of_birth, "%Y-%m-%d").date()
            except Exception:
                pass

        patient = Patient(
            user_id=new_user.id,
            first_name=f_name,
            last_name=l_name,
            gender=gender_val,
            date_of_birth=dob
        )
        db.add(patient)

    db.commit()

    # Automatically create session with JWT tokens
    session_rec, access_token, refresh_token = AuthService.create_session(
        db=db,
        user=new_user,
        ip_address=client_ip,
        user_agent=user_agent
    )

    profile = AuthService.build_user_profile(new_user)

    response.set_cookie(
        key="healthslip_session",
        value=access_token,
        max_age=86400,
        httponly=True,
        samesite="lax",
        secure=False
    )

    await event_bus.broadcast("USER_REGISTER", {
        "user_id": profile.id,
        "email": profile.email,
        "full_name": profile.full_name,
        "role": profile.primary_role
    })

    return AuthResponse(
        success=True,
        message="Account registered successfully. Signed in.",
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in_seconds=86400,
        user=profile
    )

@router.post("/logout")
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Logout active session in real-time.
    Invalidates session token in MySQL healthslip_prod, logs audit trail,
    clears HTTP-only cookies, and broadcasts real-time logout notification to all active browser tabs.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("User-Agent", "Unknown Client")
    token = extract_token_from_request(request)

    user_info = None
    if token:
        user = AuthService.validate_token(db, token)
        if user:
            user_info = {
                "user_id": user.id,
                "email": user.email,
                "full_name": user.email
            }
        AuthService.logout_session(db, token, client_ip, user_agent)

    # Invalidate cookie
    response.delete_cookie(
        key="healthslip_session",
        httponly=True,
        samesite="lax"
    )

    # Broadcast real-time logout across all active client views/tabs
    await event_bus.broadcast("USER_LOGOUT", {
        "message": "User session destroyed.",
        "user": user_info,
        "ip": client_ip
    })

    return {
        "success": True,
        "message": "Logged out successfully. Cryptographic session invalidated in real-time."
    }

@router.get("/me", response_model=UserProfileSchema)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """Fetch current authenticated user profile and permissions"""
    return AuthService.build_user_profile(current_user)

@router.get("/status", response_model=SessionStatusResponse)
def get_session_status(request: Request, db: Session = Depends(get_db)):
    """
    Real-time session status query without throwing 401 exceptions.
    Ideal for client initialization, cross-tab synchronization, and status badges.
    """
    token = extract_token_from_request(request)
    if not token:
        return SessionStatusResponse(
            authenticated=False,
            message="No active session found."
        )

    now = datetime.datetime.utcnow()
    session_rec = db.query(UserSession).filter(
        UserSession.session_token == token,
        UserSession.is_active == True,
        UserSession.expires_at > now
    ).first()

    if not session_rec or not session_rec.user:
        return SessionStatusResponse(
            authenticated=False,
            message="Session is expired or has been revoked."
        )

    profile = AuthService.build_user_profile(session_rec.user)
    return SessionStatusResponse(
        authenticated=True,
        message="Active verified session.",
        user=profile,
        session_id=session_rec.id,
        expires_at=session_rec.expires_at.isoformat()
    )

@router.get("/sessions", response_model=List[ActiveSessionSchema])
def list_my_active_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all active sessions for current user with IP, device, and current token marker"""
    current_token = extract_token_from_request(request)
    now = datetime.datetime.utcnow()
    sessions = db.query(UserSession).filter(
        UserSession.user_id == current_user.id,
        UserSession.is_active == True,
        UserSession.expires_at > now
    ).order_by(UserSession.created_at.desc()).all()

    return [
        ActiveSessionSchema(
            id=s.id,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            created_at=s.created_at,
            is_active=s.is_active,
            is_current=(s.session_token == current_token)
        ) for s in sessions
    ]

@router.get("/stream")
async def realtime_auth_events(request: Request):
    """
    Server-Sent Events (SSE) stream for real-time authentication state updates.
    Broadcasts login, logout, and security events to keep all open tabs in sync.
    """
    queue = event_bus.subscribe()

    async def event_generator():
        try:
            # Send initial connection ping
            yield f"event: connected\ndata: {json.dumps({'status': 'listening', 'timestamp': datetime.datetime.utcnow().isoformat()})}\n\n"
            while True:
                # Disconnect if client closed connection
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat keep-alive
                    yield f": keep-alive\n\n"
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
