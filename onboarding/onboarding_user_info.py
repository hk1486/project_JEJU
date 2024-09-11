from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, APIRouter
from pydantic import BaseModel
import os
import pymysql
from typing import List
import json

load_dotenv()

router = APIRouter()

# MySQL 연결 정보
MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

def save_onboarding_info(user_id: int, age_range: int, gender: int, travel_type: List[str]):
    # 여행 타입 리스트를 JSON 문자열로 변환
    travel_type_json = json.dumps(travel_type)

    connection = None
    try:
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )

        with connection.cursor() as cursor:
            add_user = "INSERT INTO onboarding_info (userId, ageRange, gender, travelType) VALUES (%s, %s, %s, %s)"
            cursor.execute(add_user, (user_id, age_range, gender, travel_type_json))
            connection.commit()

        connection.close()
        return {"message": "User info inserted successfully."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

    finally:
        if connection and connection.open:
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