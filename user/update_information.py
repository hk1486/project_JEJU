from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, APIRouter
from pydantic import BaseModel
import os
import pymysql
from typing import List
import json
import warnings
warnings.filterwarnings('ignore')

load_dotenv()

router = APIRouter()

# MySQL 연결 정보 (기존과 동일)
MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

def update_onboarding_info(user_id: int, age_range: int, gender: int, travel_type: List[str]):
    # 여행 타입 매핑 딕셔너리 정의 (기존과 동일)
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
            # 먼저 해당 userId가 존재하는지 확인
            check_user = "SELECT 1 FROM onboarding_info WHERE userId = %s"
            cursor.execute(check_user, (user_id,))
            result = cursor.fetchone()

            if result:
                # userId가 존재하면 업데이트 수행
                update_user = "UPDATE onboarding_info SET ageRange = %s, gender = %s, travelType = %s WHERE userId = %s"
                cursor.execute(update_user, (age_range, gender, travel_type_json, user_id))
                connection.commit()
                return {"message": "User info updated successfully."}
            else:
                # userId가 존재하지 않으면 오류 발생
                raise HTTPException(status_code=404, detail="User not found.")

    except pymysql.MySQLError as e:
        raise HTTPException(status_code=500, detail=f"MySQL Error: {str(e)}")

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

    finally:
        if connection and connection.open:
            connection.close()

class OnboardingUpdateInfo(BaseModel):
    userId: int
    ageRange: int
    gender: int
    travelType: List[str]

@router.post("/information/update", status_code=status.HTTP_200_OK)
async def update_onboarding(info: OnboardingUpdateInfo):
    """
    온보딩 정보를 업데이트합니다.
    """
    try:
        response = update_onboarding_info(
            user_id=info.userId,
            age_range=info.ageRange,
            gender=info.gender,
            travel_type=info.travelType
        )
        return {"status": "success", "message": response["message"]}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")