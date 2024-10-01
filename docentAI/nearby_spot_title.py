from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
import os
import pymysql
import pandas as pd
from math import radians, cos, sin, asin, sqrt
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

load_dotenv()

app = FastAPI()
router = APIRouter()

MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

# Pydantic 모델 정의
class RecommendationInput(BaseModel):
    userId: int = Field(..., example=1)
    mapx: float = Field(..., example=126.5312)
    mapy: float = Field(..., example=33.4996)

class RecommendationOutput(BaseModel):
    contentid: int
    title: str

# 데이터베이스 연결 및 쿼리 실행 함수
def connect_mysql(query, params=None):
    try:
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        # print(f"Executing query: {query} with params: {params}")  # 디버깅용 로그
        df = pd.read_sql(query, connection, params=params)
        # print(f"DataFrame head:\n{df.head()}")  # 데이터 확인용 로그
        return df

    except Exception as e:
        print(f"Error: {str(e)}")
        return pd.DataFrame()

    finally:
        connection.close()


@router.post("/recommendation", response_model=RecommendationOutput)
async def get_recommendation(input_data: RecommendationInput):
    userId = input_data.userId
    mapx = input_data.mapx
    mapy = input_data.mapy

    # 가장 가까운 관광지를 찾기 위한 SQL 쿼리
    query = f"""
            SELECT 
                contentid, title, mapx, mapy, address, firstimage, story,
                (6371 * ACOS(
                    COS(RADIANS(%s)) * COS(RADIANS(mapy)) * COS(RADIANS(mapx) - RADIANS(%s)) +
                    SIN(RADIANS(%s)) * SIN(RADIANS(mapy))
                )) AS distance
            FROM visit_main_fix
            WHERE mapx IS NOT NULL
            AND mapy IS NOT NULL
            AND firstimage IS NOT NULL
            AND firstimage NOT IN ('', ' ', 'None')
            ORDER BY distance ASC
            LIMIT 1;
        """

    params = (mapy, mapx, mapy)

    # 쿼리 실행
    df = connect_mysql(query, params=params)

    if df.empty:
        raise HTTPException(status_code=404, detail="No tourist spots found.")

    # 가장 가까운 관광지 정보 추출
    nearest_spot = df.iloc[0]
    contentid = nearest_spot['contentid']
    title = nearest_spot['title']
    mapx_insert = nearest_spot['mapx']
    mapy_insert = nearest_spot['mapy']
    address = nearest_spot['address']
    firstimage = nearest_spot['firstimage']
    story = nearest_spot['story']
    distance = nearest_spot['distance']

    # print(f"Nearest Spot: {nearest_spot}")

    # 추천 내역을 추적하기 위한 INSERT 쿼리
    insert_query = f"""
            INSERT INTO user_recommendations (userId, contentid, title, 
            mapx, mapy, address, firstimage, story, recommended_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
    insert_params = (userId, contentid, title, mapx_insert, mapy_insert,
                     address, firstimage, story, datetime.utcnow())

    try:
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
        )
        with connection.cursor() as cursor:
            cursor.execute(insert_query, insert_params)
        connection.commit()
        # print(f"Inserted recommendation: User {userId}, ContentID {contentid}")
    except Exception as e:
        print(f"Error inserting recommendation: {str(e)}")
        # 여기서 에러를 반환하거나, 실패했을 때의 처리 방안을 결정할 수 있습니다.
        raise HTTPException(status_code=500, detail="Failed to record recommendation.")
    finally:
        connection.close()

    # 결과 반환
    return RecommendationOutput(contentid=contentid, title=title)

