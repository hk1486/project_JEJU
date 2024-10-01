from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
import os
import pymysql
from course.search import search
import warnings
warnings.filterwarnings('ignore')

load_dotenv()

router = APIRouter()

# MySQL 연결 정보
MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')


# Pydantic 모델 정의
class SearchRequest(BaseModel):
    name: str
    sigungucode: str

# 데이터베이스 연결 함수
def get_db_connection():
    connection = pymysql.connect(
        host=MYSQL_HOSTNAME,
        port=MYSQL_PORT,
        user=MYSQL_USERNAME,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )
    return connection


# search
@router.get("/search")
async def search_router(name: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            return search(cursor, name)
    except pymysql.MySQLError as err:
        print(f"Database Error: {err}")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        connection.close()

