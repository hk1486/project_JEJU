from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
import os
import pymysql
import warnings
warnings.filterwarnings('ignore')

load_dotenv()

router = APIRouter()

# MySQL 연결 정보
MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')


# Pydantic 모델 정의
class LikeRequest(BaseModel):
    userId: int
    contentId: int


# 데이터베이스 연결 함수
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


# 좋아요 생성 엔드포인트
@router.post("/like")
async def like_destination(like: LikeRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 중복 좋아요 체크
            check_query = """
            SELECT COUNT(*) as count FROM likes
            WHERE userId = %s AND contentId = %s
            """
            cursor.execute(check_query, (like.userId, like.contentId))
            result = cursor.fetchone()

            if result['count'] > 0:
                raise HTTPException(status_code=400, detail="Already liked")

            # 좋아요 삽입
            insert_query = """
            INSERT INTO likes (userId, contentId)
            VALUES (%s, %s)
            """
            cursor.execute(insert_query, (like.userId, like.contentId))

            # 대상 테이블 이름 가져오기
            cursor.execute("SELECT target_table FROM main_total_v2 WHERE contentsid = %s", (like.contentId,))
            result = cursor.fetchone()

            if result and 'target_table' in result:
                target_table = result['target_table']
            else:
                raise HTTPException(status_code=400, detail="Content ID not found")

            # 허용된 테이블 이름인지 검증
            allowed_tables = ['visit_main_fix', 'festival_main', 'stay_main',
                              'culture_main', 'food_main', 'leports_main', 'shopping_main']  # 실제 테이블 이름으로 대체하세요.
            if target_table not in allowed_tables:
                raise HTTPException(status_code=400, detail="Invalid target table")

            # 좋아요 수 업데이트
            update_query = f"""
            UPDATE {target_table}
            SET like_count = like_count + 1
            WHERE contentid = %s
            """
            cursor.execute(update_query, (like.contentId,))

        return {"message": "Destination liked successfully"}
    except pymysql.MySQLError as err:
        print(f"Database Error: {err}")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        connection.close()


# 좋아요 취소 엔드포인트
@router.delete("/like")
async def unlike_destination(like: LikeRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 좋아요 존재 여부 확인
            check_query = """
            SELECT COUNT(*) as count FROM likes
            WHERE userId = %s AND contentId = %s
            """
            cursor.execute(check_query, (like.userId, like.contentId))
            result = cursor.fetchone()

            if result['count'] == 0:
                raise HTTPException(status_code=400, detail="Like not found")

            # 좋아요 삭제
            delete_query = """
            DELETE FROM likes
            WHERE userId = %s AND contentId = %s
            """
            cursor.execute(delete_query, (like.userId, like.contentId))

            # 대상 테이블 이름 가져오기
            cursor.execute("SELECT target_table FROM main_total_v2 WHERE contentsid = %s", (like.contentId,))
            result = cursor.fetchone()

            if result and 'target_table' in result:
                target_table = result['target_table']
            else:
                raise HTTPException(status_code=400, detail="Content ID not found")

            # 허용된 테이블 이름인지 검증
            allowed_tables = ['visit_main_fix', 'festival_main', 'stay_main',
                              'culture_main', 'food_main', 'leports_main', 'shopping_main']  # 실제 테이블 이름으로 대체하세요.
            if target_table not in allowed_tables:
                raise HTTPException(status_code=400, detail="Invalid target table")

            # 좋아요 수 감소
            update_query = f"""
                        UPDATE {target_table}
                        SET like_count = like_count - 1
                        WHERE contentid = %s
                        """
            cursor.execute(update_query, (like.contentId,))

        return {"message": "Destination unliked successfully"}
    except pymysql.MySQLError as err:
        print(f"Database Error: {err}")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        connection.close()


# 좋아요 상태 확인 엔드포인트
@router.get("/like/status")
async def check_like_status(userId: int, contentId: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            check_query = """
            SELECT COUNT(*) as count FROM likes
            WHERE userId = %s AND contentId = %s
            """
            cursor.execute(check_query, (userId, contentId))
            result = cursor.fetchone()

            liked = result['count'] > 0

        return {"liked": liked}
    except pymysql.MySQLError as err:
        print(f"Database Error: {err}")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        connection.close()