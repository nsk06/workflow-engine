from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import User, authenticate_user, create_access_token, get_current_user
from app.schemas_auth import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    token = create_access_token(user.username)
    return LoginResponse(access_token=token, username=user.username)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"username": user.username}
