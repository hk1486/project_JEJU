from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
import os
import pymysql
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


# Pydantic 모델 정의
class UserInfo(BaseModel):
    id: int


# 데이터 삽입 엔드포인트
@router.post("/user_info")
async def create_user_info(user_info: UserInfo):
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
            add_user = "INSERT INTO user_info (id) VALUES (%s)"
            cursor.execute(add_user, (user_info.id,))
            connection.commit()

        connection.close()
        return {"message": "User info inserted successfully."}

    except pymysql.MySQLError as err:
        raise HTTPException(status_code=500, detail=str(err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/user_info/{user_id}")
async def delete_user_info(user_id: int):
    connection = None
    try:
        # MySQL에 직접 연결
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            autocommit=False  # 자동 커밋 비활성화
        )

        with connection.cursor() as cursor:
            # 사용자 존재 여부 확인
            check_user = "SELECT 1 FROM user_info WHERE id = %s"
            cursor.execute(check_user, (user_id,))
            user_exists = cursor.fetchone()

            if not user_exists:
                # 사용자 정보가 없으면 롤백 및 오류 발생
                connection.rollback()
                raise HTTPException(status_code=404, detail="User ID not found.")

            # 사용자 정보 삭제
            delete_user = "DELETE FROM user_info WHERE id = %s"
            cursor.execute(delete_user, (user_id,))

            # 사용자 존재 여부 확인
            check_user_onboarding = "SELECT 1 FROM onboarding_info WHERE userId = %s"
            cursor.execute(check_user_onboarding, (user_id,))
            user_exists_onboarding = cursor.fetchone()

            if user_exists_onboarding:
                # 온보딩 정보 삭제
                delete_onboarding = "DELETE FROM onboarding_info WHERE userId = %s"
                cursor.execute(delete_onboarding, (user_id,))

            # 모든 작업 성공 시 커밋
            connection.commit()

        return {"message": "User info and onboarding info deleted successfully."}

    except pymysql.MySQLError as err:
        if connection:
            connection.rollback()
        raise HTTPException(status_code=500, detail=str(err))
    except Exception as e:
        if connection:
            connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if connection and connection.open:
            connection.close()