from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, APIRouter
from pydantic import BaseModel
import os
from sshtunnel import SSHTunnelForwarder
import pymysql
from typing import List

load_dotenv()

router = APIRouter()

# SSH 및 MySQL 연결 정보
SSH_HOSTNAME = os.getenv('SSH_HOSTNAME')
SSH_PORT = int(os.getenv('SSH_PORT'))
SSH_USERNAME = os.getenv('SSH_USERNAME')
SSH_KEY_FILE = os.getenv('SSH_KEY_FILE')

MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

def save_onboarding_info(user_id: int, age_range: int, gender: int, travel_type: List[str]):
    # 여행 타입 리스트를 문자열로 변환 (예: "둘레길, 해안가 드라이브")
    travel_type_str = ", ".join(travel_type)

    try:
        with SSHTunnelForwarder(
                (SSH_HOSTNAME, SSH_PORT),
                ssh_username=SSH_USERNAME,
                ssh_pkey=SSH_KEY_FILE,
                remote_bind_address=(MYSQL_HOSTNAME, MYSQL_PORT)
        ) as tunnel:
            tunnel.start()
            connection = pymysql.connect(
                host='127.0.0.1',
                port=tunnel.local_bind_port,
                user=MYSQL_USERNAME,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE
            )

            with connection.cursor() as cursor:
                add_user = "INSERT INTO onboarding_info (user_id, age_range, gender, travel_type) VALUES (%s, %s, %s, %s)"
                cursor.execute(add_user, (user_id, age_range, gender, travel_type_str))
                connection.commit()

            connection.close()
            return {"message": "User info inserted successfully."}

    finally:
        connection.close()

class OnboardingInfo(BaseModel):
    userId: int
    ageRange: int
    gender: int
    travelType: List[str]

@router.post("/onboarding/", status_code=status.HTTP_200_OK)
async def receive_onboarding_info(info: OnboardingInfo):
    """
    유저의 온보딩 정보를 수신하고 데이터베이스에 저장합니다.
    """
    try:
        save_onboarding_info(
            user_id=info.userId,
            age_range=info.ageRange,
            gender=info.gender,
            travel_type=info.travelType
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

    return {"status": "success", "message": "Data saved successfully."}
