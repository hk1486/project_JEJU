from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
import os
import pymysql

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
    nickname: str


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
            add_user = "INSERT INTO user_info (id, nickname) VALUES (%s, %s)"
            cursor.execute(add_user, (user_info.id, user_info.nickname))
            connection.commit()

        connection.close()
        return {"message": "User info inserted successfully."}

    except pymysql.MySQLError as err:
        raise HTTPException(status_code=500, detail=str(err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))