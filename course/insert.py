from pydantic import BaseModel
from typing import List
from fastapi import FastAPI, HTTPException, APIRouter, status, Query
from datetime import datetime, timedelta
import pymysql
import os
from typing import List

class AddToCourseRequest(BaseModel):
    userId: int
    courseId: int
    contentIds: List[int]

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

router = APIRouter()


@router.post("/add_to_course", status_code=status.HTTP_200_OK)
async def add_to_course(request: AddToCourseRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. 코스가 존재하고 해당 사용자 소유인지 확인
            check_course_query = """
            SELECT * FROM courses WHERE courseId = %s AND userId = %s
            """
            cursor.execute(check_course_query, (request.courseId, request.userId))
            course = cursor.fetchone()
            if not course:
                raise HTTPException(status_code=404, detail="Course not found or does not belong to the user.")

            # 코스 이름 가져오기
            course_title = course['courseName']

            # 1-1. 중복된 contentId가 있는지 확인
            existing_content_query = """
                        SELECT contentId FROM course_plans
                        WHERE courseId = %s AND contentId IS NOT NULL
                        """
            cursor.execute(existing_content_query, (request.courseId,))
            existing_contents = cursor.fetchall()
            existing_content_ids = set([row['contentId'] for row in existing_contents])

            # 요청된 contentIds와 기존 contentIds의 교집합 찾기
            duplicate_content_ids = existing_content_ids.intersection(set(request.contentIds))
            if duplicate_content_ids:
                # 중복된 경우 메시지에 '중복'이라고 반환
                return {"message": "중복"}

            # 2. 해당 코스의 날짜 목록 가져오기 (planning_date 기준으로 오름차순)
            get_course_dates_query = """
            SELECT DISTINCT planning_date
            FROM course_plans
            WHERE courseId = %s
            ORDER BY planning_date ASC
            """
            cursor.execute(get_course_dates_query, (request.courseId,))
            course_dates = [row['planning_date'] for row in cursor.fetchall()]

            # 3. 각 날짜별로 빈 슬롯과 총 슬롯 수를 가져오기
            date_slots = {}
            for date in course_dates:
                get_slots_query = """
                SELECT planId, contentId
                FROM course_plans
                WHERE courseId = %s AND planning_date = %s
                ORDER BY sequence ASC
                """
                cursor.execute(get_slots_query, (request.courseId, date))
                slots = cursor.fetchall()
                empty_slots = [slot for slot in slots if slot['contentId'] is None]
                date_slots[date] = {
                    'empty_slots': empty_slots,
                    'total_slots': slots,
                }

            # 4. 추가할 contentIds를 날짜별로 할당
            content_ids_iter = iter(request.contentIds)
            content_ids_set = set()
            for date in course_dates:
                slots_info = date_slots[date]
                empty_slots = slots_info['empty_slots']

                # 빈 슬롯에 채우기
                for slot in empty_slots:
                    try:
                        content_id = next(content_ids_iter)
                        update_slot_query = """
                        UPDATE course_plans
                        SET contentId = %s
                        WHERE planId = %s
                        """
                        cursor.execute(update_slot_query, (content_id, slot['planId']))
                        content_ids_set.add(content_id)
                    except StopIteration:
                        break  # contentIds를 모두 사용한 경우 루프 종료

            # 5. 남은 contentIds를 날짜별로 삽입
            for date in course_dates:
                while True:
                    try:
                        content_id = next(content_ids_iter)
                        # 해당 날짜에 새로운 sequence 계산
                        get_max_sequence_query = """
                        SELECT MAX(sequence) as max_sequence
                        FROM course_plans
                        WHERE courseId = %s AND planning_date = %s
                        """
                        cursor.execute(get_max_sequence_query, (request.courseId, date))
                        max_seq_result = cursor.fetchone()
                        next_sequence = (max_seq_result['max_sequence'] or 0) + 1

                        # 새로운 레코드 삽입
                        insert_plan_query = """
                        INSERT INTO course_plans (courseId, planning_date, contentId, sequence)
                        VALUES (%s, %s, %s, %s)
                        """
                        cursor.execute(insert_plan_query, (
                            request.courseId,
                            date,
                            content_id,
                            next_sequence
                        ))
                        content_ids_set.add(content_id)
                    except StopIteration:
                        break  # contentIds를 모두 사용한 경우 루프 종료

            # 6. 아직 남은 contentIds가 있다면, 마지막 날짜에 새로운 날짜를 추가하여 삽입
            while True:
                try:
                    content_id = next(content_ids_iter)
                    # 마지막 날짜의 다음 날짜 계산
                    if course_dates:
                        last_date = course_dates[-1] + timedelta(days=1)
                    else:
                        last_date = datetime.today().date()

                    # 새로운 레코드 삽입
                    insert_plan_query = """
                    INSERT INTO course_plans (courseId, planning_date, contentId, sequence)
                    VALUES (%s, %s, %s, %s)
                    """
                    cursor.execute(insert_plan_query, (
                        request.courseId,
                        last_date,
                        content_id,
                        1  # sequence 시작값
                    ))
                    content_ids_set.add(content_id)
                    course_dates.append(last_date)  # 새로운 날짜 추가
                except StopIteration:
                    break  # contentIds를 모두 사용한 경우 루프 종료

            # 7. 각 contentId에 대해 plan_count 증가
            allowed_tables = ['visit_main_fix', 'festival_main', 'stay_main',
                              'culture_main', 'food_main', 'leports_main', 'shopping_main']
            for content_id in content_ids_set:
                # 대상 테이블 이름 가져오기
                cursor.execute("SELECT target_table FROM main_total_v2 WHERE contentsid = %s", (content_id,))
                target_result = cursor.fetchone()

                if target_result and 'target_table' in target_result:
                    target_table = target_result['target_table']
                else:
                    raise HTTPException(status_code=400, detail=f"Content ID {content_id} not found in main_total_v2")

                # 허용된 테이블인지 확인
                if target_table not in allowed_tables:
                    raise HTTPException(status_code=400, detail=f"Invalid target table for content ID {content_id}")

                # plan_count 증가
                update_query = f"""
                UPDATE {target_table}
                SET plan_count = COALESCE(plan_count, 0) + 1
                WHERE contentid = %s
                """
                cursor.execute(update_query, (content_id,))

            # 8. 트랜잭션 커밋
            connection.commit()

            return {"message": f"{course_title}"}

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