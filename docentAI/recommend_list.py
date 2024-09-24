from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
import os
import pymysql
import pandas as pd
from math import radians, cos, sin, asin, sqrt
from datetime import datetime

load_dotenv()

app = FastAPI()
router = APIRouter()

MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

# 데이터베이스 연결 함수
def connect_mysql():
    try:
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        return connection
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        raise HTTPException(status_code=500, detail="Database connection failed.")

@router.get("/user_recommendations/{userId}")
async def get_user_recommendations(userId: int):
    # 중복된 contentid를 제외하고 해당 유저가 추천받은 관광지를 가져오는 쿼리
    query = """
        SELECT DISTINCT ON (contentid) 
            userId, contentid, title, mapx, mapy, address, firstimage, story, recommended_at
        FROM user_recommendations
        WHERE userId = %s
        ORDER BY recommended_at DESC;
    """
    
    try:
        connection = connect_mysql()
        df = pd.read_sql(query, connection, params=(userId,))
        connection.close()

        if df.empty:
            raise HTTPException(status_code=404, detail="No recommendations found for this user.")

        # DataFrame을 JSON으로 변환하여 반환
        recommendations = df.to_dict(orient="records")
        return JSONResponse(content=recommendations)

    except pymysql.MySQLError as e:
        print(f"Error fetching recommendations for user {userId}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch user recommendations.")

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")