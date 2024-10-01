from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, APIRouter
from pydantic import BaseModel
import os
import pymysql
from typing import List
import json
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")

load_dotenv()

router = APIRouter()

# MySQL 연결 정보
MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

def save_onboarding_info(user_id: int, age_range: int, gender: int, travel_type: List[str]):
    # 여행 타입 매핑 딕셔너리 정의
    travel_type_mapping = {
        "#해안가 드라이브": "바다",
        "#로컬 축제 즐기기": "축제",
        "#카페에서 휴식": "카페",
        "#맛있는 음식은 필수": "맛집",
        "#힐링": "힐링",
        "#호캉스": "호캉스",
        "#캠핑": "캠핑",
        "#놓칠 수 없는 쇼핑": "재래시장",
        "#체험·액티비티": "체험",
        "#자연경관 감상": "자연"
    }
    # travel_type 리스트를 매핑된 값으로 변환
    mapped_travel_type = [travel_type_mapping.get(item, item) for item in travel_type]

    # 매핑된 여행 타입 리스트를 JSON 문자열로 변환
    travel_type_json = json.dumps(mapped_travel_type, ensure_ascii=False)

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

    except pymysql.MySQLError as e:
        raise HTTPException(status_code=500, detail=f"MySQL Error: {str(e)}")

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
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

    return {"status": "success", "message": "Data saved successfully."}