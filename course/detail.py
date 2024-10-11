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

# 요청 모델 정의
class GetCourseDetailsRequest(BaseModel):
    userId: int
    courseId: int

# 응답 모델 정의
class TouristItem(BaseModel):
    contentId: int
    firstimage: str
    title: str
    cat3: str
    address: str
    mapx: Optional[float]
    mapy: Optional[float]

class DatePlan(BaseModel):
    date: str
    contents: List[TouristItem]

class GetCourseDetailsResponse(BaseModel):
    courseName: str
    totalDays: int
    totalItems: int
    plans: List[DatePlan]

@router.post("/details", response_model=GetCourseDetailsResponse, status_code=status.HTTP_200_OK)
async def get_course_details(request: GetCourseDetailsRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. 코스가 존재하고 해당 사용자 소유인지 확인하고 코스 이름 가져오기
            check_course_query = """
            SELECT * FROM courses WHERE courseId = %s AND userId = %s
            """
            cursor.execute(check_course_query, (request.courseId, request.userId))
            course = cursor.fetchone()
            if not course:
                raise HTTPException(status_code=404, detail="Course not found or does not belong to the user.")

            # 코스 이름 가져오기
            course_name = course.get('courseName') or course.get('coursename') or course.get('course_name')
            if not course_name:
                raise HTTPException(status_code=500, detail="Course name not found.")

            # 2. 여행 일수 및 관광 아이템 수 계산
            get_plans_query = """
            SELECT planning_date, contentId, sequence
            FROM course_plans
            WHERE courseId = %s
            ORDER BY planning_date ASC, sequence ASC
            """
            cursor.execute(get_plans_query, (request.courseId,))
            plans = cursor.fetchall()
            if not plans:
                raise HTTPException(status_code=404, detail="No plans found for this course.")

            # 여행 일수 계산 (고유한 planning_date의 수)
            unique_dates = sorted(set(plan['planning_date'] for plan in plans))
            total_days = len(unique_dates)

            # 관광 아이템 수 계산 (고유한 contentId의 수)
            unique_content_ids = set(plan['contentId'] for plan in plans if plan['contentId'])
            total_items = len(unique_content_ids)

            # 3. 날짜별 콘텐츠 리스트 구성
            date_plans = []
            for date in unique_dates:
                # 해당 날짜의 콘텐츠 가져오기
                date_contents = [plan for plan in plans if plan['planning_date'] == date]
                # sequence가 없으면 순서대로, 있으면 sequence 순으로 정렬
                date_contents.sort(key=lambda x: x['sequence'] if x['sequence'] is not None else 0)

                # 콘텐츠 상세 정보 수집
                contents = []
                for item in date_contents:
                    content_id = item['contentId']
                    if content_id is None:
                        continue  # contentId가 없는 경우 건너뜀

                    # 4. 콘텐츠 상세 정보 조회
                    # main_total_v2에서 target_table 가져오기
                    cursor.execute("SELECT target_table FROM main_total_v2 WHERE contentsid = %s", (content_id,))
                    target_result = cursor.fetchone()
                    if not target_result or 'target_table' not in target_result:
                        continue  # target_table이 없으면 건너뜀

                    target_table = target_result['target_table']
                    # 허용된 테이블 목록
                    allowed_tables = ['visit_main_fix', 'festival_main', 'stay_main',
                                      'culture_main', 'food_main', 'leports_main', 'shopping_main']
                    if target_table not in allowed_tables:
                        continue  # 허용되지 않은 테이블이면 건너뜀

                    # 상세 정보 조회
                    detail_query = f"""
                    SELECT contentid, firstimage, title, cat3, address, mapx, mapy
                    FROM {target_table}
                    WHERE contentid = %s
                    """
                    cursor.execute(detail_query, (content_id,))
                    detail = cursor.fetchone()
                    if not detail:
                        continue  # 상세 정보가 없으면 건너뜀

                    # TouristItem 객체 생성
                    tourist_item = TouristItem(
                        contentId=detail['contentid'],
                        firstimage=detail.get('firstimage', ''),
                        title=detail.get('title', ''),
                        cat3=detail.get('cat3', ''),
                        address=detail.get('address', ''),
                        mapx=detail.get('mapx'),
                        mapy=detail.get('mapy')
                    )
                    contents.append(tourist_item)

                # DatePlan 객체 생성
                date_plan = DatePlan(
                    date=date.strftime("%Y-%m-%d"),
                    contents=contents
                )
                date_plans.append(date_plan)

            # 5. 응답 반환
            response = GetCourseDetailsResponse(
                courseName=course_name,
                totalDays=total_days,
                totalItems=total_items,
                plans=date_plans
            )
            return response

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