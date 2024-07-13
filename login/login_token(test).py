from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")


class TokenRequest(BaseModel):
    access_token: str


class User(BaseModel):
    id: int
    properties: dict
    kakao_account: dict


async def get_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        user_info_response = await client.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if user_info_response.status_code != 200:
            raise HTTPException(status_code=user_info_response.status_code, detail="User info request failed")

        return user_info_response.json()


@app.post("/auth/kakao/verify")
async def verify_kakao_token(token_request: TokenRequest):
    user_data = await get_user_info(token_request.access_token)
    user = User(**user_data)

    # 여기서 사용자 정보를 데이터베이스에 저장하거나 기존 사용자 정보를 갱신하는 로직을 추가할 수 있습니다.

    return {"user": user}
