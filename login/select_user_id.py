from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel, ValidationError
from typing import Union
import os
import pymysql
import warnings
warnings.filterwarnings('ignore')

load_dotenv()

app = FastAPI()
router = APIRouter()

# MySQL 연결 정보
MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

# Pydantic 모델 정의
class UserInfo(BaseModel):
    id: Union[int, str]  # id가 숫자가 아닐 경우를 대비해 Union[int, str] 사용

# 유저 정보 조회 엔드포인트
@router.post("/check_user")
async def check_user_info(user_info: UserInfo):
    # id가 숫자가 아닌 경우 예외 처리
    if not isinstance(user_info.id, int):
        raise HTTPException(status_code=422, detail="Invalid input type. 'id' must be an integer.")

    try:
        # MySQL에 직접 연결
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )

        with connection.cursor() as cursor:
            check_user_query = "SELECT id FROM user_info WHERE id = %s"
            cursor.execute(check_user_query, (user_info.id,))
            user_exists = cursor.fetchone()

            if user_exists:
                # onboarding_info 테이블에서 유저 존재 여부 확인
                check_onboarding_query = "SELECT userId FROM onboarding_info WHERE userId = %s"
                cursor.execute(check_onboarding_query, (user_info.id,))
                onboarding_exists = cursor.fetchone()

                if onboarding_exists:
                    # 유저가 onboarding_info 테이블에 존재하는 경우
                    return {"message": "User exists.", "status": "success"}
                else:
                    # 유저가 onboarding_info 테이블에 존재하지 않는 경우
                    return {"message": "User exists.", "status": "onboarding"}
            else:
                # 유저가 user_info 테이블에 존재하지 않는 경우
                return {"message": "User not exists.", "status": "fail"}

    except pymysql.MySQLError as err:
        raise HTTPException(status_code=500, detail=str(err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()


# 라우터를 FastAPI 애플리케이션에 포함
app.include_router(router)