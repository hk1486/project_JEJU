from fastapi import FastAPI, HTTPException, APIRouter, status
from datetime import datetime
import pymysql
import os
from pydantic import BaseModel
from typing import Dict, List, Optional

router = APIRouter()

# MySQL 연결 정보
MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

# 데이터베이스 연결 함수
def get_db_connection():
    connection = pymysql.connect(
        host=MYSQL_HOSTNAME,
        port=MYSQL_PORT,
        user=MYSQL_USERNAME,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False  # 트랜잭션 관리 위해 자동 커밋 비활성화
    )
    return connection

class PlanItem(BaseModel):
    date: str
    contentid_list: List[int]

class CreateCourseRequest(BaseModel):
    userId: int
    plan: List[PlanItem]

class CreateCourseResponse(BaseModel):
    courseId: int
    courseName: str
    message: str

@router.post("/create", response_model=CreateCourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(request: CreateCourseRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. 해당 사용자의 기존 코스 수 확인
            count_query = """
            SELECT COUNT(*) as course_count FROM courses WHERE userId = %s
            """
            cursor.execute(count_query, (request.userId,))
            result = cursor.fetchone()
            course_number = result['course_count'] + 1

            # 2. 코스 이름 생성 (예: '내 코스-1')
            course_name = f"내 코스-{course_number}"

            # 3. 코스 정보 삽입
            insert_course_query = """
            INSERT INTO courses (userId, courseName)
            VALUES (%s, %s)
            """
            cursor.execute(insert_course_query, (
                request.userId,
                course_name
            ))
            # 생성된 course_id 가져오기
            course_id = cursor.lastrowid

            # 4. 코스 일정 정보 삽입 및 plan_count 업데이트를 위한 content_id 수집
            insert_plan_query = """
            INSERT INTO course_plans (courseId, planning_date, contentId, sequence)
            VALUES (%s, %s, %s, %s)
            """
            plan_data = []
            content_ids_set = set()  # 중복된 content_id 처리를 방지하기 위해 집합 사용

            for plan_item in request.plan:
                date_str = plan_item.date
                content_ids = plan_item.contentid_list
                # 날짜 문자열을 DATE 타입으로 변환
                plan_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if content_ids:
                    for idx, content_id in enumerate(content_ids):
                        plan_data.append((
                            course_id,
                            plan_date,
                            content_id,
                            idx + 1  # sequence는 1부터 시작
                        ))
                        content_ids_set.add(content_id)
                else:
                    # content_ids가 비어있는 경우 content_id와 sequence를 NULL로 저장
                    plan_data.append((
                        course_id,
                        plan_date,
                        None,
                        None
                    ))
            # 데이터 삽입
            cursor.executemany(insert_plan_query, plan_data)

            # 5. 각 content_id에 대해 plan_count 증가
            allowed_tables = ['visit_main_fix', 'festival_main', 'stay_main',
                              'culture_main', 'food_main', 'leports_main', 'shopping_main']
            for content_id in content_ids_set:
                # 대상 테이블 이름 가져오기
                cursor.execute("SELECT target_table FROM main_total_v2 WHERE contentsid = %s", (content_id,))
                result = cursor.fetchone()

                if result and 'target_table' in result:
                    target_table = result['target_table']
                else:
                    raise HTTPException(status_code=400, detail=f"Content ID {content_id} not found in main_total_v2")

                # 허용된 테이블 이름인지 검증
                if target_table not in allowed_tables:
                    raise HTTPException(status_code=400, detail=f"Invalid target table for content ID {content_id}")

                # plan_count 필드 증가
                update_query = f"""
                UPDATE {target_table}
                SET plan_count = COALESCE(plan_count, 0) + 1
                WHERE contentid = %s
                """
                cursor.execute(update_query, (content_id,))

            # 6. 트랜잭션 커밋
            connection.commit()

            return CreateCourseResponse(
                courseId=course_id,
                courseName=course_name,
                message="Course created successfully."
            )

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