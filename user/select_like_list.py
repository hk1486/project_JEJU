from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
import os
import pymysql
from typing import List, Dict, Any
import json

load_dotenv()

router = APIRouter()

# MySQL 연결 정보 (기존과 동일)
MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')


# 데이터베이스 연결 함수 (기존과 동일)
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


# 좋아요한 콘텐츠 상세 정보 조회 엔드포인트
@router.get("/user_likes/{user_id}")
async def get_user_liked_contents(user_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. 해당 사용자가 좋아요한 contentId 가져오기
            likes_query = """
            SELECT contentId, likedAt
            FROM likes
            WHERE userId = %s
            ORDER BY likedAt DESC
            """
            cursor.execute(likes_query, (user_id,))
            liked_contents = cursor.fetchall()

            if not liked_contents:
                return {"message": "No liked contents found for this user", "data": []}

            result_data = []

            # 2. 각 contentId에 대해 처리
            for content in liked_contents:
                content_id = content['contentId']
                liked_at = content['likedAt']

                # 2. main_total_v2에서 target_table 조회
                target_table_query = """
                SELECT target_table
                FROM main_total_v2
                WHERE contentsid = %s
                """
                cursor.execute(target_table_query, (content_id,))
                target_table_result = cursor.fetchone()

                if target_table_result and 'target_table' in target_table_result:
                    target_table = target_table_result['target_table']
                else:
                    continue  # 해당 contentId에 대한 target_table이 없으면 다음으로 넘어감

                # 3. 허용된 테이블인지 검증
                allowed_tables = ['visit_main_fix', 'festival_main', 'stay_main',
                                  'culture_main', 'food_main', 'leports_main', 'shopping_main']
                if target_table not in allowed_tables:
                    continue  # 허용되지 않은 테이블이면 건너뜀

                # 4. 해당 target_table에서 데이터 조회
                content_query = f"""
                SELECT contentid, firstimage, title, address, cat2, cat3
                FROM {target_table}
                WHERE contentid = %s
                """
                cursor.execute(content_query, (content_id,))
                content_info = cursor.fetchone()

                if content_info:
                    # likedAt 추가
                    content_info['likedAt'] = liked_at
                    result_data.append(content_info)

            return {"message": "Success", "data": result_data}

    except pymysql.MySQLError as err:
        print(f"Database Error: {err}")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        connection.close()