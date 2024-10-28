import pymysql
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()


# DB 연결 설정
def get_db_connection():
    return pymysql.connect(
        host=os.getenv('MYSQL_HOSTNAME'),
        user=os.getenv('MYSQL_USERNAME'),
        password=os.getenv('MYSQL_PASSWORD'),
        db=os.getenv('MYSQL_DATABASE'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


def update_stay_main_prices():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 컬럼 존재 여부 확인
            check_column_query = """
            SELECT COUNT(*) as count
            FROM information_schema.columns 
            WHERE table_name = 'stay_main' 
            AND column_name = 'numprice'
            """
            cursor.execute(check_column_query)
            result = cursor.fetchone()

            # 2. 컬럼이 없으면 생성
            if result['count'] == 0:
                alter_table_query = """
                ALTER TABLE stay_main 
                ADD COLUMN numprice INT DEFAULT NULL
                """
                cursor.execute(alter_table_query)
                print("numprice 컬럼이 생성되었습니다.")

            # 3. 데이터 업데이트
            update_query = """
            UPDATE stay_main sm
            LEFT JOIN (
                SELECT contentid, 
                       MIN(NULLIF(roomoffseasonminfee1, 0)) as min_price
                FROM stay_info
                WHERE roomoffseasonminfee1 IS NOT NULL
                GROUP BY contentid
            ) si ON sm.contentid = si.contentid
            SET sm.numprice = si.min_price
            """
            cursor.execute(update_query)

            # 변경사항 저장
            conn.commit()

            # 결과 확인
            cursor.execute("SELECT COUNT(*) as count FROM stay_main WHERE numprice IS NOT NULL")
            result = cursor.fetchone()
            print(f"업데이트된 레코드 수: {result['count']}")

    except Exception as e:
        print(f"에러 발생: {str(e)}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    update_stay_main_prices()