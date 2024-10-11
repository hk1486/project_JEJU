from fastapi import FastAPI, HTTPException, APIRouter, status
from datetime import datetime
import pymysql
import os
from pydantic import BaseModel
from typing import List

router = APIRouter()

# MySQL 연결 정보 (기존과 동일)
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
class UpdateCourseInfoRequest(BaseModel):
    userId: int
    courseId: int
    courseName: str
    planning_date: List[str]  # "YYYY-MM-DD" 형식의 날짜 문자열 리스트

@router.put("/update_course_info", status_code=status.HTTP_200_OK)
async def update_course_info(request: UpdateCourseInfoRequest):
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

            # 2. 기존 콘텐츠 가져오기
            fetch_contents_query = """
            SELECT contentId
            FROM course_plans
            WHERE courseId = %s AND contentId IS NOT NULL
            ORDER BY planning_date ASC, sequence ASC
            """
            cursor.execute(fetch_contents_query, (request.courseId,))
            existing_contents = cursor.fetchall()
            content_ids = [row['contentId'] for row in existing_contents]

            # 콘텐츠가 없는 경우
            if not content_ids:
                # 코스 이름 업데이트
                update_course_name_query = """
                UPDATE courses SET courseName = %s WHERE courseId = %s
                """
                cursor.execute(update_course_name_query, (request.courseName, request.courseId))

                # 기존 코스 일정 삭제
                delete_plans_query = """
                DELETE FROM course_plans WHERE courseId = %s
                """
                cursor.execute(delete_plans_query, (request.courseId,))

                # 새로운 날짜 삽입
                insert_plan_query = """
                INSERT INTO course_plans (courseId, planning_date)
                VALUES (%s, %s)
                """
                plan_data = []
                for date_str in request.planning_date:
                    # 날짜 검증 및 변환
                    try:
                        plan_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    except ValueError:
                        raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}")
                    plan_data.append((request.courseId, plan_date))
                cursor.executemany(insert_plan_query, plan_data)

                # 트랜잭션 커밋
                connection.commit()
                return {"message": "Course information updated successfully."}

            # 3. 기존 코스 일정 삭제
            delete_plans_query = """
            DELETE FROM course_plans WHERE courseId = %s
            """
            cursor.execute(delete_plans_query, (request.courseId,))

            # 4. 콘텐츠 재분배
            num_contents = len(content_ids)
            num_dates = len(request.planning_date)

            # 날짜 검증 및 정렬
            valid_dates = []
            for date_str in request.planning_date:
                try:
                    plan_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    valid_dates.append(plan_date)
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}")
            valid_dates.sort()

            # 콘텐츠를 날짜별로 분배
            contents_per_date = [[] for _ in range(num_dates)]
            for idx, content_id in enumerate(content_ids):
                date_index = idx % num_dates
                contents_per_date[date_index].append(content_id)

            # 5. 새로운 코스 일정 삽입
            insert_plan_query = """
            INSERT INTO course_plans (courseId, planning_date, contentId, sequence)
            VALUES (%s, %s, %s, %s)
            """
            plan_data = []
            for date_idx, plan_date in enumerate(valid_dates):
                contents = contents_per_date[date_idx]
                for seq_idx, content_id in enumerate(contents):
                    plan_data.append((
                        request.courseId,
                        plan_date,
                        content_id,
                        seq_idx + 1  # sequence는 1부터 시작
                    ))
                # 해당 날짜에 콘텐츠가 없는 경우
                if not contents:
                    plan_data.append((
                        request.courseId,
                        plan_date,
                        None,
                        None
                    ))
            cursor.executemany(insert_plan_query, plan_data)

            # 6. 코스 이름 업데이트
            update_course_name_query = """
            UPDATE courses SET courseName = %s WHERE courseId = %s
            """
            cursor.execute(update_course_name_query, (request.courseName, request.courseId))

            # 트랜잭션 커밋
            connection.commit()
            return {"message": "Course information and contents updated successfully."}

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