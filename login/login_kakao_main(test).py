from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2AuthorizationCodeBearer
from pydantic import BaseModel
from starlette.requests import Request
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")
# print(KAKAO_REST_API_KEY)

class Token(BaseModel):
    access_token: str
    token_type: str

class User(BaseModel):
    id: int
    properties: dict
    kakao_account: dict

@app.get("/auth/kakao/login")
async def kakao_login():
    kakao_auth_url = (
        f"https://kauth.kakao.com/oauth/authorize?response_type=code"
        f"&client_id={KAKAO_REST_API_KEY}&redirect_uri=http://localhost:8000/auth/kakao/callback"
    )
    return {"auth_url": kakao_auth_url}

@app.get("/auth/kakao/callback")
async def kakao_callback(code: str):
    token_url = "https://kauth.kakao.com/oauth/token"
    redirect_uri = "http://localhost:8000/auth/kakao/callback"

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": KAKAO_REST_API_KEY,
                "redirect_uri": redirect_uri,
                "code": code,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if token_response.status_code != 200:
            raise HTTPException(status_code=token_response.status_code, detail="Token request failed")

        token_data = token_response.json()
        access_token = token_data["access_token"]

        user_info_response = await client.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if user_info_response.status_code != 200:
            raise HTTPException(status_code=user_info_response.status_code, detail="User info request failed")

        user_data = user_info_response.json()

    return {"token": token_data, "user": user_data}
