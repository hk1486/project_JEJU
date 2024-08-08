import pymysql
from sshtunnel import SSHTunnelForwarder
from dotenv import load_dotenv
import os

load_dotenv()

# SSH 및 MySQL 연결 정보
SSH_HOSTNAME = os.getenv('SSH_HOSTNAME')
SSH_PORT = int(os.getenv('SSH_PORT'))
SSH_USERNAME = os.getenv('SSH_USERNAME')
SSH_KEY_FILE = os.getenv('SSH_KEY_FILE')

MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

def create_onboarding_info_table():
    with SSHTunnelForwarder(
            (SSH_HOSTNAME, SSH_PORT),
            ssh_username=SSH_USERNAME,
            ssh_pkey=SSH_KEY_FILE,
            remote_bind_address=(MYSQL_HOSTNAME, MYSQL_PORT)
    ) as tunnel:
        tunnel.start()
        connection = pymysql.connect(
            host='127.0.0.1',
            port=tunnel.local_bind_port,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )

        try:
            with connection.cursor() as cursor:
                # 테이블 생성 SQL 쿼리
                create_table_query = """
                        CREATE TABLE IF NOT EXISTS onboarding_info (
                            userId INT PRIMARY KEY,
                            ageRange INT NOT NULL,
                            gender INT NOT NULL,
                            travelType JSON NOT NULL
                        )
                        """
                # 테이블 생성 쿼리 실행
                cursor.execute(create_table_query)

            # 변경사항 커밋
            connection.commit()

        finally:
            # 연결 닫기
            connection.close()

    print("onboarding_info 테이블이 성공적으로 생성되었습니다.")

if __name__ == "__main__":
    create_onboarding_info_table()