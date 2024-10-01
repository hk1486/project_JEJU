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



def get_random_rows(target_table, category, contentid, user_id):
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
                content_ids = df['contentid'].tolist()

                # 좋아요 상태를 가져오는 쿼리
                like_query = """
                                   SELECT contentId
                                   FROM likes
                                   WHERE userId = %s AND contentId IN %s
                               """

                # IN 연산자를 사용하기 위해 튜플 형태로 변환
                content_ids_tuple = tuple(content_ids)
                if len(content_ids_tuple) == 1:
                    content_ids_tuple += (None,)  # 단일 요소 튜플일 경우 콤마 추가

                # 좋아요 상태를 가져옴
                df_likes = pd.read_sql(like_query, connection, params=(user_id, content_ids_tuple))

                # 좋아요 상태를 표시하기 위한 컬럼 추가
                df['is_liked'] = df['contentid'].isin(df_likes['contentId'])

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

        # stay_main일 경우 추가 정보 가져오기
        if target_table == 'stay_main':
            stay_info_query = """
                    SELECT roomoffseasonminfee1
                    FROM stay_info
                    WHERE contentid = %s
                    """
            df_stay_info = connect_mysql(stay_info_query, params=(contentid,))

            if not df_stay_info.empty:
                # roomoffseasonminfee1 컬럼을 숫자형으로 변환
                df_stay_info['roomoffseasonminfee1'] = pd.to_numeric(
                    df_stay_info['roomoffseasonminfee1'], errors='coerce'
                )

                # 0과 NaN 값을 제외한 값들로 필터링
                fees_nonzero = df_stay_info['roomoffseasonminfee1'][
                    (df_stay_info['roomoffseasonminfee1'] != 0) & (~df_stay_info['roomoffseasonminfee1'].isna())
                    ]

                if not fees_nonzero.empty:
                    # 최소값 구하기
                    min_fee = fees_nonzero.min()
                    df_detail['roomoffseasonminfee1'] = min_fee
                else:
                    # 모든 값이 0 또는 NaN인 경우
                    df_detail['roomoffseasonminfee1'] = np.nan
            else:
                df_detail['roomoffseasonminfee1'] = np.nan


        # 3. 펫 정보 확인 및 병합
        table_name = 'pet_total'
        column_name = 'contentid'

        df_pet_target_table = get_info_by_id(table_name, column_name, contentid)

        # df_pet 변수 초기화
        df_pet = None

        if df_pet_target_table is not None and not df_pet_target_table.empty:
            pet_target_table = df_pet_target_table['target_table'].values[0]

            get_pet_info = f"""SELECT * 
                                   FROM {pet_target_table} 
                                   WHERE contentid = %s"""
            df_pet = connect_mysql(get_pet_info, params=(contentid,))

            df_pet = df_pet.replace({'': np.nan, ' ': np.nan})

            # df_detail = df_detail.merge(df_pet, on='contentid', how='left')

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
        recommend_result = get_random_rows(target_table, category, contentid, user_id)

        # 6. 응답 생성
        if df_pet is not None and not df_pet.empty:
            pet_result = json.loads(df_pet.to_json(orient='records', force_ascii=False))
        else:
            pet_result = None

        json_output = {
            "result": json.loads(df_detail.to_json(orient='records', force_ascii=False)),
            "pet": pet_result,
            "is_liked": is_liked,
            "recommend": recommend_result
        }

        return JSONResponse(content=json_output)

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error occurred: {str(e)}")