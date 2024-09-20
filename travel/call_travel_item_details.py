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


def connect_mysql(query):
    try:
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        # 쿼리를 실행하여 데이터를 가져오기
        df = pd.read_sql(query, connection)
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
    WHERE cat3 = '{category}'  -- 카테고리 값을 문자열로 취급
    AND contentid != {contentid}
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
            df = pd.read_sql(recomm_query, connection)

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
async def read_main_items(contentid: int):
    """
    contentid를 인자로 받아 DB에서 정보를 조회한 후 JSON 응답으로 반환
    """
    try:
        query = f"""SELECT target_table 
                    FROM main_total_v2 
                    WHERE contentsid = {contentid}"""

        df_target_table = connect_mysql(query)

        target_table = df_target_table['target_table'].values[0]

        detail_info_query = f"""SELECT * 
                                FROM {target_table}
                                WHERE contentid = {contentid}"""

        df_detail = connect_mysql(detail_info_query)

        df_detail = df_detail.replace({'': np.nan, ' ': np.nan})
        df_detail['cat2'] = target_table

        # 예시로 호출
        table_name = 'pet_total'
        column_name = 'contentid'

        # 함수 호출
        df_pet_target_table = get_info_by_id(table_name, column_name, contentid)

        if df_pet_target_table is not None and not df_pet_target_table.empty:
            pet_target_table = df_pet_target_table['target_table'].values[0]

            get_pet_info = f"""SELECT * 
                                FROM {pet_target_table} 
                                WHERE contentid = {contentid}"""

            df_pet = connect_mysql(get_pet_info)

            df_pet = df_pet.replace({'': np.nan, ' ': np.nan})

            df_detail = df_detail.merge(df_pet, on='contentid')

        category = df_detail['cat3'].values[0]
        recommend_result = get_random_rows(target_table, category, contentid)

        json_output = {
            "result": json.loads(df_detail.to_json(orient='records', force_ascii=False)),
            "recommend": recommend_result
        }

        return JSONResponse(content=json_output)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error occurred: {str(e)}")
