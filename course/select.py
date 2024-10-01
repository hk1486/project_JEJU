from fastapi import FastAPI, HTTPException, APIRouter, status, Query
from datetime import datetime
import pymysql
import os
from pydantic import BaseModel
from typing import Dict, List, Optional

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
        autocommit=False
    )
    return connection

# Pydantic 모델 정의
class CourseInfo(BaseModel):
    courseId: int
    courseName: str
    contentCount: int
    firstimage: str  # Optional[str]에서 str로 변경하여 빈 문자열 반환

@router.get("/select", response_model=List[CourseInfo], status_code=status.HTTP_200_OK)
async def get_courses(userId: int = Query(..., description="User ID")):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. 해당 사용자의 모든 코스 조회
            get_courses_query = """
            SELECT courseId, courseName
            FROM courses
            WHERE userId = %s
            """
            cursor.execute(get_courses_query, (userId,))
            courses = cursor.fetchall()

            if not courses:
                return []  # 코스가 없으면 빈 리스트 반환

            course_list = []
            for course in courses:
                course_id = course['courseId']
                course_name = course['courseName']

                # 2. 해당 코스에 포함된 contentId의 개수 조회
                count_query = """
                SELECT COUNT(*) as contentCount
                FROM course_plans
                WHERE courseId = %s AND contentId IS NOT NULL
                """
                cursor.execute(count_query, (course_id,))
                count_result = cursor.fetchone()
                content_count = count_result['contentCount'] if count_result else 0

                # 3. 해당 코스의 첫 번째 contentId 가져오기
                first_content_query = """
                SELECT contentId
                FROM course_plans
                WHERE courseId = %s AND contentId IS NOT NULL
                ORDER BY planning_date ASC, sequence ASC
                LIMIT 1
                """
                cursor.execute(first_content_query, (course_id,))
                first_content = cursor.fetchone()

                first_image = ""
                if first_content and first_content['contentId']:
                    content_id = first_content['contentId']
                    # 4. main_total_v2 테이블에서 target_table 가져오기
                    cursor.execute("SELECT target_table FROM main_total_v2 WHERE contentsid = %s", (content_id,))
                    target_result = cursor.fetchone()
                    if target_result and 'target_table' in target_result:
                        target_table = target_result['target_table']
                        # 5. 해당 target_table에서 firstimage 가져오기
                        allowed_tables = ['visit_main_fix', 'festival_main', 'stay_main',
                                          'culture_main', 'food_main', 'leports_main', 'shopping_main']
                        if target_table in allowed_tables:
                            image_query = f"""
                            SELECT firstimage
                            FROM {target_table}
                            WHERE contentid = %s
                            """
                            cursor.execute(image_query, (content_id,))
                            image_result = cursor.fetchone()
                            if image_result and image_result['firstimage']:
                                first_image = image_result['firstimage']
                            else:
                                first_image = ""
                    else:
                        first_image = ""
                else:
                    first_image = ""

                # 결과 추가
                course_info = CourseInfo(
                    courseId=course_id,
                    courseName=course_name,
                    contentCount=content_count,
                    firstimage=first_image
                )
                course_list.append(course_info)

            return course_list

    except pymysql.MySQLError as err:
        if connection:
            connection.rollback()
        print(f"Database Error: {err}")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        if connection:
            connection.rollback()
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        if connection and connection.open:
            connection.close()