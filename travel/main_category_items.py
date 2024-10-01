from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import JSONResponse
import os
import pymysql
import pandas as pd
import json
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")

load_dotenv()

router = APIRouter()

MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')


def connect_mysql(query, params=None):
    try:
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        print(f"Executing query: {query} with params: {params}")
        df = pd.read_sql(query, connection, params=params)
        print(f"DataFrame head:\n{df.head()}")  # 데이터 확인용 로그
        return df

    except Exception as e:
        print(f"Error: {str(e)}")
        return pd.DataFrame()

    finally:
        connection.close()


category_mapping = {
    'nature': '자연 관광지',
    'experience': '체험 관광지',
    'history': '역사 관광지',
    'recreation': '휴양 관광지',
    'industry': '산업 관광지',
    'sculpture': '건축/조형물',
    'culture': '문화시설'
}

# 카테고리와 테이블 이름 매핑
category_table_mapping = {
    'nature': 'visit_main_fix',
    'experience': 'visit_main_fix',
    'history': 'visit_main_fix',
    'recreation': 'visit_main_fix',
    'industry': 'visit_main_fix',
    'sculpture': 'visit_main_fix',
    'culture': 'culture_main'
}


@router.get("/categories/{category_name}")
async def get_tourist_spots_by_category(category_name: str):

    # 카테고리 이름이 올바른지 확인
    if category_name not in category_table_mapping:
        raise HTTPException(status_code=400, detail="Invalid category name")

    # 해당 카테고리에 대한 테이블 이름 가져오기
    table_name = category_table_mapping[category_name]

    # 해당 카테고리에 대한 cat2 조건 가져오기
    cat2_name = category_mapping[category_name]

    # 해당 테이블의 모든 데이터 조회
    query = f"""SELECT cat2, cat3, contentid, firstimage, IFNULL(firstimage2, '') AS firstimage2, mapx, mapy, title, address, sigungucode
                FROM {table_name} 
                WHERE cat2 = %s
                AND firstimage IS NOT NULL
                AND firstimage not in ('', ' ', 'None')
                ORDER BY RAND();"""

    df = connect_mysql(query, params=(cat2_name,))
    if df.empty:
        return JSONResponse(content={"result": []})

    # 데이터프레임을 JSON 형태로 변환
    json_output = {
        "result": df.to_dict(orient='records')
    }

    return JSONResponse(content=json_output)