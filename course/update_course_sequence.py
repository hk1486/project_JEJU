from fastapi import FastAPI, HTTPException, APIRouter, status
from datetime import datetime
import pymysql
import os
from pydantic import BaseModel
from typing import List, Dict

router = APIRouter()

# MySQL 연결 정보
MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', '3306'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

def get_db_connection():
    connection = pymysql.connect(
        host=MYSQL_HOSTNAME,
        port=MYSQL_PORT,
        user=MYSQL_USERNAME,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False  # 트랜잭션 관리
    )
    return connection

# 요청 모델 정의
class PlanItem(BaseModel):
    date: str  # "YYYY-MM-DD" 형식
    contentid_list: List[int]

class UpdateCoursePlanRequest(BaseModel):
    userId: int
    courseId: int
    plan: List[PlanItem]

@router.put("/update_course_plan", status_code=status.HTTP_200_OK)
async def update_course_plan(request: UpdateCoursePlanRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. 코스 소유권 확인
            check_course_query = """
            SELECT * FROM courses WHERE courseId = %s AND userId = %s
            """
            cursor.execute(check_course_query, (request.courseId, request.userId))
            course = cursor.fetchone()
            if not course:
                raise HTTPException(status_code=404, detail="Course not found or does not belong to the user.")

            # 2. 기존 콘텐츠 ID 수집 (해당 코스의 모든 contentId)
            existing_content_query = """
            SELECT contentId FROM course_plans
            WHERE courseId = %s AND contentId IS NOT NULL
            """
            cursor.execute(existing_content_query, (request.courseId,))
            existing_contents = cursor.fetchall()
            existing_content_ids = set([row['contentId'] for row in existing_contents])

            # 3. 새로운 콘텐츠 ID 수집 (요청으로부터)
            new_content_ids = set()
            for plan_item in request.plan:
                new_content_ids.update(plan_item.contentid_list)

            # 4. 추가된 콘텐츠와 제거된 콘텐츠 계산
            content_ids_to_add = new_content_ids - existing_content_ids
            content_ids_to_remove = existing_content_ids - new_content_ids

            # 5. plan_count 업데이트 (제거된 콘텐츠는 감소, 추가된 콘텐츠는 증가)
            allowed_tables = ['visit_main_fix', 'festival_main', 'stay_main',
                              'culture_main', 'food_main', 'leports_main', 'shopping_main']

            # 제거된 콘텐츠에 대해 plan_count 감소
            for content_id in content_ids_to_remove:
                cursor.execute("SELECT target_table FROM main_total_v2 WHERE contentsid = %s", (content_id,))
                target_result = cursor.fetchone()
                if target_result and 'target_table' in target_result:
                    target_table = target_result['target_table']
                else:
                    continue  # 대상 테이블을 찾을 수 없으면 건너뜀

                if target_table not in allowed_tables:
                    continue  # 허용되지 않은 테이블이면 건너뜀

                update_query = f"""
                UPDATE {target_table}
                SET plan_count = GREATEST(COALESCE(plan_count, 1) - 1, 0)
                WHERE contentid = %s
                """
                cursor.execute(update_query, (content_id,))

            # 추가된 콘텐츠에 대해 plan_count 증가
            for content_id in content_ids_to_add:
                cursor.execute("SELECT target_table FROM main_total_v2 WHERE contentsid = %s", (content_id,))
                target_result = cursor.fetchone()
                if target_result and 'target_table' in target_result:
                    target_table = target_result['target_table']
                else:
                    continue  # 대상 테이블을 찾을 수 없으면 건너뜀

                if target_table not in allowed_tables:
                    continue  # 허용되지 않은 테이블이면 건너뜀

                update_query = f"""
                UPDATE {target_table}
                SET plan_count = COALESCE(plan_count, 0) + 1
                WHERE contentid = %s
                """
                cursor.execute(update_query, (content_id,))

            # 6. 기존의 course_plans 삭제
            delete_plans_query = """
            DELETE FROM course_plans WHERE courseId = %s
            """
            cursor.execute(delete_plans_query, (request.courseId,))

            # 7. 새로운 course_plans 삽입
            insert_plan_query = """
            INSERT INTO course_plans (courseId, planning_date, contentId, sequence)
            VALUES (%s, %s, %s, %s)
            """
            plan_data = []
            for plan_item in request.plan:
                date_str = plan_item.date
                content_ids = plan_item.contentid_list
                # 날짜 검증 및 변환
                try:
                    plan_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}")

                if content_ids:
                    for seq_idx, content_id in enumerate(content_ids):
                        plan_data.append((
                            request.courseId,
                            plan_date,
                            content_id,
                            seq_idx + 1  # sequence는 1부터 시작
                        ))
                else:
                    # 콘텐츠가 없는 날짜도 저장
                    plan_data.append((
                        request.courseId,
                        plan_date,
                        None,
                        None
                    ))
            if plan_data:
                cursor.executemany(insert_plan_query, plan_data)

            # 8. 트랜잭션 커밋
            connection.commit()

            return {"message": "Course plan updated successfully."}

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