from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import JSONResponse
import os
from sshtunnel import SSHTunnelForwarder
import pymysql
import numpy as np
import pandas as pd
import requests
from copy import deepcopy
import json
import ast

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
        # 쿼리를 실행하여 데이터를 가져오기
        df = pd.read_sql(query, connection, params=params)
        return df

    except Exception as e:
        print(f"Error: {str(e)}")
        return pd.DataFrame()  # 오류 발생 시 빈 DataFrame 반환

    finally:
        connection.close()

def get_info_by_id(table, column, search_id):
    query = f"SELECT * FROM {table} WHERE {column} = %s"

    try:
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        # 쿼리 실행하여 해당 ID가 있는지 확인
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {column} = %s)", (search_id,))
            exists = cursor.fetchone()[0]

            if exists:
                # 해당 ID가 있을 경우 데이터를 조회
                df = pd.read_sql(query, connection, params=(search_id,))
                return df
            else:
                return None
    except Exception as e:
        print(f"Error: {e}")
        return None



def get_random_rows(target_table, category, contentid):
    recomm_query = f"""
    SELECT contentid, title, cat3, address, firstimage
    FROM {target_table}
    WHERE cat3 = %s
    AND contentid != %s
    ORDER BY RAND()
    LIMIT 5;
    """

    try:
        # MySQL에 직접 연결
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )

        try:
            # 쿼리를 실행하고 DataFrame으로 반환
            df = pd.read_sql(recomm_query, connection, params=(category, contentid))

            # JSON 응답 생성
            if df.empty:
                # 결과가 없으면 None 반환
                json_output = {"result": None}
            else:
                # 결과가 있으면 DataFrame을 JSON으로 변환
                json_output = {
                    "result": json.loads(df.to_json(orient='records', force_ascii=False))
                }

            return json_output

        except Exception as e:
            print(f"Error executing query: {str(e)}")
            return {"result": None}

        finally:
            # MySQL 연결 해제
            connection.close()

    except Exception as e:
        print(f"Error connecting to MySQL: {str(e)}")
        return {"result": None}

@router.get("/details/{contentid}")
async def read_main_items(contentid: int, user_id: int):
    """
    contentid와 user_id를 인자로 받아 DB에서 정보를 조회한 후 JSON 응답으로 반환
    """
    try:
        # 1. 대상 테이블 이름 가져오기
        query = """SELECT target_table 
                       FROM main_total_v2 
                       WHERE contentsid = %s"""
        df_target_table = connect_mysql(query, params=(contentid,))

        if df_target_table.empty:
            raise HTTPException(status_code=404, detail="Content not found")

        target_table = df_target_table['target_table'].values[0]

        # 2. 세부 정보 가져오기
        detail_info_query = f"""SELECT * 
                                    FROM {target_table}
                                    WHERE contentid = %s"""
        df_detail = connect_mysql(detail_info_query, params=(contentid,))

        if df_detail.empty:
            raise HTTPException(status_code=404, detail="Content details not found")

        df_detail = df_detail.replace({'': np.nan, ' ': np.nan})
        df_detail['cat2'] = target_table

        # 3. 펫 정보 확인 및 병합
        table_name = 'pet_total'
        column_name = 'contentid'

        df_pet_target_table = get_info_by_id(table_name, column_name, contentid)

        if df_pet_target_table is not None and not df_pet_target_table.empty:
            pet_target_table = df_pet_target_table['target_table'].values[0]

            get_pet_info = f"""SELECT * 
                                   FROM {pet_target_table} 
                                   WHERE contentid = %s"""
            df_pet = connect_mysql(get_pet_info, params=(contentid,))

            df_pet = df_pet.replace({'': np.nan, ' ': np.nan})

            df_detail = df_detail.merge(df_pet, on='contentid', how='left')

        # 4. 좋아요 상태 확인
        like_check_query = """
                SELECT EXISTS(
                    SELECT 1 FROM likes
                    WHERE userId = %s AND contentId = %s
                ) AS is_liked
                """
        df_like = connect_mysql(like_check_query, params=(user_id, contentid))

        is_liked = bool(df_like['is_liked'].values[0])

        # 5. 추천 정보 가져오기
        category = df_detail['cat3'].values[0]
        recommend_result = get_random_rows(target_table, category, contentid)

        # 6. 응답 생성
        json_output = {
            "result": json.loads(df_detail.to_json(orient='records', force_ascii=False)),
            "is_liked": is_liked,
            "recommend": recommend_result
        }

        return JSONResponse(content=json_output)

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error occurred: {str(e)}")