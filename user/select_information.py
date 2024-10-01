from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, APIRouter
from pydantic import BaseModel
import os
import pymysql
from typing import List, Optional
import json

load_dotenv()

router = APIRouter()

# MySQL 연결 정보 (기존과 동일)
MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

def get_onboarding_info(user_id: int) -> Optional[dict]:
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
            query = "SELECT ageRange, gender, travelType FROM onboarding_info WHERE userId = %s"
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()

        if result:
            age_range, gender, travel_type_json = result
            # JSON 문자열을 리스트로 변환
            travel_type = json.loads(travel_type_json)

            # 여행 타입 역매핑 딕셔너리 정의
            travel_type_reverse_mapping = {
                "바다": "#해안가 드라이브",
                "축제": "#로컬 축제 즐기기",
                "카페": "#카페에서 휴식",
                "맛집": "#맛있는 음식은 필수",
                "힐링": "#힐링",
                "호캉스": "#호캉스",
                "캠핑": "#캠핑",
                "재래시장": "#놓칠 수 없는 쇼핑",
                "체험": "#체험·액티비티",
                "자연": "#자연경관 감상"
            }
            # travel_type 리스트를 역매핑된 값으로 변환
            mapped_travel_type = [travel_type_reverse_mapping.get(item, item) for item in travel_type]

            return {
                "userId": user_id,
                "ageRange": age_range,
                "gender": gender,
                "travelType": mapped_travel_type
            }
        else:
            return None

    except pymysql.MySQLError as e:
        raise HTTPException(status_code=500, detail=f"MySQL Error: {str(e)}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

    finally:
        if connection and connection.open:
            connection.close()

class OnboardingResponse(BaseModel):
    userId: int
    ageRange: int
    gender: int
    travelType: List[str]

@router.get("/information/{user_id}", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
async def retrieve_onboarding_info(user_id: int):
    """
    요청된 userId에 해당하는 온보딩 정보를 조회하여 반환합니다.
    """
    try:
        onboarding_info = get_onboarding_info(user_id)
        if onboarding_info:
            return onboarding_info
        else:
            raise HTTPException(status_code=404, detail="User not found.")

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")